import json
from pathlib import Path
import sys
import tempfile
import unittest
from werkzeug.security import generate_password_hash
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
try: import webapp as w
except ImportError: w=None
import appliance as a
import control as c

class WebTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(w,'web app missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);a.prepare(self.root)
        self.cfg=a.DEFAULTS | dict(paperless_url='http://localhost:8000',paperless_token='NEVER_EXPOSE_ME',allow_http=True)
        self.path=self.root/'private-config.json';self.path.write_text(json.dumps(self.cfg))
        auth=dict(password_hash=generate_password_hash('testing-password',method='pbkdf2:sha256:1000'),secret_key='test-only-secret')
        self.app=w.create_app(self.path,self.root,auth);self.app.config['TESTING']=True
        self.client=self.app.test_client()
        self.csrf=self.client.get('/api/session').get_json()['csrf']
    def post(self,path,data,token=True):
        return self.client.post(path,json=data,headers={'X-CSRF-Token':self.csrf} if token else {})
    def login(self):
        self.assertEqual(self.post('/api/login',{'password':'testing-password'}).status_code,200)
        self.csrf=self.client.get('/api/session').get_json()['csrf']
    def test_login_required_and_credentials_never_leak(self):
        self.assertEqual(self.client.get('/api/state').status_code,401)
        self.assertEqual(self.post('/api/login',{'password':'wrong'}).status_code,401)
        self.login()
        response=self.client.get('/api/state')
        self.assertEqual(response.status_code,200)
        self.assertNotIn(b'NEVER_EXPOSE_ME',response.data)
        self.assertNotIn(b'paperless_token',response.data)
    def test_csrf_and_cross_origin_cannot_start_or_change(self):
        self.login();c.worker_status(self.root,state='ready',message='Bereit')
        p=c.profile_from_config(self.cfg)
        self.assertEqual(self.post('/api/scan',{'profile':p},token=False).status_code,403)
        response=self.client.post('/api/scan',json={'profile':p},headers={'X-CSRF-Token':self.csrf,'Origin':'http://evil.example'})
        self.assertEqual(response.status_code,403)
        self.assertFalse((self.root/'scan-request.json').exists())
    def test_profile_persists_and_browser_scan_queues_once(self):
        self.login();p=c.profile_from_config(self.cfg);p['source']='ADF Front'
        self.assertEqual(self.post('/api/profile',{'name':'Einseitig','profile':p}).status_code,200)
        c.worker_status(self.root,state='ready',message='Bereit')
        self.assertEqual(self.post('/api/scan',{'profile':p}).status_code,202)
        self.assertEqual(self.post('/api/scan',{'profile':p}).status_code,409)
        self.assertEqual(c.take_scan_request(self.root)['profile']['source'],'ADF Front')
    def test_invalid_values_and_credential_injection_are_rejected(self):
        self.login();p=c.profile_from_config(self.cfg)
        for change in ({'dpi':900},{'paperless_token':'replace'},{'sane_options':{'swskip':20}}):
            with self.subTest(change=change):
                self.assertEqual(self.post('/api/profile',{'name':'Bad','profile':p|change}).status_code,400)
        self.assertFalse((self.root/'control.json').exists())
    def test_malformed_csrf_is_rejected_without_server_error(self):
        response=self.client.post('/api/login',json={'password':'wrong'},headers={'X-CSRF-Token':'ä'})
        self.assertEqual(response.status_code,403)
    def test_invalid_profile_identifier_is_a_client_error(self):
        self.login()
        self.assertEqual(self.post('/api/activate',{'name':['invalid']}).status_code,400)
    def test_logout_invalidates_session(self):
        self.login();self.assertEqual(self.post('/api/logout',{}).status_code,200)
        self.assertEqual(self.client.get('/api/state').status_code,401)
    def test_brute_force_is_limited(self):
        for _ in range(10): self.post('/api/login',{'password':'wrong'})
        self.assertEqual(self.post('/api/login',{'password':'testing-password'}).status_code,429)
    def test_login_page_loads_local_assets_and_headers(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'ScanSnap',response.data)
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        for asset in ('app.js','style.css'):
            with self.client.get('/static/'+asset) as response:
                self.assertEqual(response.status_code,200)

if __name__=='__main__': unittest.main()
