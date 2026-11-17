#!/usr/bin/env python3
"""Set or reset the separate LAN web password without changing scanner secrets."""
import getpass
import grp
import json
import os
from pathlib import Path
import secrets
import sys
import socket
from werkzeug.security import generate_password_hash
from appliance import atomic_json


def main():
    if os.geteuid()!=0 or not sys.stdin.isatty():
        print('Bitte mit sudo in einem interaktiven Terminal ausführen.',file=sys.stderr);return 1
    os.umask(0o077)
    path=Path('/etc/ix500-paperless/web.json')
    previous=json.loads(path.read_text()) if path.exists() else {}
    if previous and input('Webpasswort beibehalten? [ja]: ').strip().lower() in ('','ja','j'):
        print(f"Webzugang bleibt auf Port {previous.get('port',8080)} aktiv.");return 0
    print('Separates Webpasswort festlegen (mindestens 12 Zeichen). Eingabe bleibt unsichtbar.')
    password=getpass.getpass('Neues Webpasswort: ')
    if not 12<=len(password)<=256 or password!=getpass.getpass('Webpasswort wiederholen: '):
        print('Passwörter stimmen nicht überein oder Länge ungültig.',file=sys.stderr);return 1
    text=input(f"Webport [{previous.get('port',8080)}]: ").strip()
    port=int(text) if text else previous.get('port',8080)
    if not 1024<=port<=65535: raise ValueError('Port muss zwischen 1024 und 65535 liegen.')
    path.parent.mkdir(exist_ok=True,parents=True)
    atomic_json(path,dict(password_hash=generate_password_hash(password,method='pbkdf2:sha256:600000'),
                          secret_key=secrets.token_urlsafe(48),host='0.0.0.0',port=port))
    os.chown(path,0,grp.getgrnam('ix500').gr_gid);os.chmod(path,0o640)
    print(f'Webzugang gespeichert: http://{socket.gethostname().split('.')[0]}.local:{port}/ (alternativ Pi-IP).')
    print('Nur im vertrauenswürdigen Heimnetz verwenden. HTTP verschlüsselt die Verbindung nicht.')
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,EOFError,KeyboardInterrupt):
        print('Webeinrichtung abgebrochen oder fehlgeschlagen. Bitte erneut ausführen.',file=sys.stderr);sys.exit(1)
