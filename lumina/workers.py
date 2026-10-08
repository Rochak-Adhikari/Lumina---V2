"""Supervised Claude stream, with a capability-limited workspace bridge."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from uuid import uuid4
from .tasks import WorkerResult
from .worker_logs import WorkerLogs


def build_worker_environment(workspace):
    allowed={'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATH','PATHEXT','TEMP','TMP','USERPROFILE','HOME','CLAUDE_CONFIG_DIR','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA'}
    env={k:v for k,v in os.environ.items() if k.upper() in allowed}
    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC']='1'
    env['CLAUDE_CODE_DISABLE_AUTO_MEMORY']='1'
    return env


def user_configuration_metadata():
    """Read only key names. Auth values remain in Claude's original settings."""
    directory=Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path(os.environ.get('HOME',os.environ.get('USERPROFILE',str(Path.home()))))/'.claude')))
    path=directory/'settings.json'
    try:data=json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):data={}
    return {'path':str(path),'exists':path.is_file(),
            'plugin_names':list(data.get('enabledPlugins',{})),
            'environment_names':list(data.get('env',{}))}


def redact(text):
    candidates=dict(os.environ)
    try:
        data=json.loads(Path(user_configuration_metadata()['path']).read_text('utf-8'))
        candidates.update(data.get('env',{}))
    except (OSError,ValueError,TypeError):pass
    text=str(text)
    for key,value in candidates.items():
        if re.search(r'KEY|TOKEN|SECRET|PASSWORD|COOKIE',key,re.I) and isinstance(value,str) and len(value)>=6:
            text=text.replace(value,'[redacted]')
    text=re.sub(r'AIza[\w-]{20,}|sk-[\w-]{16,}', '[redacted]', str(text))
    text=re.sub(r'eyJ[\w-]+\.[\w-]+\.[\w-]+','[redacted]',text)
    return re.sub(r'(?i)((?:api[_-]?key|auth[_-]?token|token|password|secret)["\x27]?\s*[=:]\s*["\x27]?)[^\s,"\x27}]+',r'\1[redacted]',text)


class WorkerManager:
    """Authoritative lifecycle registry; task and process identities are separate."""
    TERMINAL={'COMPLETED','FAILED','CANCELLED','TERMINATED'}
    TRANSITIONS={'CREATED':{'STARTING','CANCELLED'},'STARTING':{'RUNNING','FAILED','CANCELLED'},'RUNNING':{'WAITING','COMPLETED','FAILED','CANCELLED','TERMINATED'},'WAITING':{'RUNNING','FAILED','CANCELLED','TERMINATED'}}
    def __init__(self,on_event=None,logs=None): self.sessions={};self.on_event=on_event;self.logs=logs
    def create(self,task_id,instruction,workspace):
        wid=uuid4().hex
        self.sessions[wid]={'worker_id':wid,'task_id':task_id,'instruction':instruction,'workspace':str(workspace),'status':'CREATED','created_at':time.time(),'started_at':None,'completed_at':None,'pid':None,'exit_code':None,'summary':'','error':None,'output':'','events':[],'changed_files':[],'test_results':[],'transport':'structured-pipes','capabilities':{'cancel':True,'pause':False,'input':False},'last_activity':None}
        if self.logs:self.sessions[wid]['log_path']=self.logs.create(wid,self.sessions[wid])
        self.emit(wid,'worker.created');return wid
    def emit(self,wid,kind,**data):
        session=self.sessions[wid]
        data={k:redact(v) if isinstance(v,str) else v for k,v in data.items()}
        event={'type':kind,'worker_id':wid,'task_id':session['task_id'],'timestamp':time.time(),**data}
        session['events'].append(event);session['events']=session['events'][-100:];session['last_activity']=event['timestamp']
        if kind=='worker.output': session['output']=(session['output']+data.get('text',''))[-100000:]
        if self.logs:
            self.logs.append(wid,event)
            if kind!='worker.output':self.logs.metadata(wid,session)
        if self.on_event:
            try:self.on_event({'type':'worker_event','data':event})
            except Exception:pass
    def transition(self,wid,state,**fields):
        session=self.sessions[wid];old=session['status']
        if state not in self.TRANSITIONS.get(old,set()): raise ValueError(f'Invalid worker transition: {old} to {state}')
        session.update(fields,status=state)
        if state=='RUNNING': session['started_at']=time.time()
        if state in self.TERMINAL:session['completed_at']=time.time()
        self.emit(wid,{'RUNNING':'worker.started'}.get(state,'worker.'+state.lower()),status=state)
    def snapshot(self,wid):
        s=dict(self.sessions[wid]);s['events']=list(s['events']);s['changed_files']=list(s['changed_files'])
        s['elapsed']=round((s['completed_at'] or time.time())-(s['started_at'] or s['created_at']),1)
        s['idle_seconds']=round(time.time()-(s['last_activity'] or s['created_at']),1)
        return s
    def list_workers(self):return [self.snapshot(w) for w in self.sessions]


class ClaudeCodeWorker:
    def __init__(self,root:Path,executable='claude',timeout=1800, use_pty=None,visible=None,log_root=None):
        self.root=Path(root).resolve();self.executable=executable;self.timeout=max(30,min(int(timeout),7200))
        self.visible=(os.name=='nt' and use_pty is not False) if visible is None else visible
        self.logs=WorkerLogs(log_root)
        self.processes={};self.manager=WorkerManager(logs=self.logs);self.task_workers={}
        self.history={}
        # Pin enforcement code before any worker can edit this application's sources.
        self.bridge_sources={name:Path(__file__).with_name(name).read_bytes() for name in ('worker_bridge.py','desktop.py','local_operations.py','filesystem.py')}
        self.use_pty = os.name=='nt' if use_pty is None else use_pty

    def command(self,message,root=None,context=None,bridge_path=None):
        root=root or self.root
        executable=shutil.which(self.executable) or self.executable
        if not Path(executable).is_file():
            executable=next((str(Path(p)/self.executable) for p in os.environ.get('PATH','').split(os.pathsep) if (Path(p)/self.executable).is_file()),executable)
        native=Path(executable).parent/'node_modules/@anthropic-ai/claude-code/bin/claude.exe'
        if Path(executable).suffix.lower() in {'.ps1','.cmd'} and native.is_file(): executable=str(native)
        metadata=user_configuration_metadata()
        scrub={name:'' for name in set(metadata['environment_names'])|{'ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','CLAUDE_CODE_OAUTH_TOKEN','GEMINI_API_KEY','GOOGLE_API_KEY','NODE_OPTIONS','PYTHONPATH'}}
        bridge={'mcpServers':{'workspace':{'command':sys.executable,'args':[str(bridge_path or Path(__file__).with_name('worker_bridge.py')),str(root)],'env':scrub}}}
        args=['--print','--output-format','stream-json','--verbose','--permission-mode','dontAsk',
              '--tools','','--allowedTools','mcp__workspace__read,mcp__workspace__search,mcp__workspace__write,mcp__workspace__edit',
              '--strict-mcp-config','--mcp-config',json.dumps(bridge),'--setting-sources','user',
              '--settings',json.dumps({'disableAllHooks':True,'enableAllProjectMcpServers':False,'enabledPlugins':{name:False for name in metadata['plugin_names']}}),
              '--disable-slash-commands','--no-chrome','--no-session-persistence',
              '--append-system-prompt','Use only the supplied workspace tools. Report limitations truthfully. Shell execution and tests are unavailable in this constrained worker.' + (' Previous task turns (context only): '+json.dumps(context) if context else ''),message]
        if executable.lower().endswith('.ps1'):
            return [str(Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-ExecutionPolicy','Bypass','-File',executable,*args]
        return [executable,*args]

    async def run(self,session_id,message,workspace=None):
        root=Path(workspace).resolve() if workspace else self.root
        if not root.is_dir() or root==Path(root.anchor): raise RuntimeError('Choose a project directory below the drive root.')
        wid=self.manager.create(session_id,message,root);self.task_workers[session_id]=wid
        context=self.history.get(session_id,[])[-4:]
        bundle=tempfile.TemporaryDirectory(prefix='.lumina-worker-')
        package=Path(bundle.name)/'lumina';package.mkdir()
        (package/'__init__.py').write_text('',encoding='utf-8')
        for name,source in self.bridge_sources.items():(package/name).write_bytes(source)
        self.manager.sessions[wid]['transport']='ConPTY' if self.use_pty else 'structured-pipes'
        self.manager.transition(wid,'STARTING');process=None;result_text='';tool_calls={}
        async def pump(stream,source):
            pending=''
            while True:
                chunk=await stream.read(8192)
                if not chunk: break
                pending+=chunk.decode('utf-8',errors='replace')
                while '\n' in pending:
                    line,pending=pending.split('\n',1);consume(line,source)
                if len(pending)>262144:
                    self.manager.emit(wid,'worker.output',stream=source,text='[Oversized output record omitted]\n');pending=''
            if pending: consume(pending,source)

        def consume(line,source):
            nonlocal result_text
            line=re.sub(r'\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]', '', line).strip('\r')
            self.manager.emit(wid,'worker.output',stream=source,text=redact(line)[:32768]+'\n')
            try:data=json.loads(line)
            except ValueError:return
            if not isinstance(data,dict):return
            if data.get('type')=='result':
                if data.get('is_error'):
                    error='Claude Code is not logged in. Sign in through the Claude CLI.' if 'not logged in' in str(data.get('result','')).lower() else 'Claude reported a failed turn. Inspect the worker output.'
                    raise RuntimeError(error)
                result_text=redact(data.get('result',''))[:100000]
            blocks=data.get('message',{}).get('content',[]) if isinstance(data.get('message'),dict) else []
            if not isinstance(blocks,list):return
            for block in blocks:
                if not isinstance(block,dict):continue
                if block.get('type')=='tool_use':
                    tool_calls[block.get('id')]=block
                    self.manager.emit(wid,'worker.tool_call',name=block.get('name','unknown'))
                if block.get('type')=='tool_result' and not block.get('is_error'):
                    call=tool_calls.get(block.get('tool_use_id'),{})
                    if call.get('name') in {'mcp__workspace__write','mcp__workspace__edit'}:
                        path=call.get('input',{}).get('path')
                        if path and path not in self.manager.sessions[wid]['changed_files']:
                            self.manager.sessions[wid]['changed_files'].append(path);self.manager.emit(wid,'worker.file_changed',path=path)
        try:
            if self.use_pty:
                from .worker_terminal import WindowsTerminal
                spawning=asyncio.create_task(WindowsTerminal.spawn(self.command(message,root,context,package/'worker_bridge.py'),str(root),build_worker_environment(root)))
            else:
                spawning=asyncio.create_task(asyncio.create_subprocess_exec(*self.command(message,root,context,package/'worker_bridge.py'),cwd=str(root),env=build_worker_environment(root),stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0))
            try:process=await asyncio.shield(spawning)
            except asyncio.CancelledError:
                # A spawn in a thread cannot be abandoned: collect and close its process.
                process=await asyncio.shield(spawning)
                self.processes[session_id]=process
                raise
            self.processes[session_id]=process;self.manager.transition(wid,'RUNNING',pid=process.pid)
            if self.visible:
                viewer_pid=self.logs.show(wid,build_worker_environment(root))
                self.manager.sessions[wid]['terminal_pid']=viewer_pid
                self.manager.emit(wid,'worker.terminal_visible',terminal_pid=viewer_pid)
            async with asyncio.timeout(self.timeout):
                await asyncio.gather(pump(process.stdout,'stdout'),pump(process.stderr,'stderr'),process.wait())
            if process.returncode!=0:raise RuntimeError('Claude Code exited unsuccessfully. Inspect the worker output.')
            if not result_text:raise RuntimeError('Claude returned no verified final result.')
            summary=result_text.splitlines()[0][:400]
            self.manager.transition(wid,'COMPLETED',summary=summary,exit_code=process.returncode)
            self.history[session_id]=[*context,{'instruction':message[:1000],'result':result_text[:1000]}][-4:]
            return WorkerResult(result_text,summary)
        except asyncio.CancelledError:
            if process:await self._terminate(process)
            if self.manager.sessions[wid]['status'] not in WorkerManager.TERMINAL:self.manager.transition(wid,'CANCELLED')
            self.logs.close(wid)
            raise
        except Exception as exc:
            if process:await self._terminate(process)
            error='Worker exceeded its time limit.' if isinstance(exc,TimeoutError) else str(exc)
            if self.manager.sessions[wid]['status'] not in WorkerManager.TERMINAL:self.manager.transition(wid,'FAILED',error=redact(error),exit_code=process.returncode if process else None)
            raise RuntimeError(error) from None
        finally:
            if process is None or process.returncode is not None:
                self.processes.pop(session_id,None)
                self.manager.emit(wid,'worker.exited',exit_code=process.returncode if process else None)
            if process and self.use_pty and process.returncode is not None:
                await process.close()
                self.manager.emit(wid,'worker.terminal_closed')
            bundle.cleanup()

    async def send_message(self,session_id,message):
        raise RuntimeError('Interactive input is unavailable; resume after the current turn completes.')

    async def cancel(self,session_id):
        process=self.processes.get(session_id)
        if process:await self._terminate(process)

    @staticmethod
    async def _terminate(process):
        existing=getattr(process,'_lumina_termination',None)
        if existing is not None:
            await asyncio.shield(existing)
            return
        task=asyncio.create_task(ClaudeCodeWorker._kill_tree(process))
        process._lumina_termination=task
        try:await asyncio.shield(task)
        except Exception:
            process._lumina_termination=None
            raise

    @staticmethod
    async def _kill_tree(process):
        if process.returncode is not None:return
        if os.name=='nt':
            killer=await asyncio.create_subprocess_exec('taskkill','/PID',str(process.pid),'/T','/F',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000)
            await asyncio.wait_for(killer.wait(),5)
        else:process.terminate()
        await asyncio.wait_for(process.wait(),5)
