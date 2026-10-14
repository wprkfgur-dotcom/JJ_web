import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('138.2.62.43', port=2222, username='huxley', password='lee0320', timeout=5)

stdin, stdout, stderr = ssh.exec_command('grep -C 5 "auto_trade" /home/huxley/oracle_web_server/data/accounts.json')
out = stdout.read().decode('utf-8', errors='replace')
print("Remote auto_trade:\n", out)

with open("remote_check_output.txt", "w", encoding="utf-8") as f:
    f.write(f"Remote auto_trade:\n{out}\n\n")
    stdin, stdout, stderr = ssh.exec_command('sudo journalctl -u jj_invest --no-pager -n 35')
    raw_log = stdout.read().decode('utf-8', errors='replace')
    f.write(f"Remote jj_invest log:\n{raw_log}\n")

print("Done writing to remote_check_output.txt")
ssh.close()
