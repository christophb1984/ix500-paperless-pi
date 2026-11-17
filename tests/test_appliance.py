"""Behavioral tests; scanner boundary is fake, PDF and HTTP paths are real."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('appliance', ROOT / 'src/appliance.py')
a = importlib.util.module_from_spec(spec)
if spec.loader and (ROOT / 'src/appliance.py').exists():
    spec.loader.exec_module(a)

class Handler(BaseHTTPRequestHandler):
    response_code = 200
    malformed = False
    task_status = 'SUCCESS'
    requests = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        data = self.rfile.read(int(self.headers['Content-Length']))
        type(self).requests.append((self.path, self.headers.get('Authorization'), data))
        self.send_response(type(self).response_code)
        self.end_headers()
        self.wfile.write(b'not-a-task' if type(self).malformed else b'"12345678-1234-1234-1234-123456789abc"')
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps([{'task_id':'12345678-1234-1234-1234-123456789abc', 'status':type(self).task_status, 'related_document':'42'}]).encode())

class ApplianceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = dict(paperless_url='http://127.0.0.1:1/paperless', paperless_token='secret-value', allow_http=True,
                        device='', mode='Color', dpi=200, width_mm=210, height_mm=297,
                        blank_percent=0.05, poll_seconds=1, scan_timeout=120, min_free_mb=1)
        Handler.response_code, Handler.malformed, Handler.task_status = 200, False, 'SUCCESS'
        Handler.requests = []
    def tearDown(self):
        self.tmp.cleanup()
    def page(self, path, blank=False):
        im = Image.new('RGB', (400,600), 'white')
        if not blank:
            ImageDraw.Draw(im).rectangle((50,50,300,100), fill='black')
        im.save(path, dpi=(200,200))
    def server(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.cfg['paperless_url'] = f'http://127.0.0.1:{server.server_port}/paperless'
    def pending(self):
        job = self.root/'pending'/'job'
        job.mkdir(parents=True)
        (job/'document.pdf').write_bytes(b'%PDF-1.4\nTEST')
        return job
    def test_config_rejects_secret_in_url_and_invalid_ranges(self):
        self.assertTrue(hasattr(a,'validate_config'), 'configuration validator is missing')
        a.validate_config(self.cfg)
        for key,value in [('paperless_url','https://user:pass@host'),('paperless_token','abc\nInjected'),('dpi',0),('blank_percent',5),('mode','evil'),('allow_http',False)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                a.validate_config(dict(self.cfg, **{key:value}))
    def test_button_options_parse_and_missing_sensor_is_error(self):
        self.assertTrue(hasattr(a,'button_state'), 'button parser is missing')
        self.assertTrue(a.button_state('  --scan[=(yes|no)] [yes] [hardware]\n'))
        self.assertFalse(a.button_state('  --scan[=(yes|no)] [no] [hardware]\n'))
        with self.assertRaises(ValueError): a.button_state('--resolution 300')
    def test_pdf_keeps_order_and_original_for_removed_backside(self):
        self.assertTrue(hasattr(a,'make_pdf'), 'PDF processor is missing')
        job=self.root/'job'; job.mkdir()
        self.page(job/'page-0001.tiff'); self.page(job/'page-0002.tiff', blank=True)
        result = a.make_pdf(job,self.cfg)
        self.assertEqual(result, (2,1))
        self.assertEqual(len(PdfReader(job/'document.pdf').pages),1)
        self.assertEqual(len(PdfReader(job/'original.pdf').pages),2)
    def test_all_blank_produces_no_upload_pdf_and_preserves_original(self):
        self.assertTrue(hasattr(a,'make_pdf'), 'PDF processor is missing')
        job=self.root/'job';job.mkdir()
        self.page(job/'page-0001.tiff',True);self.page(job/'page-0002.tiff',True)
        self.assertEqual(a.make_pdf(job,self.cfg),(2,0))
        self.assertFalse((job/'document.pdf').exists())
        self.assertEqual(len(PdfReader(job/'original.pdf').pages),2)
    def test_partial_scan_never_enters_upload_queue(self):
        self.assertTrue(hasattr(a,'finish_scan'), 'scan finalizer is missing')
        job=self.root/'working'/'job';job.mkdir(parents=True)
        self.page(job/'page-0001.tiff')
        a.finish_scan(job,self.cfg,self.root,6)
        self.assertTrue((self.root/'interrupted'/'job'/'page-0001.tiff').exists())
        self.assertFalse((self.root/'pending'/'job').exists())
    def test_full_duplex_enters_pending(self):
        self.assertTrue(hasattr(a,'finish_scan'), 'scan finalizer is missing')
        job=self.root/'working'/'job';job.mkdir(parents=True)
        self.page(job/'page-0001.tiff');self.page(job/'page-0002.tiff')
        a.finish_scan(job,self.cfg,self.root,0)
        self.assertEqual(len(PdfReader(self.root/'pending'/'job'/'document.pdf').pages),2)
    def test_upload_tracks_task_before_marking_sent(self):
        self.assertTrue(hasattr(a,'upload_cycle'), 'upload worker is missing')
        self.server();self.pending()
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'submitted'/'job'/'document.pdf').exists())
        path,auth,body=Handler.requests[0]
        self.assertEqual(path,'/paperless/api/documents/post_document/')
        self.assertEqual(auth,'Token secret-value')
        self.assertIn(b'name="document"',body)
        self.assertNotIn(b'name="created"',body)
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'sent'/'job'/'document.pdf').exists())
        self.assertEqual(len(Handler.requests),1)
    def test_unparseable_success_is_not_reposted(self):
        self.assertTrue(hasattr(a,'upload_cycle'), 'upload worker is missing')
        self.server();Handler.malformed=True;self.pending()
        a.upload_cycle(self.cfg,self.root);a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'uncertain'/'job'/'document.pdf').exists())
        self.assertEqual(len(Handler.requests),1)
    def test_rejected_upload_preserves_pdf(self):
        self.assertTrue(hasattr(a,'upload_cycle'), 'upload worker is missing')
        self.server();Handler.response_code=403;self.pending()
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'failed'/'job'/'document.pdf').exists())
    def test_restart_inflight_is_quarantined(self):
        self.assertTrue(hasattr(a,'upload_cycle'), 'upload worker is missing')
        self.pending().rename(self.root/'pending'/'tmp')
        (self.root/'inflight').mkdir()
        (self.root/'pending'/'tmp').rename(self.root/'inflight'/'job')
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'uncertain'/'job'/'document.pdf').exists())

    def test_connection_refused_stays_pending_for_retry(self):
        self.pending()
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'pending'/'job'/'document.pdf').exists())
        self.assertFalse((self.root/'uncertain'/'job').exists())
    def test_server_error_is_not_blindly_retried(self):
        self.server();Handler.response_code=500;self.pending()
        a.upload_cycle(self.cfg,self.root);a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'uncertain'/'job'/'document.pdf').exists())
        self.assertEqual(len(Handler.requests),1)
    def test_failure_in_paperless_retains_pdf(self):
        self.server();self.pending()
        a.upload_cycle(self.cfg,self.root)
        Handler.task_status='FAILURE'
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'failed'/'job'/'document.pdf').exists())
    def test_zero_status_with_half_duplex_is_quarantined(self):
        job=self.root/'working'/'job';job.mkdir(parents=True)
        self.page(job/'page-0001.tiff')
        a.finish_scan(job,self.cfg,self.root,0)
        self.assertTrue((self.root/'interrupted'/'job'/'page-0001.tiff').exists())
    def test_raw_images_are_removed_before_job_is_published(self):
        from unittest.mock import patch
        job=self.root/'working'/'job';job.mkdir(parents=True)
        self.page(job/'page-0001.tiff');self.page(job/'page-0002.tiff')
        move=a.move_job
        def observe(path,root,state):
            if state=='pending':
                self.assertFalse(list(path.glob('page-*.tiff')))
                self.assertTrue((path/'document.pdf').exists())
            return move(path,root,state)
        with patch.object(a,'move_job',observe): a.finish_scan(job,self.cfg,self.root,0)

    def test_real_scan_command_with_fake_usb_boundary(self):
        from unittest.mock import patch
        bin_dir=self.root/'bin';bin_dir.mkdir()
        scanner=bin_dir/'scanimage'
        scanner.write_text('#!'+sys.executable+'\n'+"""
import os,sys
from pathlib import Path
from PIL import Image
args=sys.argv[1:]
if '-L' in args:
    print("device `fujitsu:ScanSnap iX500:123' is a FUJITSU ScanSnap iX500 scanner")
elif '--all-options' in args:
    print('  --scan[=(yes|no)] [no] [hardware]')
else:
    assert args[args.index('--source')+1]=='ADF Duplex'
    assert args[args.index('--swskip')+1]=='0'
    assert '--batch-count=-1' in args
    pattern=next(v.split('=',1)[1] for v in args if v.startswith('--batch='))
    Image.new('RGB',(100,100),'red').save(pattern % 1)
    Image.new('RGB',(100,100),'blue').save(pattern % 2)
""")
        scanner.chmod(0o755)
        cfg=dict(self.cfg,blank_percent=0)
        with patch.dict(os.environ,{'PATH':str(bin_dir)+os.pathsep+os.environ['PATH']}):
            device=a.detect_device(cfg)
            self.assertFalse(a.read_button(device))
            a.scan_once(cfg,self.root,device)
        jobs=list((self.root/'pending').iterdir())
        self.assertEqual(len(jobs),1)
        pdf=PdfReader(jobs[0]/'document.pdf')
        self.assertEqual(len(pdf.pages),2)
        first=pdf.pages[0].images[0].image.getpixel((50,50))
        last=pdf.pages[1].images[0].image.getpixel((50,50))
        self.assertGreater(first[0],first[2])
        self.assertGreater(last[2],last[0])
    def test_token_is_not_exposed_in_curl_arguments(self):
        from unittest.mock import patch
        self.server();self.pending()
        bin_dir=self.root/'bin';bin_dir.mkdir()
        wrapper=bin_dir/'curl'
        argv_file=self.root/'curl-argv.json'
        wrapper.write_text('#!'+sys.executable+'\n'+
            'import json,os,sys\nfrom pathlib import Path\n'+
            'Path('+repr(str(argv_file))+').write_text(json.dumps(sys.argv))\n'+
            "os.execv('/usr/bin/curl',['curl',*sys.argv[1:]])\n")
        wrapper.chmod(0o755)
        with patch.dict(os.environ,{'PATH':str(bin_dir)+os.pathsep+os.environ['PATH']}):
            a.upload_cycle(self.cfg,self.root)
        self.assertNotIn('secret-value',argv_file.read_text())
        self.assertTrue((self.root/'submitted'/'job'/'receipt.json').exists())
    def test_empty_or_partial_output_is_never_uploaded(self):
        for name,partial in [('empty',False),('partial',True)]:
            with self.subTest(name=name):
                job=self.root/'working'/name;job.mkdir(parents=True,exist_ok=True)
                if partial:
                    self.page(job/'page-0001.tiff');self.page(job/'page-0002.tiff')
                    (job/'page-0003.tiff.part').write_bytes(b'partial')
                a.finish_scan(job,self.cfg,self.root,0)
                self.assertTrue((self.root/'interrupted'/name).exists())
                self.assertFalse((self.root/'pending'/name).exists())

    def test_timeout_preserves_completed_raw_page(self):
        from unittest.mock import patch
        bin_dir=self.root/'bin';bin_dir.mkdir()
        scanner=bin_dir/'scanimage'
        scanner.write_text('#!'+sys.executable+'\n'+"""
import sys,time
from PIL import Image
pattern=next(v.split('=',1)[1] for v in sys.argv if v.startswith('--batch='))
Image.new('RGB',(100,100),'white').save(pattern % 1)
time.sleep(10)
""")
        scanner.chmod(0o755)
        with patch.dict(os.environ,{'PATH':str(bin_dir)+os.pathsep+os.environ['PATH']}):
            a.scan_once(dict(self.cfg,scan_timeout=0.5),self.root,'fujitsu:ScanSnap iX500:123')
        jobs=list((self.root/'interrupted').iterdir())
        self.assertEqual(len(jobs),1)
        self.assertTrue((jobs[0]/'page-0001.tiff').exists())
        self.assertEqual(json.loads((jobs[0]/'scan.json').read_text())['status'],124)
        self.assertFalse(list((self.root/'pending').iterdir()))
    def test_scanning_requires_free_disk_reserve(self):
        with self.assertRaises(RuntimeError):
            a.scan_once(dict(self.cfg,min_free_mb=10**12),self.root,'fujitsu:ScanSnap iX500:123')
        self.assertFalse(list((self.root/'working').iterdir()))
    def test_pdf_failure_preserves_raw_pages(self):
        from unittest.mock import patch
        job=self.root/'working'/'job';job.mkdir(parents=True)
        self.page(job/'page-0001.tiff');self.page(job/'page-0002.tiff')
        with patch.object(a.img2pdf,'convert',side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError): a.finish_scan(job,self.cfg,self.root,0)
        self.assertEqual(len(list((self.root/'interrupted'/'job').glob('page-*.tiff'))),2)
        self.assertFalse((self.root/'pending'/'job').exists())
    def test_failed_task_lookup_keeps_submitted_without_reposting(self):
        self.server();self.pending()
        a.upload_cycle(self.cfg,self.root)
        self.cfg['paperless_url']='http://127.0.0.1:1/paperless'
        a.upload_cycle(self.cfg,self.root)
        self.assertTrue((self.root/'submitted'/'job'/'document.pdf').exists())
        self.assertEqual(len(Handler.requests),1)

    def test_light_showthrough_is_removed_but_real_print_is_kept(self):
        job=self.root/'job';job.mkdir()
        with Image.new('RGB',(400,600),'white') as im:
            ImageDraw.Draw(im).rectangle((20,20,350,550),fill=(220,220,220))
            im.save(job/'page-0001.tiff',dpi=(200,200))
        with Image.new('RGB',(400,600),'white') as im:
            ImageDraw.Draw(im).rectangle((50,50,300,100),fill=(165,165,165))
            im.save(job/'page-0002.tiff',dpi=(200,200))
        self.assertEqual(a.make_pdf(job,dict(self.cfg,blank_percent=0.1)),(2,1))
        self.assertEqual(len(PdfReader(job/'document.pdf').pages),1)
        self.assertEqual(len(PdfReader(job/'original.pdf').pages),2)
    def test_dark_pixel_threshold_is_validated(self):
        for value in (0,255,True,'180'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                a.validate_config(dict(self.cfg,blank_gray_threshold=value))

if __name__=='__main__': unittest.main()
