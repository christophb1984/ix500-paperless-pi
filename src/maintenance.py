#!/usr/bin/env python3
"""Serialize update shutdown with the worker's paper-feed start barrier."""
import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import control as c


@contextmanager
def existing_lock(path):
    # Never create runtime files as root or follow a service-writable symlink.
    fd=os.open(path,os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Scandienst ist gerade beschäftigt; Update später erneut starten.') from None
        yield


def guarded_stop(root,stop):
    with existing_lock(root/'control.lock'):
        status=c.read_json(root/'control-status.json',{})
        working=root/'working'
        if status.get('state')=='scanning' or (working.exists() and any(working.iterdir())) or (root/'scan-request.json').exists():
            raise RuntimeError('Scan läuft oder wartet. Abschluss abwarten, dann Update erneut starten.')
        # The daemon cannot commit a new hardware/browser start until this synchronous stop completes.
        stop()


def stop_services():
    for unit in ('ix500-web.service','ix500-scan.service','ix500-upload.timer','ix500-upload.service'):
        result=subprocess.run(['systemctl','show','--property=LoadState','--value',unit],capture_output=True,text=True)
        state=result.stdout.strip()
        if state=='not-found': continue
        if result.returncode or not state: raise RuntimeError('Dienststatus konnte nicht geprüft werden: '+unit)
        subprocess.run(['systemctl','stop',unit],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,default=Path('/var/lib/ix500-paperless'))
    args=parser.parse_args()
    if os.geteuid()!=0: raise RuntimeError('Für das Update sudo verwenden.')
    installed=Path('/opt/ix500-paperless')
    if (installed/'appliance.py').exists() and not (installed/'control.py').exists():
        result=subprocess.run(['systemctl','show','--property=ActiveState','--value','ix500-scan.service'],capture_output=True,text=True,check=True)
        if result.stdout.strip() not in ('inactive','failed',''):
            raise RuntimeError('Alte Version: Scandienst zuerst im Leerlauf manuell stoppen, dann Update erneut starten.')
        stop_services()
    else:
        # The installer creates only the state root as ix500. The lock is created as the service user.
        subprocess.run(['runuser','-u','ix500','--','touch',str(args.state/'control.lock')],check=True)
        guarded_stop(args.state,stop_services)
    # A separately launched administrator CLI scan must also have finished before files are replaced.
    scanner_lock=args.state/'scanner.lock'
    if scanner_lock.exists():
        with existing_lock(scanner_lock): pass
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as error:
        print('Update gestoppt: '+str(error),file=sys.stderr);sys.exit(1)
