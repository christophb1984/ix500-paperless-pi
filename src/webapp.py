#!/usr/bin/env python3
"""Authenticated LAN UI. All USB work stays in the scanner service."""
import argparse
from datetime import timedelta
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from flask import Flask, abort, jsonify, render_template, request, session
from werkzeug.security import check_password_hash
import appliance as a
import control as c


def create_app(config_path,state,auth):
    app=Flask(__name__)
    app.config.update(SECRET_KEY=auth['secret_key'],SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=bool(auth.get('public_origin','').startswith('https://')),SESSION_COOKIE_NAME='ix500_session',PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
                      MAX_CONTENT_LENGTH=256*1024)
    state=Path(state);a.prepare(state)
    attempts={};mutex=threading.Lock()
    def config(): return a.load_config(config_path)
    def payload():
        data=request.get_json()
        if not isinstance(data,dict): raise ValueError('JSON-Objekt erwartet.')
        return data
    def checked_profile(data):
        profile=data.get('profile')
        c.validate_profile(profile)
        caps=c.read_json(state/'capabilities.json',{})
        if profile['sane_options'] and not caps:
            raise ValueError('Geräteoptionen zuerst aktualisieren.')
        if caps:
            # Dependent options are checked live by the worker again before paper feed.
            c.validate_profile(profile,caps.get('options',[]))
        return profile
    @app.before_request
    def protect():
        if request.method=='POST':
            origin=request.headers.get('Origin')
            if origin and origin not in (request.host_url.rstrip('/'),auth.get('public_origin')): abort(403)
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token','').encode('utf-8'),session.get('csrf','_missing_').encode('utf-8')): abort(403)
        if request.path.startswith('/api/') and request.path not in ('/api/session','/api/login') and not session.get('authenticated'):
            abort(401)
    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'same-origin','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response
    @app.errorhandler(ValueError)
    def invalid(error): return jsonify(error=str(error)),400
    @app.errorhandler(RuntimeError)
    def busy(error): return jsonify(error=str(error)),409
    for code in (400,401,403,404,405,413,415,429):
        app.register_error_handler(code,lambda error:(jsonify(error={401:'Bitte anmelden.',403:'Sitzung ungültig. Seite neu laden.',429:'Zu viele Versuche. Bitte fünf Minuten warten.'}.get(error.code,'Anfrage nicht möglich.')),error.code))
    @app.get('/')
    def index(): return render_template('index.html')
    @app.get('/api/session')
    def current_session():
        if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
        return jsonify(authenticated=bool(session.get('authenticated')),csrf=session['csrf'])
    @app.post('/api/login')
    def login():
        password=payload().get('password')
        if not isinstance(password,str) or len(password)>256: abort(401)
        address=request.remote_addr or 'unknown';now=time.monotonic()
        with mutex:
            recent=[t for t in attempts.get(address,[]) if now-t<300]
            if len(recent)>=10: abort(429)
            if len(attempts)>256: attempts.clear()
            attempts[address]=recent+[now]
        if not check_password_hash(auth['password_hash'],password): abort(401)
        with mutex: attempts.pop(address,None)
        session.clear();session.update(authenticated=True,csrf=secrets.token_urlsafe(32));session.permanent=True
        return jsonify(ok=True,csrf=session['csrf'])
    @app.post('/api/logout')
    def logout(): session.clear();return jsonify(ok=True)
    @app.get('/api/state')
    def snapshot(): return jsonify(c.public_state(state,config()))
    @app.post('/api/profile')
    def profile_save():
        data=payload();profile=checked_profile(data)
        c.save_profile(state,config(),data.get('name'),profile)
        return jsonify(ok=True)
    @app.post('/api/activate')
    def profile_activate():
        name=payload().get('name');cfg=config()
        settings=c.load_control(state,cfg)
        if not isinstance(name,str) or name not in settings['profiles']: raise ValueError('Profil nicht gefunden.')
        c.save_profile(state,cfg,name,settings['profiles'][name]);return jsonify(ok=True)
    @app.post('/api/scan')
    def scan():
        profile=checked_profile(payload())
        return jsonify(id=c.submit_scan(state,profile)),202
    @app.post('/api/refresh')
    def refresh():
        profile=payload().get('profile');c.validate_profile(profile)
        with a.lock(state,'control'):
            status=c.read_json(state/'control-status.json',{})
            if status.get('state')=='scanning': raise RuntimeError('Bitte laufenden Scan abwarten.')
            a.atomic_json(state/'refresh-request.json',dict(profile=profile))
        return jsonify(ok=True),202
    return app


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('/etc/ix500-paperless/config.json'))
    parser.add_argument('--state',type=Path,default=Path('/var/lib/ix500-paperless'))
    parser.add_argument('--auth',type=Path,default=Path('/etc/ix500-paperless/web.json'))
    args=parser.parse_args();auth=json.loads(args.auth.read_text())
    from waitress import serve
    serve(create_app(args.config,args.state,auth),host=auth.get('host','0.0.0.0'),port=auth.get('port',8080),
          threads=4,connection_limit=50,channel_timeout=30,max_request_body_size=256*1024)

if __name__=='__main__': main()
