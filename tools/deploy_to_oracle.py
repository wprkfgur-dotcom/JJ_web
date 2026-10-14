import paramiko
import time

def deploy():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("Connecting to Oracle Server (138.2.62.43:2222)...")
    ssh.connect('138.2.62.43', port=2222, username='huxley', password='lee0320', timeout=10)

    def run_remote(cmd):
        print(f"\n>>> Remote: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        if out.strip():
            print(out.strip())
        if err.strip():
            print("STDERR:", err.strip())

    run_remote("cd /home/huxley/oracle_web_server && git pull origin main")
    run_remote("sudo systemctl restart jj_invest")
    time.sleep(2)
    run_remote("sudo systemctl status jj_invest --no-pager -n 10")
    ssh.close()
    print("\n[SUCCESS] Deployment complete!")

if __name__ == "__main__":
    deploy()
