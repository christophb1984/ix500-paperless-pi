import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('setup_wizard',ROOT/'src/setup_wizard.py')
w=importlib.util.module_from_spec(spec)
if (ROOT/'src/setup_wizard.py').exists(): spec.loader.exec_module(w)

class SetupTests(unittest.TestCase):
    def test_wifi_keyfile_escapes_injection_and_hides_secrets_in_file_only(self):
        self.assertTrue(hasattr(w,'wifi_keyfile'),'keyfile generator missing')
        text=w.wifi_keyfile('Office\\SSID\n[wifi-security]','safe pass word','wlan0')
        self.assertIn('ssid=Office\\\\SSID\\n[wifi-security]',text)
        self.assertIn('psk=safe\\spass\\sword',text)
        self.assertEqual(text.count('\n[wifi-security]\n'),1)
    def test_host_and_user_validation(self):
        self.assertTrue(hasattr(w,'valid_hostname'),'hostname validator missing')
        self.assertTrue(w.valid_hostname('scan-pi'))
        for v in ('-bad','bad.abc','bad\nroot','a'*64): self.assertFalse(w.valid_hostname(v))
        self.assertTrue(w.valid_user('scanneradmin'))
        for v in ('root','ix500','-bad','bad user'): self.assertFalse(w.valid_user(v))
    def test_install_help_is_read_only(self):
        self.assertTrue((ROOT/'install.sh').exists(),'installer missing')
        result=subprocess.run(['bash',str(ROOT/'install.sh'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('--prepare-image',result.stdout)

    def test_update_help_is_read_only(self):
        result=subprocess.run(['bash',str(ROOT/'update.sh'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn('Retains Paperless credentials',result.stdout)

if __name__=='__main__': unittest.main()
