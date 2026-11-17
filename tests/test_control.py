import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
try: import control as c
except ImportError: c=None
import appliance as a

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cfg=a.DEFAULTS | dict(paperless_url='http://localhost:8000',paperless_token='secret',allow_http=True)
    def test_profile_never_contains_credentials(self):
        self.assertIsNotNone(c,'control module missing')
        p=c.profile_from_config(self.cfg)
        self.assertNotIn('paperless_token',p)
        for key in ('paperless_token','device','command'):
            with self.assertRaises(ValueError): c.validate_profile(dict(p,**{key:'injected'}))
    def test_profile_save_and_active_config_survive_reload(self):
        self.assertIsNotNone(c,'control module missing')
        p=c.profile_from_config(self.cfg);p['source']='ADF Front';p['dpi']=300
        c.save_profile(self.root,self.cfg,'Briefe',p)
        state=c.load_control(self.root,self.cfg)
        self.assertEqual(state['active'],'Briefe')
        self.assertEqual(state['profiles']['Briefe']['source'],'ADF Front')
        self.assertEqual(c.effective_config(self.cfg,p)['paperless_token'],'secret')
    def test_start_snapshot_and_no_double_start(self):
        self.assertIsNotNone(c,'control module missing')
        p=c.profile_from_config(self.cfg)
        c.worker_status(self.root,state='ready',message='Bereit')
        c.submit_scan(self.root,p)
        p['dpi']=600
        self.assertEqual(json.loads((self.root/'scan-request.json').read_text())['profile']['dpi'],200)
        with self.assertRaises(RuntimeError): c.submit_scan(self.root,p)
    def test_offline_or_stale_worker_cannot_start(self):
        self.assertIsNotNone(c,'control module missing')
        p=c.profile_from_config(self.cfg)
        with self.assertRaises(RuntimeError): c.submit_scan(self.root,p)
        c.worker_status(self.root,state='ready',message='Bereit')
        status=json.loads((self.root/'control-status.json').read_text());status['updated']=time.time()-100
        a.atomic_json(self.root/'control-status.json',status)
        with self.assertRaises(RuntimeError): c.submit_scan(self.root,p)
    def test_native_options_are_constrained_and_cannot_override_pipeline(self):
        self.assertIsNotNone(c,'control module missing')
        p=c.profile_from_config(self.cfg)
        caps=[dict(name='contrast',kind='integer',active=True,editable=True,range=[-127,127,1]),
              dict(name='swcrop',kind='boolean',active=True,editable=True)]
        good=dict(p,sane_options={'contrast':10,'swcrop':True})
        c.validate_profile(good,caps)
        for options in ({'contrast':128},{'contrast':'10'},{'swcrop':'yes'},{'output-file':'/tmp/x'},{'swskip':20}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                c.validate_profile(dict(p,sane_options=options),caps)
    def test_native_command_order_follows_live_backend(self):
        self.assertIsNotNone(c)
        p=c.profile_from_config(self.cfg)
        p['sane_options']={'gamma-table':[0,255],'custom-gamma':True}
        caps=[dict(name='custom-gamma',kind='boolean',active=True,editable=True),dict(name='gamma-table',kind='vector',scalar='integer',count=2,range=[0,255,1],active=True,editable=True)]
        cfg=c.effective_config(self.cfg,p,caps)
        self.assertEqual(list(cfg['sane_options']),['custom-gamma','gamma-table'])
    def test_auto_mode_validates_as_duplex_and_requires_filter(self):
        p=c.profile_from_config(self.cfg) | dict(source='Auto',blank_percent=0.1)
        c.validate_profile(p,[dict(name='source',kind='text',active=True,choices=['ADF Front','ADF Duplex'])])
        self.assertEqual(c.backend_source(p),'ADF Duplex')
        with self.assertRaises(ValueError): c.validate_profile(p | dict(blank_percent=0))
    def test_auto_keeps_printed_front_and_removes_blank_back(self):
        from PIL import Image
        from pypdf import PdfReader
        job=self.root/'working'/'auto';job.mkdir(parents=True)
        Image.new('RGB',(100,100),'black').save(job/'page-0001.tiff')
        Image.new('RGB',(100,100),'white').save(job/'page-0002.tiff')
        a.finish_scan(job,self.cfg | dict(source='Auto',blank_percent=0.1),self.root,0)
        self.assertEqual(len(PdfReader(self.root/'pending/auto/document.pdf').pages),1)
        self.assertEqual(len(PdfReader(self.root/'pending/auto/original.pdf').pages),2)
    def test_safe_native_error_reaches_caller_without_unstructured_stderr(self):
        import subprocess
        from unittest.mock import patch
        result=subprocess.CompletedProcess([],1,'','private native debug noise\nIX500_OPTION_ERROR {"error":"page-width: Wert liegt außerhalb des Gerätebereichs."}\n')
        with patch('subprocess.run',return_value=result):
            with self.assertRaises(RuntimeError) as raised:
                c.query_capabilities('fujitsu:ScanSnap iX500:test',c.profile_from_config(self.cfg))
        self.assertIn('page-width',str(raised.exception))
        self.assertNotIn('private native debug noise',str(raised.exception))
    def test_simplex_odd_page_is_valid_but_duplex_is_not(self):
        from PIL import Image
        for source,target in [('ADF Front','pending'),('ADF Duplex','interrupted'),('Auto','interrupted')]:
            with self.subTest(source=source):
                job=self.root/'working'/source;job.mkdir(parents=True)
                Image.new('RGB',(80,100),'black').save(job/'page-0001.tiff')
                a.finish_scan(job,self.cfg | dict(source=source),self.root,0)
                self.assertTrue((self.root/target/source).exists())

if __name__=='__main__': unittest.main()
