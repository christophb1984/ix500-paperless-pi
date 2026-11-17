import json
from pathlib import Path
import sys
import tempfile
import threading
import time
PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'src'),str(PROJECT/'tests')]
OUTPUT=PROJECT/'work'
OUTPUT.mkdir(exist_ok=True)
import appliance as a
import control as c
import webapp
from sane_options import describe_options
from test_sane_options import FakeDevice
from werkzeug.security import generate_password_hash
from waitress import create_server
from playwright.sync_api import sync_playwright

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);a.prepare(root)
    cfg=a.DEFAULTS | dict(paperless_url='http://localhost:8000',paperless_token='private-test-token',allow_http=True)
    path=root/'config.json';path.write_text(json.dumps(cfg))
    c.worker_status(root,state='ready',message='Bereit für einen neuen Stapel.')
    a.atomic_json(root/'capabilities.json',dict(options=describe_options(FakeDevice()),profile=c.profile_from_config(cfg),updated=time.time()))
    app=webapp.create_app(path,root,dict(secret_key='preview-only',password_hash=generate_password_hash('preview-password',method='pbkdf2:sha256:1000')))
    server=create_server(app,host='127.0.0.1',port=0,threads=4)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        with sync_playwright() as play:
            browser=play.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto('http://127.0.0.1:'+str(server.effective_port))
            page.get_by_label('Webpasswort',exact=True).fill('preview-password')
            page.get_by_role('button',name='Anmelden').click()
            page.get_by_role('heading',name='Papier & Qualität').wait_for()
            page.get_by_label('Seiten',exact=True).select_option('ADF Front')
            page.get_by_label('Profilname',exact=True).fill('Briefe einseitig')
            page.get_by_role('button',name='Profil speichern & aktivieren',exact=True).click()
            page.get_by_text('Profil gespeichert. Die blaue Taste nutzt jetzt diese Einstellungen.').wait_for()
            assert c.load_control(root,cfg)['profiles']['Briefe einseitig']['source']=='ADF Front'
            c.worker_status(root,state='ready',message='Bereit für einen neuen Stapel.')
            page.get_by_role('button',name='Scan starten').click()
            page.get_by_text('Scanstart angefordert.',exact=False).wait_for()
            assert json.loads((root/'scan-request.json').read_text())['profile']['source']=='ADF Front'
            (root/'scan-request.json').unlink()
            c.worker_status(root,state='ready',message='Bereit für einen neuen Stapel.')
            page.get_by_label('Seiten',exact=True).select_option('Auto')
            assert page.locator('#blank_percent').input_value()=='0.1'
            assert page.locator('#auto-help').is_visible()
            page.get_by_label('Profilname',exact=True).fill('Automatisch')
            page.get_by_role('button',name='Profil speichern & aktivieren',exact=True).click()
            page.get_by_text('Blaue Taste: Automatisch',exact=True).wait_for()
            assert c.load_control(root,cfg)['profiles']['Automatisch']['source']=='Auto'
            c.worker_status(root,state='ready',message='Bereit für einen neuen Stapel.')
            page.get_by_role('button',name='Scan starten').click()
            page.get_by_text('Scanstart angefordert.',exact=False).wait_for()
            assert json.loads((root/'scan-request.json').read_text())['profile']['source']=='Auto'
            (root/'scan-request.json').unlink()
            page.wait_for_timeout(3000)
            page.screenshot(path=str(OUTPUT/'web-desktop.png'),full_page=True)
            page.get_by_text('Erweiterte Geräteoptionen',exact=False).click()
            page.get_by_label('Option suchen',exact=True).fill('gamma')
            assert page.locator('.option:visible').count()>=2
            page.screenshot(path=str(OUTPUT/'web-options.png'),full_page=True)
            page.get_by_text('Erweiterte Geräteoptionen',exact=False).click()
            page.set_viewport_size({'width':390,'height':844})
            assert page.locator('.intro h1').inner_text()=='Vom Papier direkt zu Paperless.'
            page.screenshot(path=str(OUTPUT/'web-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
            assert not errors,errors
            assert 'private-test-token' not in page.content()
            print('Browser PASS: login, simplex and automatic profiles, auto filter default, save, scan queue, advanced options, 1440px and 390px, no JS errors or horizontal overflow.')
            browser.close()
    finally:
        from waitress import wasyncore
        # Close sockets on the event-loop thread, not across an active select().
        server.trigger.pull_trigger(lambda:wasyncore.close_all(map=server._map))
        thread.join(timeout=5)
        server.task_dispatcher.shutdown()
        assert not thread.is_alive(), 'Preview server did not shut down.'

