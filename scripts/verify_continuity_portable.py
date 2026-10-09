"""Exercise portable memory APIs across a real backend process restart, locally."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request


def verify(package):
    with tempfile.TemporaryDirectory(prefix='lumina-continuity-live-') as folder:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        origin='http://127.0.0.1:'+str(port)
        env=dict(os.environ,LUMINA_PORT=str(port),LUMINA_PROVIDER='local',LUMINA_WORKER='none',
                 LUMINA_MEMORY_PATH=str(Path(folder)/'memory.sqlite3'))
        headers={};backend=None
        def request(path,payload=None):
            data=None if payload is None else json.dumps(payload).encode()
            req=urllib.request.Request(origin+path,data=data,headers={**headers,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
        def start():
            nonlocal backend,headers
            backend=subprocess.Popen([str(package/'python/python.exe'),'-m','lumina.desktop_backend'],
                cwd=package/'app',env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                if backend.poll() is not None:raise RuntimeError('Portable backend exited before readiness.')
                try:
                    if request('/health').get('application')=='LUMINA':break
                except OSError:pass
                time.sleep(.1)
            else:raise RuntimeError('Portable backend did not become healthy.')
            headers={'X-Lumina-Token':request('/api/config')['token']}
        def stop():
            nonlocal backend
            if backend is not None:
                try:backend.communicate(b'shutdown\n',timeout=20)
                finally:
                    if backend.poll() is None:backend.kill();backend.wait(timeout=5)
                    backend=None
        try:
            start()
            assert request('/api/continuity?action=status')['status']=='ready'
            saved=request('/api/memory',{'action':'remember','text':'Portable fixture prefers a quiet editor','category':'preference'})
            assert saved['ok']
            identity=saved['record_id']
            pending=request('/api/continuity',{'tool':'memory_correct','arguments':{'id':identity,'new_value':'Portable fixture prefers a concise editor'}})
            assert pending['confirmation_required']
            assert request('/api/continuity?action=explain&id='+identity)['record']['valid_until'] is None
            confirmed=request('/api/confirm',{'confirmation_id':pending['confirmation_id'],'approve':True,'speak':False})
            assert confirmed['ok']
            stop();start()
            pack=request('/api/continuity?action=recall&query=Portable')
            assert len(pack['items'])==1
            assert pack['items'][0]['record']['object_value']=='Portable fixture prefers a concise editor'
            detail=request('/api/continuity?action=explain&id='+pack['items'][0]['id'])
            assert len(detail['history'])==2 and detail['evidence']
            assert request('/api/continuity?action=continuation')['ok']
            return {'ok':True,'packaged_python_used':True,'startup':'ready','create_retrieve':True,
                'correction_required_confirmation':True,'confirmed_correction':True,'restart_preserved_result':True,
                'historical_value_retained':True,'provenance_present':True,'continuation_api':True,
                'online_provider_calls':0,'real_user_database_modified':False}
        finally:stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('package',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=verify(args.package.resolve())
    if args.output:args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
