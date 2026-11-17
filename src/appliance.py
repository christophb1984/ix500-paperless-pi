#!/usr/bin/env python3
"""ScanSnap iX500 → durable job queue → Paperless-ngx. No root at runtime."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tempfile
from urllib.parse import urlsplit, quote
import uuid

from PIL import Image
import img2pdf

LOG = logging.getLogger('ix500')
STATES = ('working', 'pending', 'inflight', 'submitted', 'sent', 'failed', 'uncertain', 'interrupted')
DEFAULTS = dict(device='', mode='Color', dpi=200, width_mm=210, height_mm=297,
                blank_percent=0.0, blank_gray_threshold=180, poll_seconds=1.0, scan_timeout=900, min_free_mb=512,
                allow_http=False, ca_bundle='')


def validate_config(cfg):
    url = urlsplit(cfg.get('paperless_url', ''))
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(c.isspace() for c in cfg['paperless_url'])):
        raise ValueError('Paperless-URL muss eine Basis-URL ohne Zugangsdaten/Query/Fragment sein.')
    if url.scheme == 'http' and cfg.get('allow_http') is not True:
        raise ValueError('HTTP erfordert allow_http=true; HTTPS ist empfohlen.')
    token = cfg.get('paperless_token', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', token):
        raise ValueError('API-Token fehlt oder enthält unzulässige Zeichen.')
    if cfg.get('mode') not in ('Color', 'Gray', 'Lineart'):
        raise ValueError('mode muss Color oder Gray sein.')
    ranges = dict(dpi=(100,600), width_mm=(50,216), height_mm=(50,356),
                  blank_percent=(0,1), poll_seconds=(0.5,10), scan_timeout=(30,3600),
                  min_free_mb=(1,1048576))
    for name,(low,high) in ranges.items():
        value=cfg.get(name)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not low <= value <= high:
            raise ValueError(f'{name} muss zwischen {low} und {high} liegen.')
    cutoff=cfg.get('blank_gray_threshold',180)
    if isinstance(cutoff,bool) or not isinstance(cutoff,int) or not 32<=cutoff<=254:
        raise ValueError('blank_gray_threshold muss ganzzahlig zwischen 32 und 254 liegen.')
    if not isinstance(cfg['dpi'],int):
        raise ValueError('dpi muss ganzzahlig sein.')
    if cfg.get('device') and not cfg['device'].startswith('fujitsu:ScanSnap iX500:'):
        raise ValueError('device muss ein iX500-SANE-Gerät sein oder leer bleiben.')
    if cfg.get('ca_bundle') and not Path(cfg['ca_bundle']).is_file():
        raise ValueError('ca_bundle ist keine lesbare Datei.')


def load_config(path):
    cfg = DEFAULTS | json.loads(Path(path).read_text())
    validate_config(cfg)
    return cfg


def atomic_json(path, data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w') as out:
        json.dump(data,out,indent=2)
        out.write('\n');out.flush();os.fsync(out.fileno())
    temporary.replace(path)
    sync_dir(path.parent)


def sync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def prepare(root):
    root.mkdir(parents=True,exist_ok=True)
    for state in STATES: (root/state).mkdir(exist_ok=True)


def move_job(job,root,state):
    target=root/state/job.name
    job.rename(target)
    sync_dir(job.parent);sync_dir(target.parent)
    return target


@contextmanager
def lock(root, name):
    prepare(root)
    with (root/(name+'.lock')).open('a') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError(f'{name} läuft bereits.') from None
        yield


def run_scanimage(args,timeout=20):
    return subprocess.run(['scanimage',*args],capture_output=True,text=True,timeout=timeout,
                          env=os.environ | {'LC_ALL':'C'})


def detect_device(cfg):
    if cfg.get('device'): return cfg['device']
    proc=run_scanimage(['-L'])
    devices=re.findall(r"device `([^`']+)'",proc.stdout)
    devices=[d for d in devices if d.startswith('fujitsu:ScanSnap iX500:')]
    if len(devices)!=1:
        raise RuntimeError('Genau einen iX500 anschließen oder device explizit konfigurieren.')
    return devices[0]


def button_state(options):
    match=re.search(r'^\s*--scan(?:\[=\(yes\|no\)\])?\s+\[(yes|no)\]',options,re.M)
    if not match:
        raise ValueError('SANE-Scan-Tastensensor fehlt oder ist inaktiv; scanimage -A prüfen.')
    return match[1]=='yes'


def read_button(device):
    proc=run_scanimage(['--device-name',device,'--all-options'])
    if proc.returncode: raise RuntimeError('Scanner nicht verfügbar, ausgeschaltet oder belegt.')
    return button_state(proc.stdout)


def make_pdf(job,cfg):
    """Process one TIFF at a time; retain a full PDF whenever filtering drops pages."""
    pages=sorted(job.glob('page-*.tiff'))
    all_jpegs, kept=[],[]
    for index,path in enumerate(pages):
        with Image.open(path) as image:
            image.load()
            with image.convert('L') as gray:
                hist=gray.histogram()
                # ponytail: simple whole-page pixel threshold; disable for sparse/low-contrast originals.
                dark_percent=100*sum(hist[:cfg.get('blank_gray_threshold', 180)])/(gray.width*gray.height)
            blank=cfg['blank_percent']>0 and dark_percent<cfg['blank_percent']
            jpeg=job/f'encoded-{index:04d}.jpg'
            with image.convert('RGB' if cfg['mode']=='Color' else 'L') as encoded:
                encoded.save(jpeg,quality=cfg.get('jpeg_quality',90),dpi=(cfg['dpi'],cfg['dpi']))
        all_jpegs.append(str(jpeg))
        if not blank: kept.append(str(jpeg))
    def write_pdf(name,paths):
        temporary=job/(name+'.tmp')
        with temporary.open('wb') as output:
            img2pdf.convert(*paths,outputstream=output,engine=img2pdf.Engine.internal)
            output.flush();os.fsync(output.fileno())
        temporary.replace(job/name)
        sync_dir(job)
    if kept: write_pdf('document.pdf',kept)
    if len(kept)<len(all_jpegs): write_pdf('original.pdf',all_jpegs)
    for jpeg in all_jpegs: Path(jpeg).unlink()
    return len(pages),len(kept)


def finish_scan(job,cfg,root,status):
    prepare(root)
    pages=list(job.glob('page-*.tiff'))
    # Unlimited scanimage batch normally converts NO_DOCS to success after the last sheet.
    # Empty feeder (7), jams (6), timeouts and half-duplex stacks must never be uploaded.
    if status!=0 or not pages or (cfg.get('source','ADF Duplex') in ('Auto','ADF Duplex') and len(pages)%2) or list(job.glob('*.part')):
        atomic_json(job/'scan.json',dict(status=status,pages=len(pages),reason='Unvollständiger/fehlgeschlagener Scan'))
        move_job(job,root,'interrupted')
        LOG.warning('Job %s zurückgehalten; Scanstatus %s, Seiten %s.',job.name,status,len(pages))
        return
    try:
        total,kept=make_pdf(job,cfg)
        atomic_json(job/'scan.json',dict(status=status,pages=total,kept=kept,dpi=cfg['dpi'],mode=cfg['mode']))
        # Complete all writes/deletions before publication; uploader may move the job immediately.
        for path in job.glob('page-*.tiff'): path.unlink()
        sync_dir(job)
        move_job(job,root,'pending' if kept else 'interrupted')
        LOG.info('Job %s: %s/%s Seiten behalten; %s.',job.name,kept,total,'Upload bereit' if kept else 'nur Leerseiten')
    except Exception:
        # Preserve TIFFs and any completed PDF. Do not expose a half-produced PDF to the uploader.
        if job.exists(): move_job(job,root,'interrupted')
        raise


def scan_once(cfg,root,device):
    prepare(root)
    if shutil.disk_usage(root).free<cfg['min_free_mb']*1024**2:
        raise RuntimeError('Zu wenig freier Speicher; Warteschlange prüfen.')
    job=root/'working'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:12])
    job.mkdir()
    from control import profile_from_config, backend_source
    atomic_json(job/'profile.json',profile_from_config(cfg))
    args=['scanimage','--device-name',device,'--source',backend_source(profile_from_config(cfg)),'--mode',cfg['mode'],
          '--resolution',str(cfg['dpi']),'--page-width',str(cfg['width_mm']),
          '--page-height',str(cfg['height_mm']),'-x',str(cfg['width_mm']),'-y',str(cfg['height_mm']),
          '--swskip','0','--format=tiff',f'--batch={job}/page-%04d.tiff','--batch-count=-1']
    for name,value in cfg.get('sane_options',{}).items():
        if isinstance(value,bool): value='yes' if value else 'no'
        elif isinstance(value,list): value=','.join(str(v) for v in value)
        args.append(f'--{name}={value}')
    LOG.info('Scanne Job %s (%s, %s dpi).',job.name,cfg['mode'],cfg['dpi'])
    with (job/'scanner.log').open('wb') as output:
        try:
            proc=subprocess.run(args,stdout=output,stderr=subprocess.STDOUT,timeout=cfg['scan_timeout'],
                                env=os.environ | {'LC_ALL':'C'})
            status=proc.returncode
        except subprocess.TimeoutExpired:
            status=124
    finish_scan(job,cfg,root,status)


def daemon(cfg,root):
    from control import (load_control, effective_config, query_capabilities,
                         worker_status, take_scan_request, read_json)
    with lock(root,'scanner'):
        for job in (root/'working').iterdir():
            if job.is_dir(): move_job(job,root,'interrupted')
        # A restart must not cause a delayed, unexpected paper feed.
        stale=take_scan_request(root)
        if stale: atomic_json(root/'last-request.json',stale | dict(result='Neustart: Startauftrag verworfen.'))
        worker_status(root,state='offline',message='Scanner wird gesucht.')
        device=None;latched=False;last_caps=None
        while True:
            try:
                if not device: device=detect_device(cfg)
                controls=load_control(root,cfg)
                profile=controls['profiles'][controls['active']]
                refresh=root/'refresh-request.json'
                if last_caps!=profile or refresh.exists():
                    query_profile=profile
                    if refresh.exists():
                        requested=read_json(refresh,{})
                        refresh.unlink()
                        query_profile=requested.get('profile',profile)
                    worker_status(root,state='checking',message='Geräteoptionen werden geprüft.')
                    capabilities=query_capabilities(device,query_profile)
                    capabilities['updated']=time.time()
                    atomic_json(root/'capabilities.json',capabilities)
                    last_caps=profile
                pressed=read_button(device)
                with lock(root,'control'):
                    request=read_json(root/'scan-request.json',None)
                    if request is not None:
                        (root/'scan-request.json').unlink();sync_dir(root)
                    if request or (pressed and not latched):
                        worker_status(root,state='scanning',message='Scan läuft. Bitte Papierdurchlauf abwarten.')
                    else:
                        worker_status(root,state='ready',message='Bereit für einen neuen Stapel.')
                if request or (pressed and not latched):
                    latched=bool(pressed)
                    if request and time.time()-request['created']>30:
                        raise RuntimeError('Startauftrag ist abgelaufen. Bitte erneut starten.')
                    selected=request['profile'] if request else profile
                    try:
                        live=query_capabilities(device,selected)  # Validate live, after dependent mode changes.
                        scan_once(effective_config(cfg,selected,live['options']),root,device)
                        if request: atomic_json(root/'last-request.json',request | dict(result='Scan beendet; Warteschlange prüfen.'))
                    except Exception:
                        if request: atomic_json(root/'last-request.json',request | dict(result='Scan fehlgeschlagen; Journal prüfen.'))
                        raise
                    worker_status(root,state='ready',message='Scan beendet. Upload erfolgt automatisch.')
                    time.sleep(2)
                elif not pressed: latched=False
                time.sleep(cfg['poll_seconds'])
            except Exception as error:
                detail=str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Lokaler Fehler ('+type(error).__name__+'); Journal prüfen.'
                detail=detail.replace('\n',' ')[:400]
                LOG.warning('Scanner/Profil nicht bereit: %s',detail)
                worker_status(root,state='offline',message=detail)
                device=None;last_caps=None
                time.sleep(5)


def api_call(cfg,endpoint,document=None):
    """Token passed through stdin config, never argv. No redirects or implicit POST retry."""
    url=cfg['paperless_url'].rstrip('/')+'/api/'+endpoint
    secret_config='header = "Authorization: Token '+cfg['paperless_token']+'"\n'
    with tempfile.TemporaryDirectory(prefix='ix500-http-') as temporary:
        response=Path(temporary)/'response'
        cmd=['curl','-q','--config','-','--silent','--show-error','--connect-timeout','10',
             '--max-time','120','--proto','=http,https','--output',str(response),
             '--write-out','%{http_code}',url]
        if cfg.get('ca_bundle'): cmd+=['--cacert',cfg['ca_bundle']]
        if document:
            cmd+=['--form',f'document=@{document};type=application/pdf;filename={document.parent.name}.pdf']
        try:
            proc=subprocess.run(cmd,input=secret_config,text=True,capture_output=True,timeout=130)
        except subprocess.TimeoutExpired:
            return 0,0,None
        # Do not log stderr, server bodies or credentials; all may contain sensitive data.
        code=int(proc.stdout) if proc.stdout.isdigit() else 0
        try: body=json.loads(response.read_text())
        except (OSError,ValueError): body=None
        return proc.returncode,code,body


def task_uuid(body):
    if not isinstance(body,str): return None
    try: return str(uuid.UUID(body))
    except ValueError: return None


def upload_cycle(cfg,root):
    with lock(root,'uploader'):
        for job in (root/'inflight').iterdir():
            if job.is_dir():
                move_job(job,root,'uncertain')
                LOG.warning('Job %s: unterbrochener POST, manuell prüfen.',job.name)
        # Only GET may be automatically retried after an ambiguous response.
        for job in sorted((root/'submitted').iterdir()):
            if not job.is_dir(): continue
            task=json.loads((job/'receipt.json').read_text())['task_id']
            rc,code,body=api_call(cfg,'tasks/?task_id='+quote(task,safe=''))
            if rc or code!=200: continue
            rows=body.get('results',[]) if isinstance(body,dict) else body
            if not isinstance(rows,list): continue
            row=next((row for row in rows if isinstance(row,dict) and row.get('task_id')==task),None)
            if not row: continue
            status=row.get('status')
            if status in ('SUCCESS','FAILURE'):
                atomic_json(job/'result.json',dict(task_id=task,status=status,document_id=row.get('related_document')))
                move_job(job,root,'sent' if status=='SUCCESS' else 'failed')
                LOG.info('Job %s: Paperless %s.',job.name,status)
        for job in sorted((root/'pending').iterdir()):
            if not job.is_dir(): continue
            job=move_job(job,root,'inflight')
            try:
                rc,code,body=api_call(cfg,'documents/post_document/',job/'document.pdf')
                task=task_uuid(body) if not rc and code==200 else None
                if task:
                    atomic_json(job/'receipt.json',dict(task_id=task,accepted_at=datetime.now(timezone.utc).isoformat()))
                    move_job(job,root,'submitted')
                    LOG.info('Job %s: Upload angenommen; Import wird geprüft.',job.name)
                elif rc in (5,6,7,35,60,77) and code==0:
                    # DNS/connect/TLS failures cannot have delivered an authenticated POST.
                    move_job(job,root,'pending')
                    LOG.warning('Paperless nicht erreichbar oder TLS-Prüfung fehlgeschlagen; späterer Versuch.')
                    break
                elif not rc and 400<=code<500:
                    atomic_json(job/'receipt.json',dict(http_status=code,reason='HTTP-Ablehnung'))
                    move_job(job,root,'failed')
                    LOG.warning('Job %s: HTTP %s; Einstellungen/Berechtigungen prüfen.',job.name,code)
                else:
                    atomic_json(job/'receipt.json',dict(http_status=code,curl_status=rc,reason='POST-Ergebnis unklar'))
                    move_job(job,root,'uncertain')
                    LOG.warning('Job %s: Upload-Ergebnis unklar; vor Wiederholung Paperless prüfen.',job.name)
            except Exception:
                if job.exists(): move_job(job,root,'uncertain')
                raise


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('daemon','scan','upload','check','status'))
    parser.add_argument('--config',default='/etc/ix500-paperless/config.json')
    parser.add_argument('--state',type=Path,default=Path('/var/lib/ix500-paperless'))
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:
        cfg=load_config(args.config)
        if args.command=='daemon': daemon(cfg,args.state)
        elif args.command=='upload': upload_cycle(cfg,args.state)
        elif args.command=='scan':
            with lock(args.state,'scanner'):
                from control import load_control, effective_config, query_capabilities
                settings=load_control(args.state,cfg)
                profile=settings['profiles'][settings['active']]
                device=detect_device(cfg)
                live=query_capabilities(device,profile)
                scan_once(effective_config(cfg,profile,live['options']),args.state,device)
        elif args.command=='status':
            prepare(args.state)
            for state in STATES: print(state, sum(p.is_dir() for p in (args.state/state).iterdir()))
        else:
            device=detect_device(cfg)
            read_button(device)
            options=run_scanimage(['--device-name',device,'--help']).stdout
            if 'ADF Duplex' not in options: raise RuntimeError('ADF Duplex nicht verfügbar.')
            rc,code,body=api_call(cfg,'documents/?page_size=1')
            if rc or code!=200 or not isinstance(body,dict) or 'results' not in body:
                raise RuntimeError(f'Paperless-API-Prüfung fehlgeschlagen (HTTP {code}, curl {rc}).')
            print('USB-iX500, Tastensensor, Duplex und Paperless-Lesezugriff erkannt. Uploadrecht separat mit Testscan prüfen.')
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        LOG.error('Aktion fehlgeschlagen. Konfiguration, Gerätezugriff, Journal und lokale Jobs prüfen.')
        return 1

if __name__=='__main__': sys.exit(main())
