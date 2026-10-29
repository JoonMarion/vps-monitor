import datetime
import base64
import hashlib
import hmac
import io

import paramiko


class UntrustedHostKey(paramiko.SSHException):
    pass


class PinnedHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected):
        self.expected = expected

    def missing_host_key(self, client, hostname, key):
        actual = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        if not self.expected or not hmac.compare_digest(actual.encode(), self.expected.encode()):
            raise UntrustedHostKey("A identidade SSH da VPS não foi confirmada.")


def connect_ssh(ssh, server):
    fingerprint = server.get("host_key_fingerprint", "")
    if fingerprint or server.get("_require_host_fingerprint"):
        # Verification happens before Paramiko sends any password or SSH authentication.
        ssh.set_missing_host_key_policy(PinnedHostKeyPolicy(fingerprint))
    else:
        # Compatibility for local development; production always requires a pin.
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    options = {
        "hostname": server["ip"],
        "port": server.get("port", 22),
        "username": server["user"],
        "timeout": 8,
        "auth_timeout": 8,
        "banner_timeout": 8,
        "look_for_keys": False,
        "allow_agent": False,
    }
    if server.get("ssh_key"):
        # Keys belong to the user; never read a path from the API host's disk.
        key = server["ssh_key"]
        passphrase = server.get("passphrase") or None
        for key_type in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                options["pkey"] = key_type.from_private_key(io.StringIO(key), password=passphrase)
                break
            except paramiko.PasswordRequiredException:
                raise
            except (paramiko.SSHException, ValueError):
                continue
        else:
            raise paramiko.SSHException("Chave privada inválida ou senha da chave incorreta.")
    else:
        options["password"] = server["password"]
    ssh.connect(**options)


def ssh_error_message(error):
    if isinstance(error, (UntrustedHostKey, paramiko.BadHostKeyException)):
        return "A identidade SSH da VPS não foi confirmada. Confira a fingerprint no console do provedor e cadastre a VPS com a chave correta."
    if isinstance(error, paramiko.AuthenticationException):
        return "Falha na autenticação SSH. Confira o usuário e as credenciais."
    if isinstance(error, paramiko.PasswordRequiredException):
        return "Informe a senha da chave privada SSH."
    return "Não foi possível coletar os dados. Confira o IP, a porta e as credenciais SSH."

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
        "lastChecked": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    ssh = paramiko.SSHClient()

    try:
        connect_ssh(ssh, server)

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
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
            metrics[key] = stdout.read().decode().strip()

        # Parse CPU
        try:
            result["cpu"] = float(metrics["cpu"].replace(',', '.'))
        except (ValueError, TypeError):
            result["cpu"] = 0.0

        # Parse RAM (input is MB, output must be GB)
        try:
            ram_parts = metrics["ram"].split()
            if len(ram_parts) == 2:
                total_mb, free_mb = map(float, ram_parts)
                used_mb = total_mb - free_mb
                result["ram"]["total"] = round(total_mb / 1024, 2)
                result["ram"]["used"] = round(used_mb / 1024, 2)
        except (ValueError, TypeError):
            pass

        # Parse Disk (input is GB, output must be GB)
        try:
            disk_parts = metrics["disk"].split()
            if len(disk_parts) == 2:
                result["disk"]["total"] = int(disk_parts[0])
                result["disk"]["used"] = int(disk_parts[1])
        except (ValueError, TypeError):
            pass

        # Parse Uptime
        result["uptime"] = metrics["uptime"] or "N/A"

        # Parse Load Average
        try:
            load_parts = metrics["load"].split()
            result["load"] = [float(x.replace(',', '.')) for x in load_parts]
        except (ValueError, TypeError):
            result["load"] = [0.0, 0.0, 0.0]

        # Parse Processes
        try:
            result["processes"] = int(metrics["processes"])
        except (ValueError, TypeError):
            result["processes"] = 0

        # Parse OS
        result["os"] = metrics["os"] or "Linux"

        # Parse Network
        try:
            net_parts = metrics["network"].split()
            if len(net_parts) == 2:
                result["network"]["rx"] = format_network_bytes(net_parts[0])
                result["network"]["tx"] = format_network_bytes(net_parts[1])
        except (ValueError, TypeError):
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
        result["status"] = "offline"
        result["error_details"] = ssh_error_message(e)
    finally:
        ssh.close()

    return result

def debug_vps_ssh(server):
    entry = {"name": server["name"], "ip": server["ip"], "user": server["user"]}
    ssh = paramiko.SSHClient()
    try:
        connect_ssh(ssh, server)
        _, stdout, _ = ssh.exec_command("echo OK", timeout=8)
        entry.update(status="connected", echo=stdout.read().decode().strip())
    except Exception as error:
        entry.update(status="failed", error=ssh_error_message(error))
    finally:
        ssh.close()
    return entry
