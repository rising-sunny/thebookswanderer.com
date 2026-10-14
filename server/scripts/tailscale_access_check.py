"""Read-only VPN/SSH diagnostics, without auth keys, state files or peer inventory."""
import json
import shutil
import subprocess


def run(argv):
    p=subprocess.run(argv,capture_output=True,text=True,timeout=15)
    return p.returncode,p.stdout.strip()

result={'tailscale_installed':bool(shutil.which('tailscale'))}
if shutil.which('systemctl'):
    result['tailscaled_service']=run(['systemctl','is-active','tailscaled'])[1]
if result['tailscale_installed']:
    code,out=run(['tailscale','status','--json'])
    result['status_exit_code']=code
    try:
        status=json.loads(out)
        self_info=status.get('Self') or {}
        result['tailscale']={k:status.get(k) for k in ('BackendState','Health')}
        result['tailscale']['self']={k:self_info.get(k) for k in ('HostName','DNSName','TailscaleIPs','Online','Tags')}
    except ValueError:result['status_available']=False
if shutil.which('ss'):
    code,out=run(['ss','-ltn'])
    result['ssh_listeners']=[line for line in out.splitlines() if ':22 ' in line]
sshd=shutil.which('sshd') or '/usr/sbin/sshd'
if shutil.which(sshd):
    code,out=run([sshd,'-T'])
    allowed=('port ','listenaddress ','pubkeyauthentication ','passwordauthentication ','permitrootlogin ')
    result['sshd_configuration']=[line for line in out.splitlines() if line.startswith(allowed)]
print(json.dumps(result,indent=2))
