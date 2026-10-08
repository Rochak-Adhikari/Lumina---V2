"""Bounded per-session event logs and a display-only Windows console."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class WorkerLogs:
    def __init__(self,root=None,limit=2_000_000,retention=20):
        self.root=Path(root or Path(os.environ.get('LOCALAPPDATA',Path.home()))/'LUMINA/.worker-logs')
        self.limit=limit;self.retention=retention;self.viewers={}

    def directory(self,wid):
        if not re.fullmatch('[0-9a-f]{32}',wid):raise ValueError('Invalid worker ID.')
        path=self.root/wid
        if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('Invalid log directory.')
        return path

    def create(self,wid,metadata):
        path=self.directory(wid);path.mkdir(parents=True,exist_ok=False)
        (path/'session.log').touch()
        self.metadata(wid,metadata)
        # Only completed logs created by this service are eligible for retention cleanup.
        completed=[]
        for p in self.root.iterdir():
            if not re.fullmatch('[0-9a-f]{32}',p.name) or not p.is_dir() or p.is_symlink():continue
            try:
                data=json.loads((p/'metadata.json').read_text('utf-8'))
                if data.get('status') in {'COMPLETED','FAILED','CANCELLED','TERMINATED'}:completed.append(p)
            except (OSError,ValueError):continue
        completed.sort(key=lambda p:p.stat().st_mtime,reverse=True)
        for old in completed[max(0,self.retention-1):]:
            if getattr(old,'is_junction',lambda:False)():continue
            for name in ('session.log','session.log.1','metadata.json'):
                try:(old/name).unlink(missing_ok=True)
                except OSError:pass
            try:old.rmdir()
            except OSError:pass
        return str(path/'session.log')

    def append(self,wid,event):
        path=self.directory(wid)/'session.log'
        encoded=json.dumps(event,ensure_ascii=True)+'\n'
        if path.stat().st_size+len(encoded.encode('utf-8'))>self.limit:
            path.replace(path.with_name('session.log.1'))
        with path.open('a',encoding='utf-8') as stream:stream.write(encoded)

    def metadata(self,wid,session):
        data={k:v for k,v in session.items() if k not in {'output','events','instruction'}}
        path=self.directory(wid)/'metadata.json'
        path.write_text(json.dumps(data,indent=2),encoding='utf-8')

    def read(self,wid):
        path=self.directory(wid)/'session.log'
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-100000));data=stream.read(100000)
        return data.decode('utf-8',errors='replace')

    def show(self,wid,env):
        if os.name!='nt':return None
        viewer=subprocess.Popen([sys.executable,str(Path(__file__).with_name('worker_viewer.py')),str(self.directory(wid)),wid],env=env,creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.viewers[wid]=viewer
        return viewer.pid

    def close(self,wid):
        viewer=self.viewers.pop(wid,None)
        if viewer and viewer.poll() is None:
            viewer.terminate();viewer.wait(timeout=5)


