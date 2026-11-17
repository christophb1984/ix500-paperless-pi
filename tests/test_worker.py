"""Real daemon + native query subprocess + fake USB, via the real web API."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from werkzeug.security import generate_password_hash
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import appliance as a
import control as c
import webapp

class WorkerIntegrationTests(unittest.TestCase):
    def test_browser_and_button_share_the_worker_and_keep_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);root=base/'state';a.prepare(root)
            fixture=base/'fixture';fixture.mkdir();button=fixture/'button';blank_back=fixture/'blank-back'
            (fixture/'sane.py').write_text('from test_sane_options import MethodCollisionDevice as FakeDevice\ndef init(): pass\ndef exit(): pass\ndef open(name): return FakeDevice()\n')
            scanner=fixture/'scanimage'
            scanner.write_text('#!'+sys.executable+'\n'+'''import os,sys
from pathlib import Path
from PIL import Image
args=sys.argv[1:]
if '--all-options' in args:
    print(' --scan[=(yes|no)] ['+('yes' if Path(os.environ['FAKE_BUTTON']).exists() else 'no')+']')
else:
    source=args[args.index('--source')+1]
    pattern=next(arg.split('=',1)[1] for arg in args if arg.startswith('--batch='))
    for i in range(1,2 if source!='ADF Duplex' else 3):
        Image.new('RGB',(80,100),'white' if i%2==0 and Path(os.environ['FAKE_BLANK_BACK']).exists() else 'black').save(pattern % i)
''');scanner.chmod(0o755)
            cfg=a.DEFAULTS | dict(paperless_url='http://localhost:8000',paperless_token='secret',allow_http=True,
                                device='fujitsu:ScanSnap iX500:fake',poll_seconds=.5)
            config=base/'config.json';config.write_text(json.dumps(cfg))
            env=os.environ | dict(PATH=str(fixture)+os.pathsep+os.environ['PATH'],
                 PYTHONPATH=str(fixture)+os.pathsep+str(ROOT/'tests'),FAKE_BUTTON=str(button),FAKE_BLANK_BACK=str(blank_back))
            log=(base/'worker.log').open('w')
            proc=subprocess.Popen([sys.executable,str(ROOT/'src/appliance.py'),'daemon','--config',str(config),'--state',str(root)],
                                  env=env,stdout=log,stderr=log,start_new_session=True)
            def wait_for(condition,timeout=18):
                deadline=time.monotonic()+timeout
                while time.monotonic()<deadline:
                    if condition(): return
                    if proc.poll() is not None: break
                    time.sleep(.1)
                self.fail('Worker did not reach expected state: '+(base/'worker.log').read_text())
            try:
                wait_for(lambda:c.read_json(root/'control-status.json',{}).get('state')=='ready')
                app=webapp.create_app(config,root,dict(secret_key='test',password_hash=generate_password_hash('test-password',method='pbkdf2:sha256:1000')))
                client=app.test_client();token=client.get('/api/session').json['csrf']
                login=client.post('/api/login',json={'password':'test-password'},headers={'X-CSRF-Token':token})
                token=login.json['csrf'];headers={'X-CSRF-Token':token}
                # Browser request is simplex, but the active button profile remains duplex.
                profile=c.profile_from_config(cfg);profile['source']='ADF Front'
                result=client.post('/api/scan',json={'profile':profile},headers=headers)
                self.assertEqual(result.status_code,202)
                wait_for(lambda:len(list((root/'pending').iterdir()))==1)
                first=next((root/'pending').iterdir())
                self.assertEqual(json.loads((first/'scan.json').read_text())['pages'],1)
                self.assertEqual(json.loads((first/'profile.json').read_text())['source'],'ADF Front')
                # Refresh an unsaved simplex draft; it must not change the hardware profile.
                client.post('/api/refresh',json={'profile':profile},headers=headers)
                wait_for(lambda:c.read_json(root/'capabilities.json',{}).get('profile',{}).get('source')=='ADF Front')
                button.touch()
                wait_for(lambda:len(list((root/'pending').iterdir()))==2)
                second=next(p for p in (root/'pending').iterdir() if p!=first)
                self.assertEqual(json.loads((second/'scan.json').read_text())['pages'],2)
                self.assertEqual(json.loads((second/'profile.json').read_text())['source'],'ADF Duplex')
                time.sleep(3)
                self.assertEqual(len(list((root/'pending').iterdir())),2)
                # Auto still commands physical duplex; the blank backside is then removed.
                button.unlink();blank_back.touch()
                auto=profile | dict(source='Auto',blank_percent=0.1)
                response=client.post('/api/scan',json={'profile':auto},headers=headers)
                self.assertEqual(response.status_code,202)
                wait_for(lambda:len(list((root/'pending').iterdir()))==3)
                third=next(p for p in (root/'pending').iterdir() if p not in (first,second))
                record=json.loads((third/'scan.json').read_text())
                self.assertEqual((record['pages'],record['kept']),(2,1))
                self.assertEqual(json.loads((third/'profile.json').read_text())['source'],'Auto')
                self.assertTrue((third/'original.pdf').exists())
            finally:
                os.killpg(proc.pid,signal.SIGTERM)
                proc.wait(timeout=5);log.close()

if __name__=='__main__': unittest.main()
