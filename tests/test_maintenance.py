import sys
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import appliance as a
import control as c
try: import maintenance as m
except ImportError: m=None

class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m,'maintenance guard missing')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);a.prepare(self.root);(self.root/'control.lock').touch()
    def test_no_new_browser_scan_can_enter_while_services_stop(self):
        c.worker_status(self.root,state='ready',message='Bereit')
        called=[]
        def stop():
            with self.assertRaises(RuntimeError): c.submit_scan(self.root,c.profile_from_config({}))
            self.assertFalse((self.root/'scan-request.json').exists())
            called.append(True)
        m.guarded_stop(self.root,stop)
        self.assertEqual(called,[True])
    def test_scan_already_committed_or_working_is_never_stopped(self):
        for state in ('scanning','working'):
            with self.subTest(state=state):
                c.worker_status(self.root,state='scanning' if state=='scanning' else 'ready',message='test')
                job=self.root/'working'/'job'
                if state=='working': job.mkdir()
                calls=[]
                with self.assertRaises(RuntimeError): m.guarded_stop(self.root,lambda:calls.append(True))
                self.assertEqual(calls,[])
                if job.exists(): job.rmdir()
    def test_missing_runtime_lock_is_not_created_as_root(self):
        (self.root/'control.lock').unlink()
        with self.assertRaises(FileNotFoundError): m.guarded_stop(self.root,lambda:self.fail('must not stop'))
        self.assertFalse((self.root/'control.lock').exists())
    def test_queued_request_is_retained_and_upgrade_refused(self):
        c.worker_status(self.root,state='ready',message='Bereit')
        c.submit_scan(self.root,c.profile_from_config({}))
        with self.assertRaises(RuntimeError): m.guarded_stop(self.root,lambda:self.fail('must not stop'))
        self.assertTrue((self.root/'scan-request.json').exists())

if __name__=='__main__': unittest.main()
