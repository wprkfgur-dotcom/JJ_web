import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('138.2.62.43', port=2222, username='huxley', password='lee0320', timeout=5)

stdin, stdout, stderr = ssh.exec_command('grep -C 5 "auto_trade" /home/huxley/oracle_web_server/data/accounts.json')
out = stdout.read().decode('utf-8', errors='replace')
print("Remote auto_trade:\n", out)

stdin, stdout, stderr = ssh.exec_command('ls -la /home/huxley/oracle_web_server/data/')
print("Remote data files:\n", stdout.read().decode('utf-8', errors='replace'))

ssh.close()
