"""Persistent MSYS2 tmux worker with explicit, identity-checked cancellation."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import time
from .workers import WorkerManager,build_worker_environment,redact
from .tasks import WorkerResult


class TmuxCommandError(RuntimeError):
    pass


class TmuxWorker:
    persistent=True
    def __init__(self,root,executable,msys_root,limit=4,allow_metered=False):
        self.allow_metered=allow_metered
        self.root=Path(root);self.msys=Path(msys_root);self.executable=executable;self.limit=limit
        self.manager=WorkerManager();self.task_workers={};self.lock=asyncio.Lock()
        self.storage=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'LUMINA'/'agents'
        self.storage.mkdir(parents=True,exist_ok=True)
        self.registry=self.storage/'sessions.json'
        self.records=json.loads(self.registry.read_text()) if self.registry.exists() else {}
    async def command(self,*args,input=None,check=True):
        env=build_worker_environment(self.root);env['MSYS2_ARG_CONV_EXCL']='*';env['MSYS']='noglob'
        p=await asyncio.create_subprocess_exec(str(self.msys/'usr/bin/tmux.exe'),*args,env=env,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=0x08000000)
        try:out,err=await asyncio.wait_for(p.communicate(input),8)
        except BaseException:
            if p.returncode is None:
                p.kill()
                try:await asyncio.wait_for(p.wait(),2)
                except asyncio.TimeoutError:pass
            raise
        if check and p.returncode:raise TmuxCommandError('tmux operation failed: '+redact(err.decode(errors='replace'))[:200])
        return out.decode(errors='replace')
    def path(self,path):
        # Preserve the public path: resolve() can expose package virtualization
        # targets which a separately launched Windows Terminal cannot access.
        p=Path(os.path.abspath(path));return '/'+p.drive[0].lower()+str(p)[2:].replace('\\','/')
    def save(self):
        temp=self.registry.with_suffix('.tmp');temp.write_text(json.dumps(self.records),encoding='utf-8');temp.replace(self.registry)

    def save_task_state(self,session_id,status,summary='',completed_at=None):
        if session_id in self.records:
            self.records[session_id].update(task_status=status,summary=summary,completed_at=completed_at)
            self.save()

    def _state(self,session_id,status,**fields):
        record=self.records[session_id]
        record.update(status=status,**fields);self.save()
        wid=self.task_workers.get(session_id)
        if wid:
            state=self.manager.sessions[wid]
            # A failed startup can leave a live persistent process. Its later
            # confirmed cancellation is an adapter-specific terminal update.
            state.update(status=status,**fields)
            state['capabilities']['input']=status not in WorkerManager.TERMINAL
            if status in WorkerManager.TERMINAL:state['completed_at']=time.time()
            self.manager.emit(wid,'worker.'+status.lower(),status=status)

    async def _identity(self,record):
        """Return the exact session id, or None only on confirmed absence."""
        socket,name,pane=(record.get(k) for k in ('socket','name','pane'))
        if (not isinstance(socket,str) or not Path(socket).is_absolute()
                or not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',name)
                or not isinstance(pane,str) or not re.fullmatch(r'%\d+',pane)):
            raise ValueError('Invalid tracked tmux identity; refusing lifecycle operation.')
        try:
            output=await self.command('-S',socket,'list-panes','-a','-F',
                '#{session_name}|#{pane_id}|#{session_id}')
        except TmuxCommandError as exc:
            # Do not mistake permission errors, timeouts or executable failures
            # for proof that a persistent agent is no longer running.
            if re.search(r'(?i)no server running on |error connecting to .+\((?:no such file or directory|connection refused)\)',str(exc)):
                return None
            raise
        matches=[]
        for line in output.splitlines():
            fields=line.split('|')
            if len(fields)!=3 or not re.fullmatch(r'\$\d+',fields[2]):
                raise RuntimeError('Could not verify tmux session identity.')
            if fields[0]==name or fields[1]==pane:matches.append(fields)
        exact=[fields for fields in matches if fields[0]==name and fields[1]==pane]
        if not matches:return None
        if len(exact)!=1 or any(fields[0]!=name for fields in matches):
            raise RuntimeError('Tracked tmux session identity changed; refusing lifecycle operation.')
        return exact[0][2]

    async def remove(self,session_id):
        """Forget an inactive record; never delete agent files or logs."""
        async with self.lock:
            record=self.records.get(session_id)
            if record is not None:
                if await self._identity(record) is not None:
                    raise ValueError('The agent is still active; cancel it before removal.')
                del self.records[session_id]
                try:self.save()
                except BaseException:
                    self.records[session_id]=record
                    raise
            wid=self.task_workers.pop(session_id,None)
            if wid:self.manager.sessions.pop(wid,None)
    async def resolve_executable(self):
        executable=shutil.which(self.executable) or self.executable
        if not Path(executable).is_file():
            powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
            name=self.executable.replace("'","''")
            process=await asyncio.create_subprocess_exec(str(powershell),'-NoProfile','-NonInteractive','-Command',
                "(Get-Command -Name '"+name+"' -CommandType Application,ExternalScript -ErrorAction Stop | Select-Object -First 1).Source",
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000)
            try:output,_=await asyncio.wait_for(process.communicate(),10)
            except BaseException:
                if process.returncode is None:process.kill();await process.wait()
                raise
            executable=output.decode(errors='replace').strip()
        native=Path(executable).parent/'node_modules/@anthropic-ai/claude-code/bin/claude.exe'
        if native.is_file():executable=str(native)
        if not executable or not Path(executable).is_file():
            raise RuntimeError('Configured Claude executable is unavailable.')
        return executable
    async def terminal_executable(self):
        found=shutil.which('wt.exe')
        if found:return found
        powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        process=await asyncio.create_subprocess_exec(str(powershell),'-NoProfile','-NonInteractive','-Command',
            '(Get-AppxPackage Microsoft.WindowsTerminal | Select-Object -First 1).InstallLocation',
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000)
        try:output,_=await asyncio.wait_for(process.communicate(),10)
        except BaseException:
            process.kill();await process.wait();raise
        candidate=Path(output.decode(errors='replace').strip())/'WindowsTerminal.exe'
        return str(candidate) if candidate.is_file() else None

    async def attach(self,record):
        wt=await self.terminal_executable()
        if not wt:raise RuntimeError('Windows Terminal is unavailable; detached session preserved.')
        import subprocess
        command='exec /usr/bin/env TERM=xterm-256color /usr/bin/tmux -S '+shlex.quote(record['socket'].replace('\\','/'))+' attach-session -t '+shlex.quote(record['name'])
        # Keep the multi-layer command out of Windows Terminal's argument parser.
        # Terminal is outside the app's redirected LocalAppData namespace.
        # Keep the non-secret attachment script in MSYS2's shared filesystem.
        launcher=self.msys/'tmp'/(record['name']+'-attach.sh')
        launcher.write_text('#!/usr/bin/bash\nexport SHELL=/usr/bin/bash\nexec /usr/bin/script -q -c '+shlex.quote(command)+' /dev/null\n',encoding='utf-8')
        clients_before=set((await self.command('-S',record['socket'],'list-clients','-t',record['name'],'-F','#{client_pid} #{client_tty}')).splitlines())
        # Packaged Windows Terminal requires ShellExecute activation; CreateProcess
        # can exit without opening a tab when launched by the Python runtime.
        os.startfile(wt,arguments=subprocess.list2cmdline(['new-tab',str(self.msys/'usr/bin/bash.exe'),self.path(launcher)]))
        async with asyncio.timeout(12):
            while True:
                clients=set((await self.command('-S',record['socket'],'list-clients','-t',record['name'],'-F','#{client_pid} #{client_tty}')).splitlines())
                if clients-clients_before:
                    record.pop('attachment_error',None);return
                await asyncio.sleep(.2)
    async def discover(self):
        # Enumerate every socket, including named sockets, not merely "default".
        roots=[self.msys/'tmp']
        if os.environ.get('TMUX_TMPDIR'):roots.append(Path(os.environ['TMUX_TMPDIR']))
        sockets={str(p) for root in roots if root.exists() for folder in root.glob('tmux-*') for p in folder.iterdir()}
        sockets.update(r['socket'] for r in self.records.values())
        gate=asyncio.Semaphore(4)
        async def inspect_socket(socket):
            async with gate:
                try:
                    output=await self.command('-S',socket,'list-panes','-a','-F','#{session_name}|#{pane_id}|#{pane_current_path}|#{pane_dead}',check=False)
                except (OSError,asyncio.TimeoutError):return []
            found=[]
            for line in output.splitlines():
                fields=line.split('|')
                if len(fields)==4:found.append(dict(zip(('name','pane','cwd','dead'),fields),socket=socket))
            return found
        return [pane for group in await asyncio.gather(*(inspect_socket(socket) for socket in sorted(sockets))) for pane in group]
    async def tail(self,record):
        text=await self.command('-S',record['socket'],'capture-pane','-p','-J','-S','-60','-t',record['pane'])
        return redact('\n'.join(text.splitlines()[-60:]))[-8000:]
    @staticmethod
    def ready(text):
        # Fail closed on update, trust, login and permission dialogs.
        if re.search(r'(?i)update available|update now|trust this|not logged in|sign in|allow this|permission required',text):return False
        return bool(re.search(r'(?m)^\s*[❯>]\s*$',text)) and bool(re.search(r'(?i)claude code|\? for shortcuts',text))
    async def wait_ready(self,record):
        async with asyncio.timeout(45):
            while True:
                # Readiness concerns this pane, not every old socket on the machine.
                cwd=(await self.command('-S',record['socket'],'display-message','-p','-t',record['pane'],'#{pane_current_path} ')).strip()
                if cwd.rstrip('/').casefold()==record['cwd'].rstrip('/').casefold() and self.ready(await self.tail(record)):return
                await asyncio.sleep(.4)
    async def deliver(self,record,message):
        if any(ord(c)<32 and c not in '\n\r\t' for c in message):
            raise ValueError('Terminal control characters are not permitted in briefs.')
        await self.wait_ready(record)
        before=await self.tail(record)
        # The user explicitly authorized their configured Claude account. A UI
        # billing label is not a permission gate; Claude owns account limits.
        if len(message)>220:
            brief=self.storage/(record['name']+'-'+str(time.time_ns())+'.txt');brief.write_text(message,encoding='utf-8')
            message='Read the task brief at '+self.path(brief)+' and carry it out.'
        if '\x1b' in message:raise ValueError('Terminal escape characters are not permitted in briefs.')
        buffer='lumina-'+record['name']
        await self.command('-S',record['socket'],'load-buffer','-b',buffer,'-',input=message.encode())
        await self.command('-S',record['socket'],'paste-buffer','-p','-d','-b',buffer,'-t',record['pane'])
        await asyncio.sleep(.8)
        await self.command('-S',record['socket'],'send-keys','-t',record['pane'],'Enter')
        for attempt in range(8):
            await asyncio.sleep(.4);text=await self.tail(record)
            # Echo alone is not acknowledgement. Observe Claude's busy/output indicators.
            if text!=before and re.search(r'(?i)esc to interrupt|thinking',text):
                record['submitted']=True;self.save();return
            if attempt==3 and re.search(r'(?m)^\s*[❯>]\s*'+re.escape(message[:50]),text):
                await self.command('-S',record['socket'],'send-keys','-t',record['pane'],'Enter')
        raise RuntimeError('Brief submission could not be verified; session preserved for manual inspection.')
    async def run(self,session_id,message,workspace=None,*,launch_only=False):
        async with self.lock:
            if session_id not in self.records:
                live=await self.discover()
                if sum(p['name'].startswith('lumina-') and p['dead']=='0' for p in live)>=self.limit:raise RuntimeError('Live agent limit reached; existing agents are preserved.')
                root=Path(workspace or self.root).resolve(strict=True)
                if not root.is_dir():raise ValueError('Choose a project folder.')
                executable=await self.resolve_executable()
                user_key=hashlib.sha256(str(Path.home()).casefold().encode()).hexdigest()[:12]
                name='lumina-'+session_id[:12];socket=str(self.msys/'tmp'/('lumina-'+user_key+'.sock'));cwd=self.path(root)
                spawning=asyncio.create_task(self.command('-S',socket,'new-session','-d','-P','-F','#{pane_id} ','-s',name,'-c',cwd,shlex.quote(self.path(executable))))
                try:pane=(await asyncio.shield(spawning)).strip()
                except asyncio.CancelledError:
                    # Retain the identity even when cancellation races creation.
                    pane=(await asyncio.shield(spawning)).strip()
                    self.records[session_id]={'name':name,'socket':socket,'pane':pane,'cwd':cwd,'workspace':str(root),'instruction':message};self.save()
                    raise
                self.records[session_id]={'name':name,'socket':socket,'pane':pane,'cwd':cwd,'workspace':str(root),'instruction':message};self.save()
            record=self.records[session_id]
            if record.get('status') in {'CANCELLED','TERMINATED'}:
                raise ValueError('This agent has been stopped.')
            wid=self.task_workers.get(session_id)
            if not wid:
                wid=self.manager.create(session_id,message,record['workspace']);self.task_workers[session_id]=wid
                self.manager.sessions[wid].update(transport='persistent-tmux',capabilities={'cancel':True,'input':True,'pause':False})
                self.manager.transition(wid,'STARTING')
            elif self.manager.sessions[wid]['status']=='WAITING':self.manager.transition(wid,'RUNNING')
            elif self.manager.sessions[wid]['status']=='FAILED':self._state(session_id,'STARTING',error=None)
            try:
                await self.attach(record)
                if launch_only:
                    await self.wait_ready(record)
                    if self.manager.sessions[wid]['status']=='STARTING':self.manager.transition(wid,'RUNNING')
                    self.manager.transition(wid,'WAITING')
                    self._state(session_id,'WAITING')
                    return dict(record)
                await self.deliver(record,message)
                if self.manager.sessions[wid]['status']=='STARTING':self.manager.transition(wid,'RUNNING')
                self._state(session_id,'RUNNING')
            except Exception as e:
                self.manager.sessions[wid]['error']=str(e) or 'Agent startup timed out; its terminal session was preserved.'
                self._state(session_id,'FAILED',error=self.manager.sessions[wid]['error']);raise
        return await self.monitor(session_id)

    async def monitor(self,session_id):
        record=self.records[session_id];wid=self.task_workers[session_id]
        previous='';busy=bool(record.get('submitted',False))
        while True:
            if record.get('status') in {'CANCELLED','TERMINATED'}:raise asyncio.CancelledError()
            try:
                if await self._identity(record) is None:raise RuntimeError('The tracked tmux session is missing.')
                tail=await self.tail(record)
            except Exception as exc:
                if record.get('status') in {'CANCELLED','TERMINATED'}:raise asyncio.CancelledError()
                self._state(session_id,'FAILED',error=redact(str(exc)))
                raise
            if record.get('status') in {'CANCELLED','TERMINATED'}:raise asyncio.CancelledError()
            if tail!=previous:
                previous=tail;self.manager.sessions[wid]['output']=tail;self.manager.emit(wid,'worker.pane_changed')
            busy=busy or bool(re.search(r'(?i)esc to interrupt',tail))
            if busy and self.ready(tail):
                record['submitted']=False;self.save()
                self._state(session_id,'WAITING')
                return WorkerResult(tail,f"Agent {record['name']} has answered; its latest pane is available for summary.",True)
            await asyncio.sleep(1)
    async def send_message(self,session_id,message):
        async with self.lock:
            record=self.records[session_id]
            if record.get('status') in {'CANCELLED','TERMINATED'}:raise ValueError('This agent has been stopped.')
            await self.deliver(record,message)

    async def native_tree(self,record):
        from .windows_process_tree import ProcessTree
        pane_pid=(await self.command('-S',record['socket'],'display-message','-p','-t',record['pane'],'#{pane_pid}')).strip()
        if not pane_pid.isdigit():raise RuntimeError('Cannot identify worker pane process.')
        process=await asyncio.create_subprocess_exec(str(self.msys/'usr/bin/ps.exe'),'-l','-p',pane_pid,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=0x08000000)
        try:output,_=await asyncio.wait_for(process.communicate(),5)
        except BaseException:
            if process.returncode is None:process.kill();await process.wait()
            raise
        for line in output.decode(errors='replace').splitlines():
            fields=line.split()
            if len(fields)>=4 and fields[0]==pane_pid and fields[3].isdigit():
                return await asyncio.to_thread(ProcessTree,int(fields[3]))
        raise RuntimeError('Cannot map worker pane to its Windows process; cancellation was not performed.')

    async def cancel(self,session_id):
        async with self.lock:
            if session_id not in self.records:
                raise ValueError('That tracked tmux session is unavailable.')
            record=self.records[session_id]
            identity=await self._identity(record)
            if identity is not None:
                tree=await self.native_tree(record)
                try:
                    if await self._identity(record)!=identity:
                        raise RuntimeError('Worker identity changed before cancellation.')
                    await asyncio.to_thread(tree.terminate)
                finally:tree.close()
                # Recheck on the server command queue immediately before killing
                # the immutable session id. No shell and no prefix/name targeting.
                condition='#{&&:#{==:#{session_name},'+record['name']+'},#{==:#{session_id},'+identity+'}}'
                try:
                    await self.command('-S',record['socket'],'if-shell','-F','-t',record['pane'],
                        condition,'kill-session -t '+identity)
                except TmuxCommandError:
                    # The session may disappear between inspection and cancellation.
                    if await self._identity(record) is not None:raise
                if await self._identity(record) is not None:
                    raise RuntimeError('The tmux session did not confirm cancellation.')
            self._state(session_id,'CANCELLED',submitted=False)
            self.save_task_state(session_id,'CANCELLED','The task was cancelled.',time.time())

    def restore(self,session_id):
        record=self.records[session_id]
        wid=self.manager.create(session_id,record['instruction'],record['workspace']);self.task_workers[session_id]=wid
        status=record.get('status','RUNNING')
        if record.get('task_status')=='CANCELLED':status='CANCELLED'
        self.manager.sessions[wid].update(transport='persistent-tmux',capabilities={'cancel':True,'input':status not in WorkerManager.TERMINAL,'pause':False},
            status=status,error=record.get('error'),completed_at=record.get('completed_at'))
