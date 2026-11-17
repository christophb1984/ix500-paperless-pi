#!/usr/bin/env python3
"""Interactive target-Pi configuration; secrets never enter the project checkout."""
import argparse
import getpass
import grp
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import tempfile
import uuid

from appliance import DEFAULTS, validate_config, atomic_json

CONFIG=Path('/etc/ix500-paperless/config.json')
WIFI=Path('/etc/NetworkManager/system-connections/ix500-appliance.nmconnection')
SSH=Path('/etc/ssh/sshd_config.d/80-ix500-appliance.conf')


def valid_hostname(value):
    return bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',value))


def valid_user(value):
    return value not in ('root','ix500') and bool(re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}',value))


def keyfile_escape(value):
    return value.replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t').replace(' ','\\s')


def wifi_keyfile(ssid,psk,interface):
    return (f'[connection]\nid=ix500-appliance\nuuid={uuid.uuid4()}\ntype=wifi\n'
            f'interface-name={interface}\nautoconnect=true\nautoconnect-priority=10\n\n'
            f'[wifi]\nmode=infrastructure\nssid={keyfile_escape(ssid)}\n\n'
            f'[wifi-security]\nkey-mgmt=wpa-psk\npsk={keyfile_escape(psk)}\n\n'
            '[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n')


def ask(prompt,default='',secret=False):
    message=prompt+(f' [{default}]' if default and not secret else '')+': '
    value=getpass.getpass(message) if secret else input(message).strip()
    return value or default


def choose(prompt,values,default):
    while True:
        value=ask(prompt+' ('+'/'.join(values)+')',default)
        if value in values: return value
        print('Bitte eine der angegebenen Optionen wählen.')


def run(args,**kwargs):
    # No exception containing arguments or output is printed by main.
    return subprocess.run(args,check=True,**kwargs)


def write_private(path,text,mode=0o600,gid=0):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(text)
    os.chmod(tmp,mode);os.chown(tmp,0,gid)
    tmp.replace(path)


def collect():
    cfg=dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
        print('Vorhandene Einstellungen als Vorgaben geladen. Token mit Enter behalten.')
    print('\nNetzwerk und SSH müssen für den ersten Zugriff bereits über Pi Imager eingerichtet sein.')
    network=choose('Netzwerk','behalten ethernet wlan'.split(),'behalten')
    wifi=None
    if network=='wlan':
        interface=ask('WLAN-Interface','wlan0')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,15}',interface): raise ValueError('Ungültiges Interface.')
        if not Path('/sys/class/net',interface).exists(): raise ValueError('WLAN-Interface fehlt.')
        country=ask('WLAN-Land (ISO, z.B. DE)','DE').upper()
        if not re.fullmatch('[A-Z]{2}',country): raise ValueError('Ungültiges WLAN-Land.')
        ssid=ask('WLAN-SSID')
        if not 1<=len(ssid.encode())<=32: raise ValueError('SSID muss 1–32 Bytes haben.')
        psk=ask('WLAN-Passwort (WPA2/WPA3-Personal, keine Enterprise-Netze)',secret=True)
        if not (8<=len(psk)<=63 or re.fullmatch('[a-fA-F0-9]{64}',psk)):
            raise ValueError('WLAN-Passwort muss 8–63 Zeichen oder 64 Hex-Zeichen haben.')
        wifi=(wifi_keyfile(ssid,psk,interface),country)
    host=ask('Hostname',Path('/etc/hostname').read_text().strip())
    if not valid_hostname(host): raise ValueError('Ungültiger Hostname (nur Kleinbuchstaben, Zahlen, Bindestrich).')
    admin=ask('Administrativer Benutzer (vorhanden oder neu)',os.environ.get('SUDO_USER','') or 'scanadmin')
    if not valid_user(admin): raise ValueError('Ungültiger Benutzername.')
    try:
        account=pwd.getpwnam(admin)
        if account.pw_uid<1000: raise ValueError('Kein Systemkonto als Administrator verwenden.')
        new_user=False
        print('Vorhandener Benutzer behält sein Passwort und seine Gruppenmitgliedschaften.')
    except KeyError:
        new_user=True
    password=None
    if new_user:
        print('Neuer Administrator erhält sudo-Mitgliedschaft. Benutzerpasswort verdeckt eingeben.')
        password=ask('Neues Benutzerpasswort',secret=True)
        if len(password)<12 or '\n' in password or '\r' in password:
            raise ValueError('Mindestens 12 Zeichen; kein Zeilenumbruch.')
        if password!=ask('Passwort wiederholen',secret=True): raise ValueError('Passwörter stimmen nicht überein.')
    ssh_mode=choose('SSH für diesen Benutzer','behalten passwort schluessel'.split(),'behalten' if not new_user else 'schluessel')
    key=None
    if ssh_mode=='schluessel':
        key=ask('Öffentlicher SSH-Schlüssel (ganze ssh-ed25519/ssh-rsa/... Zeile, kein privater Schlüssel)')
        if '\n' in key or not key.startswith(('ssh-ed25519 ','ssh-rsa ','ecdsa-sha2-','sk-ssh-','sk-ecdsa-')):
            raise ValueError('Öffentlicher SSH-Schlüssel erwartet.')
        with tempfile.NamedTemporaryFile(mode='w',prefix='ix500-public-key-') as public:
            public.write(key+'\n');public.flush()
            run(['ssh-keygen','-l','-f',public.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    cfg['paperless_url']=ask('Paperless-Basis-URL (inkl. Unterpfad, ohne /api)',cfg.get('paperless_url','https://paperless.example.org')).rstrip('/')
    cfg['allow_http']=False
    if cfg['paperless_url'].startswith('http://'):
        print('HTTP überträgt Token und Dokumente unverschlüsselt. Nur im vertrauenswürdigen LAN verwenden.')
        cfg['allow_http']=choose('HTTP bewusst verwenden?',('ja','nein'),'nein')=='ja'
    cfg['paperless_token']=ask('Paperless-API-Token (verdeckt)',cfg.get('paperless_token',''),secret=True)
    cfg['ca_bundle']=ask('Optional: Pfad zu eigener CA-Datei (leer = System-CA)',cfg.get('ca_bundle',''))
    profile=choose('Scanprofil',('farbe200','farbe300','grau300','individuell'),'farbe200')
    if profile=='individuell':
        cfg['mode']=choose('Farbmodus',('Color','Gray'),cfg['mode'])
        cfg['dpi']=int(ask('Auflösung 100–600 dpi',str(cfg['dpi'])))
    else:
        cfg['mode']='Gray' if profile=='grau300' else 'Color'
        cfg['dpi']=200 if profile=='farbe200' else 300
    paper=choose('Papierformat',('a4','legal'),'a4')
    cfg['width_mm'],cfg['height_mm']=(210,297) if paper=='a4' else (216,356)
    print('Leerseitenfilter: 0=aus, 0.05=vorsichtig. Bei entfernten Seiten bleibt original.pdf erhalten.')
    cfg['blank_percent']=float(ask('Dunkelpixel-Prozent unter dem eine Seite entfällt (0–1)','0'))
    cfg['device']=ask('SANE-Gerät (leer = genau einen iX500 automatisch erkennen)',cfg.get('device',''))
    validate_config(cfg)
    return cfg,network,wifi,host,admin,new_user,password,ssh_mode,key


def configure_ssh(admin,mode,key):
    if mode=='behalten': return
    account=pwd.getpwnam(admin)
    if key:
        home=Path(account.pw_dir)
        folder=home/'.ssh'; folder.mkdir(mode=0o700,exist_ok=True)
        if folder.is_symlink(): raise ValueError('.ssh darf kein Symlink sein.')
        authorized=folder/'authorized_keys'
        if authorized.is_symlink(): raise ValueError('authorized_keys darf kein Symlink sein.')
        existing=authorized.read_text() if authorized.exists() else ''
        if key not in existing.splitlines(): authorized.write_text(existing.rstrip()+'\n'+key+'\n')
        os.chown(folder,account.pw_uid,account.pw_gid);os.chmod(folder,0o700)
        os.chown(authorized,account.pw_uid,account.pw_gid);os.chmod(authorized,0o600)
    # One managed drop-in; other users' SSH policy remains under system administration.
    previous=SSH.read_text() if SSH.exists() else None
    policy=(f'# Managed by ix500-paperless-pi\nMatch User {admin}\n'
            f'    PasswordAuthentication {"no" if key else "yes"}\n'
            '    KbdInteractiveAuthentication no\n    PubkeyAuthentication yes\nMatch all\n')
    write_private(SSH,policy,0o644)
    try: run(['/usr/sbin/sshd','-t'],stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        if previous is None: SSH.unlink()
        else: write_private(SSH,previous,0o644)
        raise ValueError('SSH-Prüfung fehlgeschlagen; vorherige Richtlinie wiederhergestellt.') from None
    run(['systemctl','enable','--now','ssh'])
    run(['systemctl','reload','ssh'])


def apply(settings):
    cfg,network,wifi,host,admin,new_user,password,ssh_mode,key=settings
    # Stop scan/upload workers before changing config; finish/retain outstanding jobs on restart.
    run(['systemctl','stop','ix500-upload.timer','ix500-upload.service','ix500-scan.service','ix500-web.service'])
    if new_user:
        run(['useradd','--create-home','--shell','/bin/bash',admin])
        run(['chpasswd'],input=admin+':'+password+'\n',text=True)
        run(['usermod','-aG','sudo',admin])
    run(['hostnamectl','set-hostname',host])
    hosts=Path('/etc/hosts')
    lines=hosts.read_text().splitlines()
    lines=[line for line in lines if not re.match(r'^127\.0\.1\.1\s',line)]
    hosts.write_text('\n'.join(lines)+f'\n127.0.1.1\t{host}\n')
    configure_ssh(admin,ssh_mode,key)
    if wifi:
        text,country=wifi
        run(['raspi-config','nonint','do_wifi_country',country])
        write_private(WIFI,text)
        run(['nmcli','connection','load',str(WIFI)],stdout=subprocess.DEVNULL)
    elif network=='ethernet':
        # Only create this project's own DHCP profile if absent; no active connection is brought down.
        exists=subprocess.run(['nmcli','connection','show','ix500-ethernet'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
        if not exists:
            run(['nmcli','connection','add','type','ethernet','ifname','eth0','con-name','ix500-ethernet',
                 'ipv4.method','auto','ipv6.method','auto','connection.autoconnect','yes'],stdout=subprocess.DEVNULL)
    gid=grp.getgrnam('ix500').gr_gid
    CONFIG.parent.mkdir(mode=0o750,parents=True,exist_ok=True)
    os.chown(CONFIG.parent,0,gid);os.chmod(CONFIG.parent,0o750)
    atomic_json(CONFIG,cfg);os.chown(CONFIG,0,gid);os.chmod(CONFIG,0o640)
    print('\nKonfiguration gespeichert. API-Token und WLAN-Passwort wurden nicht im Checkout gespeichert.')
    check=subprocess.run(['runuser','-u','ix500','--','/usr/bin/python3','/opt/ix500-paperless/appliance.py','check'])
    if check.returncode:
        print('Geräte/API-Prüfung fehlgeschlagen. Scanner aufklappen, USB prüfen, README beachten.')
    print('Optionaler Testscan: 1–2 beidseitig beschriftete A4-Blätter einlegen. Der Scan wird hochgeladen.')
    if choose('Testscan jetzt?',('ja','nein'),'nein')=='ja':
        scan=subprocess.run(['runuser','-u','ix500','--','/usr/bin/python3','/opt/ix500-paperless/appliance.py','scan'])
        if scan.returncode: print('Testscan fehlgeschlagen; lokale Warteschlange und scanner.log prüfen.')
        subprocess.run(['runuser','-u','ix500','--','/usr/bin/python3','/opt/ix500-paperless/appliance.py','upload'])
    run(['systemctl','enable','--now','ix500-scan.service','ix500-upload.timer'])
    if Path('/etc/ix500-paperless/web.json').exists(): run(['systemctl','start','ix500-web.service'])
    print(f'Dienste gestartet. SSH-Ziel nach Neustart: {admin}@{host}.local (alternativ IP im Router).')
    print('Vor Schließen der aktuellen Sitzung Anmeldung aus einer zweiten SSH-Sitzung prüfen.')
    if wifi:
        print('WLAN-Profil gespeichert; Aktivierung kann die aktuelle SSH-Verbindung trennen.')
        if choose('WLAN jetzt aktivieren?',('ja','nein'),'nein')=='ja':
            run(['nmcli','connection','up','ix500-appliance'],stdout=subprocess.DEVNULL)
        else: print('Später aktivieren: sudo nmcli connection up ix500-appliance; alternativ Neustart.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    if os.geteuid()!=0 or not sys.stdin.isatty():
        print('Bitte als root/sudo interaktiv am Pi ausführen (SSH mit Terminal oder lokale Konsole).',file=sys.stderr)
        return 1
    os.umask(0o077)
    try: apply(collect())
    except subprocess.CalledProcessError as error:
        print(f'\nSystemaktion {Path(error.cmd[0]).name} fehlgeschlagen (Exit {error.returncode}). Dienste/SSH/Netzwerk prüfen und Setup erneut ausführen.',file=sys.stderr)
        return 1
    except (ValueError,OSError,EOFError,KeyboardInterrupt):
        print('\nEinrichtung abgebrochen oder Aktion fehlgeschlagen. Es erfolgt kein automatischer Rollback bereits angewandter Systemänderungen. Dienste/SSH/Netzwerk prüfen und Setup erneut ausführen. Geheimnisse werden nicht ausgegeben.',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
