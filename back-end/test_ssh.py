import paramiko
import warnings
warnings.filterwarnings("ignore")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
pkey = paramiko.Ed25519Key.from_private_key_file(r"C:\Users\Mariano\.ssh\id_ed25519")
ssh.connect("191.252.208.43", username="root", pkey=pkey, timeout=8)

cmds = {
    "cpu": 'awk \'/^cpu /{u=$2+$4; t=$2+$3+$4+$5+$6+$7+$8; printf "%.1f\\n",(t>0)?(u/t)*100:0}\' /proc/stat',
    "load": "cat /proc/loadavg | awk '{print $1, $2, $3}'",
    "network": "grep -E 'eth0|ens[0-9]|enp[0-9]' /proc/net/dev | awk '{print $2, $10}'",
}

for k, v in cmds.items():
    _, out, err = ssh.exec_command(v)
    result = out.read().decode().strip()
    error = err.read().decode().strip()
    print(f"=== {k} ===")
    print("OUT:", repr(result))
    if error:
        print("ERR:", repr(error))

ssh.close()
