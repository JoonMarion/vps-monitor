import time
import datetime
import concurrent.futures
import warnings
import json
import os
import paramiko
from flask import Flask, jsonify, redirect, request
from flask_cors import CORS

# Suppress annoying Paramiko/Cryptography deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# Path to the servers persistence file
SERVERS_FILE = os.path.join(os.path.dirname(__file__), 'servers.json')

def load_servers():
    if not os.path.exists(SERVERS_FILE):
        return []
    with open(SERVERS_FILE, 'r') as f:
        return json.load(f)

def save_servers(servers):
    with open(SERVERS_FILE, 'w') as f:
        json.dump(servers, f, indent=4)

def format_network_bytes(byte_count):
    """
    Format bytes to readable string according to requirements:
    - ≥ 1 GB → "X.X GB"
    - ≥ 1 MB → "XXX MB"
    - < 1 MB → "XXX KB"
    """
    try:
        bytes_val = float(byte_count)
    except (ValueError, TypeError):
        return "0 KB"

    gb = 1024**3
    mb = 1024**2
    kb = 1024

    if bytes_val >= gb:
        return f"{bytes_val / gb:.1f} GB"
    elif bytes_val >= mb:
        return f"{int(bytes_val / mb)} MB"
    else:
        return f"{int(bytes_val / kb)} KB"

def fetch_vps_metrics(server):
    """
    Connects to a single VPS via SSH and collects metrics.
    """
    result = {
        "id": server.get("id", server["name"]),
        "name": server["name"],
        "ip": server["ip"],
        "location": server["location"],
        "os": "Unknown",
        "uptime": "N/A",
        "cpu": 0.0,
        "ram": {"used": 0.0, "total": 0.0},
        "disk": {"used": 0, "total": 0},
        "load": [0.0, 0.0, 0.0],
        "network": {"rx": "0 KB", "tx": "0 KB"},
        "processes": 0,
        "status": "offline",
        "lastChecked": datetime.datetime.now().isoformat()
    }

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # Connection setup with 8s timeout
        connect_kwargs = {
            "hostname": server["ip"],
            "username": server["user"],
            "timeout": 8,
            "look_for_keys": False, # Prevent searching default keys if one is provided
            "allow_agent": False    # Avoid using SSH agent for now to keep it predictable
        }
        
        if "ssh_key" in server:
            # Try loading the key explicitly (handles Ed25519 and RSA)
            passphrase = server.get("passphrase")  # optional passphrase for encrypted keys
            try:
                pkey = paramiko.Ed25519Key.from_private_key_file(server["ssh_key"], password=passphrase)
                connect_kwargs["pkey"] = pkey
            except Exception:
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(server["ssh_key"], password=passphrase)
                    connect_kwargs["pkey"] = pkey
                except Exception:
                    # Last resort: let paramiko resolve the key itself
                    connect_kwargs["key_filename"] = server["ssh_key"]
                    connect_kwargs["look_for_keys"] = True
        elif "password" in server:
            connect_kwargs["password"] = server["password"]

        ssh.connect(**connect_kwargs)

        # Commands to execute
        commands = {
            # 100 - idle gives total CPU in use; works reliably on all Debian versions
            "cpu": "awk '/^cpu /{u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; printf \"%.1f\\n\",(t>0)?(u/t)*100:0}' /proc/stat",
            "ram": "free -m | awk '/^Mem/{print $2, $4}'",
            "disk": "df -BG / | awk 'NR==2{gsub(\"G\",\"\"); print $2, $3}'",
            "uptime": "uptime -p | sed 's/up //'",
            "load": "cat /proc/loadavg | awk '{print $1, $2, $3}'",
            "processes": "ps aux | wc -l",
            "os": "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
            # \s is not supported in mawk (Debian default); use grep to filter interface
            "network": "grep -E 'eth0|ens[0-9]|enp[0-9]' /proc/net/dev | awk '{print $2, $10}'"
        }

        # Execute commands and parse results
        metrics = {}
        for key, cmd in commands.items():
            stdin, stdout, stderr = ssh.exec_command(cmd)
            metrics[key] = stdout.read().decode().strip()

        # Parse CPU
        try:
            result["cpu"] = float(metrics["cpu"].replace(',', '.'))
        except:
            result["cpu"] = 0.0

        # Parse RAM (input is MB, output must be GB)
        try:
            ram_parts = metrics["ram"].split()
            if len(ram_parts) == 2:
                total_mb, free_mb = map(float, ram_parts)
                used_mb = total_mb - free_mb
                result["ram"]["total"] = round(total_mb / 1024, 2)
                result["ram"]["used"] = round(used_mb / 1024, 2)
        except:
            pass

        # Parse Disk (input is GB, output must be GB)
        try:
            disk_parts = metrics["disk"].split()
            if len(disk_parts) == 2:
                result["disk"]["total"] = int(disk_parts[0])
                result["disk"]["used"] = int(disk_parts[1])
        except:
            pass

        # Parse Uptime
        result["uptime"] = metrics["uptime"] or "N/A"

        # Parse Load Average
        try:
            load_parts = metrics["load"].split()
            result["load"] = [float(x.replace(',', '.')) for x in load_parts]
        except:
            result["load"] = [0.0, 0.0, 0.0]

        # Parse Processes
        try:
            result["processes"] = int(metrics["processes"])
        except:
            result["processes"] = 0

        # Parse OS
        result["os"] = metrics["os"] or "Linux"

        # Parse Network
        try:
            net_parts = metrics["network"].split()
            if len(net_parts) == 2:
                result["network"]["rx"] = format_network_bytes(net_parts[0])
                result["network"]["tx"] = format_network_bytes(net_parts[1])
        except:
            pass

        # Determine Status
        # CPU > 85% or Disk > 90% -> warning
        disk_usage_pct = (result["disk"]["used"] / result["disk"]["total"] * 100) if result["disk"]["total"] > 0 else 0
        if result["cpu"] > 85 or disk_usage_pct > 90:
            result["status"] = "warning"
        else:
            result["status"] = "online"

    except Exception as e:
        # If SSH fails, status remains 'offline'
        print(f"Error connecting to {server['name']} ({server['ip']}): {e}")
        result["status"] = "offline"
        result["error_details"] = str(e)  # Added for debugging
    finally:
        ssh.close()

    return result

@app.route('/')
def index():
    """Redirect root to API endpoint"""
    return redirect('/api/vps')

@app.route('/api/vps', methods=['GET'])
def get_vps_data():
    """
    Main endpoint to fetch all VPS metrics in parallel.
    """
    servers = load_servers()
    if not servers:
        return jsonify([])

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(servers)) as executor:
        vps_results = list(executor.map(fetch_vps_metrics, servers))
    
    return jsonify(vps_results)

@app.route('/api/vps', methods=['POST'])
def add_vps():
    """Add a new VPS to the list"""
    data = request.json
    servers = load_servers()
    
    # Simple ID generation
    new_id = str(len(servers) + 1).zfill(2)
    
    new_vps = {
        "id": new_id,
        "name": data.get("name"),
        "ip": data.get("ip"),
        "location": data.get("location", "Brasil"),
        "user": data.get("user", "root"),
        "ssh_key": data.get("ssh_key"),
        "password": data.get("password"),
        "sudo_password": data.get("sudo_password")
    }
    
    servers.append(new_vps)
    save_servers(servers)
    return jsonify(new_vps), 201

@app.route('/api/vps/<id>', methods=['DELETE'])
def delete_vps(id):
    """Delete a VPS from the list"""
    servers = load_servers()
    servers = [s for s in servers if s['id'] != id]
    save_servers(servers)
    return jsonify({"message": "Server deleted"}), 200

@app.route('/api/vps/debug-ssh', methods=['GET'])
def debug_ssh():
    """
    Diagnostic endpoint: attempts SSH on each server and returns
    the raw error message without crashing. Visit this URL in
    the browser to troubleshoot authentication issues.
    """
    results = []
    servers = load_servers()
    for server in servers:
        entry = {"name": server["name"], "ip": server["ip"], "user": server["user"]}
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = {
                "hostname": server["ip"],
                "username": server["user"],
                "timeout": 8,
                "look_for_keys": False,
                "allow_agent": False,
            }
            passphrase = server.get("passphrase")
            if "ssh_key" in server:
                connect_kwargs["key_filename"] = server["ssh_key"]
                if passphrase:
                    connect_kwargs["passphrase"] = passphrase
                connect_kwargs["look_for_keys"] = True
            elif "password" in server:
                connect_kwargs["password"] = server["password"]
            ssh.connect(**connect_kwargs)
            _, stdout, _ = ssh.exec_command("echo OK")
            entry["status"] = "connected"
            entry["echo"] = stdout.read().decode().strip()
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            entry["error_type"] = type(e).__name__
        finally:
            ssh.close()
        results.append(entry)
    return jsonify(results)


if __name__ == '__main__':
    # Default port 5000 as requested
    app.run(host='0.0.0.0', port=5000, debug=True)
