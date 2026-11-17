"""Public scan profiles and the single-worker control channel (no credentials)."""
import copy
import json
import math
from pathlib import Path
import re
import time
import uuid
import appliance as a

PROFILE_DEFAULTS=dict(source='ADF Duplex',mode='Color',dpi=200,width_mm=210,height_mm=297,
                      blank_percent=0.0,blank_gray_threshold=180,jpeg_quality=90,sane_options={})
# These are owned by the PDF/scan pipeline, not arbitrary browser options.
MANAGED={'source','mode','resolution','page-width','page-height','tl-x','tl-y','br-x','br-y','swskip',
         'batch-scan','side','format','batch','output-file','device-name','help','test'}


def profile_from_config(cfg):
    return {k:copy.deepcopy(cfg.get(k,v)) for k,v in PROFILE_DEFAULTS.items()}


def backend_source(profile):
    return 'ADF Duplex' if profile['source']=='Auto' else profile['source']


def validate_value(value,option):
    kind=option['kind']
    if kind=='boolean':
        if not isinstance(value,bool): raise ValueError('Schalter erwartet.')
    elif kind in ('integer','number'):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Endliche Zahl erwartet.')
        if kind=='integer' and not isinstance(value,int): raise ValueError('Ganze Zahl erwartet.')
    elif kind=='text':
        if not isinstance(value,str) or len(value)>4096 or any(x in value for x in ('\0','\r','\n')):
            raise ValueError('Ungültiger Textwert.')
    elif kind=='vector':
        if not isinstance(value,list) or len(value)!=option['count'] or len(value)>4096:
            raise ValueError('Falsche Länge der Zahlentabelle.')
        scalar=option | {'kind':option.get('scalar','integer')}
        for item in value: validate_value(item,scalar)
        return
    else: raise ValueError('Diese Geräteoption ist nicht schreibbar.')
    if option.get('choices') is not None and value not in option['choices']:
        raise ValueError('Wert ist nicht in der Geräteauswahl.')
    if option.get('range'):
        low,high,step=option['range']
        if not low<=value<=high: raise ValueError('Wert liegt außerhalb des Gerätebereichs.')
        if step and abs((value-low)/step-round((value-low)/step))>0.0001:
            raise ValueError('Wert passt nicht zur Schrittweite des Geräts.')


def validate_profile(profile,capabilities=None):
    if not isinstance(profile,dict) or set(profile)!=set(PROFILE_DEFAULTS):
        raise ValueError('Profilfelder fehlen oder sind unbekannt.')
    if profile['source'] not in ('Auto','ADF Duplex','ADF Front','ADF Back'):
        raise ValueError('Ungültige Scanquelle.')
    if profile['mode'] not in ('Color','Gray','Lineart'): raise ValueError('Ungültiger Farbmodus.')
    for key,low,high,integer in [('dpi',100,600,True),('width_mm',50,216,False),('height_mm',50,356,False),
                                 ('blank_percent',0,1,False),('blank_gray_threshold',32,254,True),('jpeg_quality',40,100,True)]:
        validate_value(profile[key],dict(kind='integer' if integer else 'number',range=[low,high,0]))
    if profile['source']=='Auto' and profile['blank_percent']<=0:
        raise ValueError('Automatisch benötigt einen aktiven Leerseitenfilter (z. B. 0.1).')
    options=profile['sane_options']
    if not isinstance(options,dict) or len(options)>100: raise ValueError('Ungültige Geräteoptionen.')
    catalog={o['name']:o for o in capabilities or []}
    for name,value in options.items():
        if not re.fullmatch('[a-z][a-z0-9-]{0,63}',name) or name in MANAGED:
            raise ValueError('Reservierte oder ungültige Geräteoption.')
        if capabilities is not None:
            option=catalog.get(name)
            if not option or not option.get('editable') or not option.get('active'):
                raise ValueError('Geräteoption ist unbekannt oder im aktuellen Modus nicht aktiv: '+name)
            validate_value(value,option)
        elif not isinstance(value,(str,bool,int,float,list)):
            raise ValueError('Ungültiger Optionswert.')
    if capabilities is not None:
        for key,name in [('source','source'),('mode','mode'),('dpi','resolution')]:
            option=catalog.get(name)
            if option and option.get('active'): validate_value(backend_source(profile) if key=='source' else profile[key],option)


def effective_config(cfg,profile,capabilities=None):
    validate_profile(profile,capabilities)
    selected=copy.deepcopy(profile)
    if capabilities is not None:
        selected['sane_options']={o['name']:selected['sane_options'][o['name']] for o in capabilities if o['name'] in selected['sane_options']}
    return cfg | selected


def load_control(root,cfg):
    path=root/'control.json'
    if path.exists():
        data=json.loads(path.read_text())
        if not isinstance(data.get('profiles'),dict) or data.get('active') not in data['profiles']:
            raise ValueError('Profilablage ist beschädigt.')
        for profile in data['profiles'].values(): validate_profile(profile)
        return data
    return dict(active='Standard',profiles={'Standard':profile_from_config(cfg)})


def save_profile(root,cfg,name,profile):
    validate_profile(profile)
    if not isinstance(name,str) or not name.strip() or len(name)>60 or any(ord(c)<32 for c in name):
        raise ValueError('Profilname muss 1–60 sichtbare Zeichen enthalten.')
    with a.lock(root,'control'):
        data=load_control(root,cfg)
        if name not in data['profiles'] and len(data['profiles'])>=30: raise ValueError('Maximal 30 Profile.')
        data['profiles'][name]=copy.deepcopy(profile);data['active']=name
        a.atomic_json(root/'control.json',data)


def read_json(path,default):
    try: return json.loads(path.read_text())
    except FileNotFoundError: return copy.deepcopy(default)


def worker_status(root,**data):
    a.prepare(root)
    previous=read_json(root/'control-status.json',{})
    if {k:v for k,v in previous.items() if k!='updated'}==data and time.time()-previous.get('updated',0)<5:
        return  # Heartbeat every five seconds, avoiding an fsync on every idle button poll.
    a.atomic_json(root/'control-status.json',dict(updated=time.time(),**data))


def submit_scan(root,profile):
    validate_profile(profile)
    with a.lock(root,'control'):
        status=read_json(root/'control-status.json',{})
        if status.get('state')!='ready' or time.time()-status.get('updated',0)>15:
            raise RuntimeError('Scanner nicht bereit. Gerät aufklappen und Status prüfen.')
        if (root/'scan-request.json').exists(): raise RuntimeError('Ein Scanstart wartet bereits.')
        request=dict(id=uuid.uuid4().hex,created=time.time(),profile=copy.deepcopy(profile))
        a.atomic_json(root/'scan-request.json',request)
        return request['id']


def take_scan_request(root):
    with a.lock(root,'control'):
        path=root/'scan-request.json'
        request=read_json(path,None)
        if request is not None:
            path.unlink();a.sync_dir(root)
        return request


def query_capabilities(device,profile):
    import subprocess,sys
    result=subprocess.run([sys.executable,str(Path(__file__).with_name('sane_options.py'))],
        input=json.dumps(dict(device=device,profile=profile)),capture_output=True,text=True,timeout=25)
    if result.returncode:
        for line in result.stderr.splitlines():
            if line.startswith('IX500_OPTION_ERROR '):
                try: detail=json.loads(line[len('IX500_OPTION_ERROR '):]).get('error')
                except (ValueError,AttributeError): continue
                if isinstance(detail,str): raise RuntimeError('Geräteeinstellungen: '+detail[:400])
        raise RuntimeError('Geräteoptionen konnten nicht angewandt werden. Profil/Modus prüfen.')
    return json.loads(result.stdout)


def public_state(root,cfg):
    data=load_control(root,cfg)
    status=read_json(root/'control-status.json',dict(state='offline',message='Scandienst noch nicht bereit.',updated=0))
    if status['state']!='scanning' and time.time()-status.get('updated',0)>15:
        status.update(state='offline',message='Scandienst nicht erreichbar.')
    return dict(settings=data,worker=status,capabilities=read_json(root/'capabilities.json',{}),
                queued=(root/'scan-request.json').exists(),
                jobs={state:sum(p.is_dir() for p in (root/state).iterdir()) if (root/state).exists() else 0 for state in a.STATES},
                free_mb=__import__('shutil').disk_usage(root).free//1024**2)
