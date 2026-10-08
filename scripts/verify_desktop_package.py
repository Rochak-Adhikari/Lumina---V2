"""Live packaged launcher verification using an isolated port and relocated copy."""
import json,os,shutil,socket,subprocess,tempfile,time,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
relocated=Path(tempfile.mkdtemp(prefix='LUMINA-relocated-'))/'LUMINA'
shutil.copytree(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'dist/LUMINA-Portable',relocated)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env=dict(os.environ,LUMINA_PORT=str(port),LUMINA_PROVIDER='local',LUMINA_WORKER='none')
exe=relocated/'LUMINA.exe'
report={'relocated':str(relocated),'port':port}
def health():
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=1) as r:return json.load(r)
 except Exception:return None
def run(kind,name):
 output=relocated/(name+'.json')
 p=subprocess.Popen([str(exe),kind,str(output)],cwd=os.environ['WINDIR'],env=env)
 try:p.wait(timeout=50)
 except subprocess.TimeoutExpired:p.kill();raise
 result=json.loads(output.read_text());report[name]=result;return result
assert run('--verify-backend','owned')['owned']
assert health() is None
backend=subprocess.Popen([str(relocated/'python/python.exe'),'-m','lumina.desktop_backend'],cwd=relocated/'app',env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
try:
 for _ in range(100):
  if health():break
  if backend.poll() is not None:raise RuntimeError(backend.stderr.read().decode())
  time.sleep(.1)
 assert run('--verify-backend','reused')['owned'] is False
 assert backend.poll() is None and health()
finally:
 backend.communicate(b'shutdown\n',timeout=15)
with socket.socket() as foreign:
 foreign.bind(('127.0.0.1',port));foreign.listen()
 result=run('--verify-backend','foreign')
 assert not result['ok'] and 'occupied' in result['error']
assert run('--verify-window','window')['ok']
assert health() is None
(ROOT/'artifacts/desktop-package-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
