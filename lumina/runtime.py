import asyncio
import time
import re
import base64
import uuid
import sqlite3
from contextvars import ContextVar
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit
from .filesystem import FileIndex
from .tools import ToolRegistry
from .providers.base import ProviderUnavailable
from .speech import spoken_text, brief_spoken_text
from .tasks import TaskManager
from .memory import MemoryStore
from .session_log import SessionLog
from .continuity_commands import ContinuityCommands, SCHEMAS as MEMORY_SCHEMAS, user_evidence, summary as memory_summary

STATES = {"IDLE", "LISTENING", "THINKING", "EXECUTING", "SPEAKING", "INTERRUPTED", "WAITING_FOR_USER", "ERROR"}


def browser_url(value):
    """Make a spoken domain usable while keeping the browser provider strict."""
    candidate=value.strip()
    if not re.match(r'^https?://', candidate, re.I):
        if ':' in candidate:
            raise ValueError('Use a public HTTP or HTTPS address.')
        candidate='https://'+candidate
    parsed=urlsplit(candidate)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Use a public HTTP or HTTPS address.')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or '/', parsed.query, ''))


class Runtime:
    def __init__(self, config, provider=None, workers=None):
        self.config = config
        self.index = FileIndex(config)
        self.session_log = SessionLog(config.root)
        self.session_id = self.session_log.session_id
        self.last_user_event_id = None
        self.last_memory_question = ''
        self._direct_reply_owner = ContextVar('lumina_direct_reply_owner', default=None)
        self.project_id = None
        self.continuity_error = None
        try:
            self.memory = MemoryStore(getattr(config, 'memory_path', ''))
        except (OSError, sqlite3.Error, ValueError):
            from .memory import UnavailableMemory
            self.memory = UnavailableMemory()
        self.tools = ToolRegistry(self.index, self.memory)
        self.tools.memory_context = self.memory_context
        self.continuity_commands = ContinuityCommands(self)
        self._continuity_workspace = None
        self.sync_memory_workspace()
        self.session_log.write('runtime.initialized', provider=config.provider, worker=config.worker,
                               workspace=str(config.root), memory_path=str(self.memory.path) if self.memory.path else None,
                               memory_status=self.memory_operation('status').get('status'))
        if workers is None and config.worker == "claude":
            if config.worker_backend=='tmux':
                from .tmux_worker import TmuxWorker
                workers={'claude-code':TmuxWorker(config.root,config.worker_executable,config.msys_root,config.agent_limit,config.allow_metered_agents)}
            else:
                from .workers import ClaudeCodeWorker
                workers = {"claude-code": ClaudeCodeWorker(config.root, config.worker_executable, config.worker_timeout)}
        self.provider = provider
        if config.provider == "gemini" and provider is None:
            from .providers.gemini import GeminiProvider
            self.provider = GeminiProvider(config)
        if self.provider:
            self.provider.register_tools(self.tools.specs)
        self.state = {"state": "IDLE", "revision": 0, "user_speaking": False, "lumina_speaking": False,
                      "task": None, "current_tool": None, "last_tool_result": None, "last_search": None,
                      "provider_status": "not_connected" if self.provider else "local", "errors": [],
                      "live_connected": False, "speech_id": 0}
        self.graph = {"revision": 0, "mode": "overview", "nodes": [], "links": []}
        self.graph_epoch = 0
        self.lock = asyncio.Lock()
        self.clients = set()
        self.messages = []
        self.message_id = 0
        self.live_owner = None
        self.analysis_task = None
        self.analysis_client = None
        self.analysis_audio_enabled=False
        self.command_task = None
        self.last_playback = time.monotonic()
        self.announcements = {}
        self.tools.reminders.notify = self._notify_reminder
        self.tools.phase2.notify = self._notify_automation
        self.tools.phase2.busy = lambda: (not self.clients or self.lock.locked() or
            self.state.get('user_speaking') or self.state.get('lumina_speaking') or
            self.state.get('state') in {'LISTENING','THINKING','EXECUTING','SPEAKING','WAITING_FOR_USER'})
        self.agent_summary_tasks = set()
        self.audit = []
        self.tasks = TaskManager(workers, self.agent_event, brief_spoken_text,
                                 on_continuity=self.continuity_task)
        self.tools.worker_status=lambda:[{k:v for k,v in s.items() if k not in {'output','events'}} for s in self.worker_sessions()]
        self.tools.agent_tail=self.read_agent_tail
        self.tools.spawn_agent=self.start_coding_agent
        self.delegation_request=None
        self.last_uploaded_file=None
        for worker in self.tasks.workers.values():
            if hasattr(worker,'manager'): worker.manager.on_event=self.worker_event

    def memory_context(self):
        return {'session_id': self.session_id, 'project_id': self.project_id,
                'device_id': getattr(self.memory, 'device_id', None),
                'model_metadata': {'provider':self.config.provider,'model':self.config.model,'prompt_version':'continuity-v1'},
                'source_event_id': self.last_user_event_id, 'query': self.last_memory_question}

    def memory_operation(self, operation, *args, **kwargs):
        """Continuity failure cannot change a completed user/worker operation."""
        try:
            result = getattr(self.memory, operation)(*args, **kwargs)
            if isinstance(result, dict) and result.get('ok') is False:
                self.continuity_error = 'Memory could not persist or retrieve this operation.'
            if operation in {'propose','remember','correct','consolidate','continuation','forget'}:
                self.session_log.write('continuity.'+operation,ok=result.get('ok') if isinstance(result,dict) else None,
                    decision=result.get('decision') if isinstance(result,dict) else None)
            return result
        except Exception:
            self.continuity_error = 'Memory is unavailable; no save was confirmed.'
            self.session_log.write('continuity.unavailable', operation=operation)
            return {'ok': False, 'status': 'unavailable', 'error': self.continuity_error}

    def sync_memory_workspace(self):
        path = str(Path(self.tools.desktop.workspace.active_workspace).resolve())
        if path == self._continuity_workspace:
            return
        result = self.memory_operation('set_workspace', path, session_id=self.session_id)
        if result.get('ok') is False:
            return
        project = result.get('project', result.get('entity', result))
        self.project_id = result.get('project_id') or project.get('id')
        self._continuity_workspace = path

    def capture_user_evidence(self, text):
        self.last_user_event_id = None
        self.memory.last_user_event_id = None
        selected = user_evidence(text)
        self.last_memory_question = selected or ''
        if selected is None:
            return None
        self.sync_memory_workspace()
        result = self.memory_operation('record_event', 'conversation.message',
            {'role': 'user', 'text': selected}, source_type='user',
            session_id=self.session_id, project_id=self.project_id,
            device_id=getattr(self.memory, 'device_id', None))
        if result.get('ok') is not False:
            self.last_user_event_id = result.get('id')
            self.memory.last_user_event_id = self.last_user_event_id
        return self.last_user_event_id

    def continuity_task(self, event):
        self.sync_memory_workspace()
        self.memory_operation('observe_task', event['task_id'], event['status'],
            description=user_evidence(event.get('description', '')) or '',
            workspace=event.get('workspace'), session_id=self.session_id, project_id=self.project_id)

    def continuity_tool(self, name, result):
        if name in MEMORY_SCHEMAS or name == 'search_memory':
            return
        self.sync_memory_workspace()
        # Only observed operation metadata crosses into event capture. No raw
        # command arguments, file contents, provider text or worker output.
        selected = {key: result[key] for key in ('ok', 'status', 'verified', 'confirmation_required',
            'exit_code', 'task_id') if key in result and isinstance(result[key], (str, int, bool, type(None)))}
        if result.get('ok') is True and not result.get('confirmation_required') and result.get('verified') is not False:
            for key in ('path', 'output_path', 'application_id', 'pid'):
                if isinstance(result.get(key), (str, int)):
                    selected[key] = result[key]
        self.memory_operation('observe_tool', name, {}, selected,
                              session_id=self.session_id, project_id=self.project_id)

    def worker_event(self,event):
        self.broadcast(event)
        self.session_log.write('worker.event', event_type=event.get('data', {}).get('type'),
                               task_id=event.get('data', {}).get('task_id'))
        if event['data']['type']!='worker.output':
            self.audit_event('worker',event['data']['type'],task_id=event['data']['task_id'])

    def worker_sessions(self):
        return [session for worker in self.tasks.workers.values() if hasattr(worker,'manager') for session in worker.manager.list_workers()]

    async def read_agent_tail(self,task_id):
        for worker in self.tasks.workers.values():
            if getattr(worker,'persistent',False) and task_id in worker.records:
                return {'ok':True,'agent':worker.records[task_id]['name'],'tail':await worker.tail(worker.records[task_id])}
        return {'ok':False,'error':'That persistent agent is unavailable.'}

    def authorize_delegation(self,text):
        """Called only for user text/transcription, never model output or tool data."""
        explicit=re.search(r'\b(?:assign|assigin|delegate|start|spawn|ask|tell)\b.*\b(?:worker|agent|claude)\b',text,re.I|re.S)
        denied=re.search(r"\b(?:don.t|do not|never)\s+(?:assign|delegate|start|spawn)\b",text,re.I)
        self.delegation_request=(text,time.monotonic()) if explicit and not denied else None

    async def start_coding_agent(self):
        request=self.delegation_request
        self.delegation_request=None  # One user request cannot spawn duplicate agents.
        if not request or time.monotonic()-request[1]>120:
            return {'ok':False,'error':'A fresh explicit user request to delegate is required.'}
        adapter=self.tasks.workers.get('claude-code')
        if not getattr(adapter,'persistent',False):
            return {'ok':False,'error':'The full Claude coding agent requires the tmux backend. The configured constrained worker is not a full coding terminal.'}
        instruction=request[0]
        workspace=self.tools.desktop.workspace.active_workspace
        folder=re.search(r'folder\s+(?:called|named?|name)\s+["\']?([\w -]+?)["\']?\s+(?:on|in)\s+(?:my\s+|the\s+)?desktop\b',instruction,re.I)
        if folder:
            target=self.tools.desktop.workspace.locations()['desktop']/folder[1].strip()
            try:
                target=self.tools.desktop.resolver.path(str(target),False)
                if target.exists() and not target.is_dir():return {'ok':False,'error':'The requested folder name is already a file.'}
                if not target.exists():
                    created=await self.tools.execute('create_directory',{'path':str(target)})
                    if not created.get('ok'):return created
                workspace=target
            except ValueError as exc:return {'ok':False,'error':str(exc)}
        result=await self.tasks.start_task('claude-code',instruction,authorized=True,workspace=workspace)
        self.broadcast({'type':'worker_panel_open'})
        return {'ok':True,'status':'queued','task_id':result['task_id'],'agent':'Claude '+result['task_id'][:12],
                'workspace':str(workspace),'message':'Launch requested; startup and brief submission are not yet verified. Use worker_status for actual progress.'}

    def audit_event(self, operation, status, **details):
        safe = {'operation': operation, 'status': status, 'time': time.time()}
        safe.update({key: value for key, value in details.items() if key in {'tool', 'worker', 'task_id', 'state'}})
        self.audit.append(safe)
        self.audit = self.audit[-100:]
        self.session_log.write('audit', **safe)

    def agent_event(self, event):
        data = event['data']
        self.audit_event('agent_task', data['status'].lower(), worker=data['worker'], task_id=data['task_id'])
        if data['status'] in {'COMPLETED','ERROR'} and self.tools.phase2.automation.status().get('settings',{}).get('enabled'):
            kind='worker_completed' if data['status']=='COMPLETED' else 'worker_failed'
            summary=brief_spoken_text(data.get('summary','')) or 'Its result is available in Workers.'
            self.record_automation_event(kind,'worker:'+data['task_id']+':'+data['status'],data['worker']+': '+summary)
            self.broadcast(event)
            return
        adapter=self.tasks.workers.get(data['worker'])
        if getattr(adapter,'persistent',False) and data['status']=='WAITING_FOR_USER':
            self.broadcast(event)
            task=asyncio.create_task(self.announce_agent_result(data))
            self.agent_summary_tasks.add(task)
            task.add_done_callback(self.agent_summary_tasks.discard)
            return
        summary = brief_spoken_text(data['summary']) or 'The worker returned no summary.'
        text = f"{data['worker']}: {summary}"
        if data['status'] == 'WAITING_FOR_USER':
            text += ' Your reply is needed, sir.'
        self.message('assistant', spoken_text(text))
        self.broadcast(event)
        self.queue_announcement(text)

    async def announce_agent_result(self,data):
        name='Agent '+data['task_id'][:12]
        text=name+' has returned; its result is available, but a spoken summary is unavailable.'
        try:
            result=self.tasks.get_agent_result(data['task_id'])
            summarize=getattr(self.provider,'summarize_agent_result',None)
            if summarize and result.get('result'):
                summary=await summarize(result['result'])
                text=name+': '+brief_spoken_text(summary)
        except Exception:
            pass  # Summary/provider failure must not hide the worker result.
        self.message('assistant',spoken_text(text))
        self.queue_announcement(text)

    def queue_announcement(self, text):
        # Direct replies are spoken by their own connection/turn, immediately.
        # Background agent/reminder tasks still retain their notification queue.
        owner = self._direct_reply_owner.get()
        if owner is not None and owner is asyncio.current_task():return
        key = str(self.message_id)
        self.announcements[key] = brief_spoken_text(text)
        self.announcements = dict(list(self.announcements.items())[-20:])
        self.broadcast({'type': 'announcement', 'id': key, 'text': self.announcements[key]})

    async def _notify_reminder(self, event):
        message = f"Reminder: {event['message']}"
        self.message('assistant', spoken_text(message))
        self.queue_announcement(message)
        return {'ok': True, 'status': 'notified', 'delivery_id': event['delivery_id']}

    async def _notify_automation(self, event):
        # No model or action tools run during notification phrasing.
        count=len(event.get('events',[]))
        text=(f'{count} updates are available in Automation, sir.' if count>1 else
              brief_spoken_text(event.get('message','An update is available in Automation, sir.')))
        self.message('assistant',text)
        self.queue_announcement(text)
        self.broadcast({'type':'automation_notification','id':event['delivery_id']})
        return {'ok':True,'status':'notified','delivery_id':event['delivery_id']}

    def record_automation_event(self,kind,identity,message):
        async def enqueue():
            await self.tools.phase2.automation.enqueue({'type':kind,'delivery_id':identity,'message':message[:1000]})
        try:
            task=asyncio.create_task(enqueue())
            self.agent_summary_tasks.add(task)
            task.add_done_callback(self.agent_summary_tasks.discard)
        except RuntimeError:pass

    async def local_command(self, text, allow_search=True, output_client=None, speak=False):
        token=self._direct_reply_owner.set(asyncio.current_task())
        try:
            return await self._local_command(text,allow_search,output_client,speak)
        finally:
            self._direct_reply_owner.reset(token)

    async def _local_command(self, text, allow_search=True, output_client=None, speak=False):
        """Narrow deterministic commands remain usable without online reasoning."""
        clean = text.strip().strip('“”"')
        if await self.continuity_commands.run(clean):return True
        if not hasattr(self,'capability_commands'):
            from .capability_commands import CapabilityCommands
            self.capability_commands=CapabilityCommands(self)
        if await self.capability_commands.run(clean):return True
        if re.fullmatch(r'(?:show|list|browse)(?: me)? (?:my |the )?(?:uploaded files|uploads|workspace files)[.!]?',clean,re.I):
            self.message('user',text)
            result=await self.handle_tool_call('list_uploaded_files',{})
            self.broadcast({'type':'workspace_open'})
            self.message('assistant',f"There are {len(result.get('files',[]))} uploaded files available in your workspace, sir." if result.get('ok') else result['error'])
            self.set_state('IDLE');return True
        if clean.lower().rstrip('.!') in {'confirm','yes confirm','allow the capture','approve','yes','yeah'}:
            pending=[key for key,value in self.tools.pending.items() if value['expires']>time.monotonic()]
            if len(pending)==1:
                self.message('user',text)
                async with self.lock:await self.confirm_action(pending[0],speak=speak,output_client=output_client)
                return True
            if pending:
                self.message('assistant','Choose the exact action in the confirmation dialog, sir.');return True
        if await self.desktop_command(clean): return True
        app = re.fullmatch(r'open\s+(chrome|edge|notepad|calculator)[.!]?', clean, re.I)
        file = re.fullmatch(r'(read|open)\s+file\s+(.+)', clean, re.I)
        url = re.fullmatch(r'open\s+(https?://\S+)', clean, re.I)
        search = re.fullmatch(r'(?:find|search for)\s+(.+)', clean, re.I)
        memory = re.fullmatch(r'(?:remember|save memory)\s+(.+)', clean, re.I)
        recall = re.fullmatch(r'(?:search|recall)\s+memory(?:\s+for)?\s+(.+)', clean, re.I)
        if app:
            name, args = 'open_app', {'app': app[1].lower()}
        elif file:
            name, args = ('read_file' if file[1].lower() == 'read' else 'open_file'), {'path': file[2].strip('"')}
        elif url:
            name, args = 'open_url', {'url': url[1]}
        elif clean.lower().rstrip('.?') in ('system info', 'system information'):
            name, args = 'system_info', {}
        elif search and allow_search:
            await self.local_search(search[1])
            return True
        elif memory:
            self.message('user', text)
            result = self.memory_operation('remember', memory[1], authorized=True)
            self.report_memory_result(result)
            return True
        elif recall:
            self.message('user', text)
            result = self.memory_operation('search', recall[1])
            if not result.get('ok'):
                answer = result.get('error', 'Memory is unavailable.')
            elif result['count']:
                match = result['matches'][0]
                answer = f"I found {result['total']} memory match{'es' if result['total'] != 1 else ''}. The closest says, {match['text']}."
            else:
                answer = 'I found no matching memory, sir.'
            self.message('assistant', spoken_text(answer));self.set_state('IDLE', task=None);self.queue_announcement(answer)
            return True
        else:
            return False
        self.message('user', text)
        async with self.lock:
            result = await self.handle_tool_call(name, args)
            self.report_local_result(name, result)
        return True

    async def desktop_command(self,text):
        """Trusted user text only; model tool output never authorizes delegation."""
        clean=text.strip().rstrip('.?')
        lower=clean.lower()
        reminder_match=re.fullmatch(r'(?:create|set)\s+(?:a\s+)?reminder\s+(?:for|in)\s+(\d+|one|two|fifteen)\s+(second|minute|hour)s?(?:\s+(?:from now|in the future))?(?:\s+to\s+(.+))?',clean,re.I)
        if reminder_match:
            words={'one':1,'two':2,'fifteen':15}; amount=words.get(reminder_match[1].lower())
            if amount is None:amount=int(reminder_match[1])
            seconds=amount*{'second':1,'minute':60,'hour':3600}[reminder_match[2].lower()]
            if not 1<=seconds<=31536000:
                self.message('assistant','Choose a reminder between one second and one year from now.');return True
            self.message('user',text)
            result=await self.handle_tool_call('reminder',{'action':'create','message':reminder_match[3] or 'Your requested reminder',
                'due_at':(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()})
            self.report_local_result('reminder',result);return True
        if re.search(r'\b(?:inspect|process|extract|summarize|analyse|analyze|explain|read)\b',lower) and re.search(r'\b(?:uploaded|attached|selected)\b',lower):
            inventory=await asyncio.to_thread(self.tools.uploads.list_files)
            files=inventory.get('files',[])
            matches=[file for file in files if file['name'].casefold() in lower]
            path=matches[0]['path'] if len(matches)==1 else self.last_uploaded_file if not matches else None
            if path is None and len(files)==1:path=files[0]['path']
            if path is None or len(matches)>1:
                self.broadcast({'type':'workspace_open'})
                self.message('assistant','Select the document in Workspace or give me its exact filename, sir.');return True
            self.message('user',text)
            action='analyze' if re.search(r'\b(?:summarize|analyse|analyze|explain)\b',lower) else 'extract'
            args={'path':path,'action':action}
            if action=='analyze':args['question']=text
            result=await self.handle_tool_call('process_file',args)
            self.report_local_result('process_file',result);return True
        follow=re.fullmatch(r'(?:tell|message) agent(?: ([a-f0-9]{6,32}))?\s*:\s*(.+)',clean,re.I|re.S)
        if follow:
            candidates=[s for s in self.tasks.list_tasks() if (not follow[1] or s['task_id'].startswith(follow[1])) and s['status'] in {'RUNNING','WAITING_FOR_USER'}]
            if len(candidates)!=1:
                self.message('assistant','Which agent should receive that, sir?');return True
            s=candidates[0];self.message('assistant',f"I’m messaging agent {s['task_id'][:6]}: {follow[2][:120]}")
            method=self.tasks.send_agent_message if s['status']=='RUNNING' else self.tasks.resume_task
            await method(s['task_id'],follow[2],authorized=True);return True
        compound=re.fullmatch(r'(find (?:my |the )?lumina project|create (.+?)),? (?:and )?open it in (?:vs code|visual studio code),? and (?:create a claude task to|ask claude to) (.+)',clean,re.I)
        if compound:
            if 'claude-code' not in self.tasks.workers:
                self.message('assistant','Claude Code is not configured, sir.');return True
            path='my project'
            if compound[2]:
                made=await self.handle_tool_call('create_directory',{'path':compound[2]})
                if not made.get('ok'):self.report_local_result('create_directory',made);return True
                path=made['path']
            resolved=await self.handle_tool_call('resolve_path',{'path':path})
            if not resolved.get('ok'):self.report_local_result('resolve_path',resolved);return True
            opened=await self.handle_tool_call('open_with',{'path':resolved['path'],'application':'visual studio code'})
            if not opened.get('ok'):self.report_local_result('open_with',opened);return True
            await self.tasks.start_task('claude-code',compound[3],authorized=True,workspace=resolved['path'])
            from pathlib import Path
            self.tools.desktop.workspace.active_worker_workspace=Path(resolved['path'])
            self.broadcast({'type':'worker_panel_open'})
            self.message('assistant','The project is open and the Claude launch is requested, sir.');self.set_state('IDLE',task=None);return True
        if lower in {'what is claude doing','is claude still working','how long has claude been working','show me what claude is doing',"cancel claude's current task",'stop claude','stop the worker','cancel the worker','terminate the worker','remove the worker','cancel that task','show my workers','show my agents'}:
            sessions=self.worker_sessions()
            active=[s for s in sessions if s['status'] in {'STARTING','RUNNING','WAITING'}]
            if lower.startswith('show'):
                self.broadcast({'type':'worker_panel_open'})
                answer='The worker panel is open, sir.'
            elif lower.startswith(('cancel','stop','terminate','remove')):
                self.broadcast({'type':'worker_panel_open'})
                answer='Select the exact agent in Workers and confirm Stop or Remove, sir.'
            elif len(active)==1:
                s=active[0];last=next((e.get('name') for e in reversed(s['events']) if e['type']=='worker.tool_call'),None)
                answer=f"Claude has been working for {int(s['elapsed'])} seconds, sir."+(f' Its latest reported action is {last}.' if last else '')
            elif active:answer=f'{len(active)} Claude tasks are active. Choose one in the worker panel, sir.'
            else:answer='No Claude task is running, sir.'
            self.message('user',text);self.message('assistant',answer);self.queue_announcement(answer);return True
        browser_request=re.fullmatch(r'(?:open|launch)\s+(?:a\s+)?(?:supervised\s+)?browser(?:\s+session)?\s+and\s+navigate\s+to\s+([^\s]+)(?:\s+in\s+the\s+browser)?',clean,re.I)
        if browser_request:
            self.message('user', text)
            started=await self.handle_tool_call('browser_control', {'action':'start'})
            if not started.get('ok'):
                self.report_local_result('browser_control', started);return True
            tab_id=started.get('tab_id')
            if not tab_id:
                tabs=await self.handle_tool_call('browser_control',{'action':'list_tabs'})
                tab_id=next((tab['tab_id'] for tab in tabs.get('tabs',[])),None)
            inspected=await self.handle_tool_call('browser_control', {'action':'inspect','tab_id':tab_id})
            if not inspected.get('ok'):
                self.report_local_result('browser_control', inspected);return True
            url=browser_url(browser_request[1])
            result=await self.handle_tool_call('browser_control', {'action':'navigate','tab_id':tab_id,
                'snapshot':inspected['snapshot'],'url':url})
            self.report_local_result('browser_control', result)
            return True
        if re.fullmatch(r'(?:process|capture|analyze|analyse|look at|show me)\s+(?:(?:my|the)\s+)?screen(?:\s+and\s+tell\s+me\s+what\s+you\s+(?:can\s+)?see)?',clean,re.I):
            self.message('user', text)
            result=await self.handle_tool_call('screen_capture', {'action':'capture' if lower.startswith('capture') else 'analyze','target':'monitor','source':'1'})
            self.report_local_result('screen_capture', result)
            return True
        web_query=re.fullmatch(r'(?:search|look up|find)\s+(.+?)\s+(?:in|on)\s+(?:the\s+)?web',clean,re.I)
        web_query=web_query or re.fullmatch(r'(?:search\s+(?:the\s+)?(?:web|internet|online)(?:\s+for)?|web\s+search|look\s+up\s+online)\s+(.+)',clean,re.I)
        if web_query:
            self.message('user', text)
            result=await self.handle_tool_call('web_search', {'query':web_query[1]})
            self.report_local_result('web_search', result)
            return True
        file_request=re.fullmatch(r'(?:process|inspect|extract)\s+(?:this|the)?\s*file\s+(.+)',clean,re.I)
        if file_request:
            self.message('user', text)
            action='extract' if lower.startswith('extract') else 'inspect'
            result=await self.handle_tool_call('process_file', {'path':file_request[1], 'action':action})
            self.report_local_result('process_file', result)
            return True
        delegate=re.fullmatch(r'(?:ask claude to|tell claude to|start claude task to)\s+(.+)',clean,re.I)
        if delegate:
            if 'claude-code' not in self.tasks.workers:
                self.message('assistant','Claude Code is not configured, sir.');return True
            self.message('user',text)
            task=await self.tasks.start_task('claude-code',delegate[1],authorized=True,workspace=self.tools.desktop.workspace.active_workspace)
            self.tools.desktop.workspace.active_worker_workspace=self.tools.desktop.workspace.active_workspace
            self.broadcast({'type':'worker_panel_open'})
            answer=f"I’m starting Claude agent {task['task_id'][:12]} to {delegate[1][:120]}"
            self.message('assistant',answer);self.queue_announcement(answer);return True
        name=args=None
        if lower in {'find my lumina project','find the lumina project','find my project'}:
            name,args='resolve_path',{'path':'my project'}
        else:
            match=re.fullmatch(r'open (.+) in (?:vs code|visual studio code)',clean,re.I)
            if match:name,args='open_with',{'path':match[1],'application':'visual studio code'}
            match=re.fullmatch(r'create (?:a )?folder (?:called )?(.+?) (?:inside|in) (.+)',clean,re.I)
            if match:
                try:
                    base=self.tools.desktop.resolver.path(match[2])
                    from pathlib import Path
                    if Path(match[1]).name!=match[1]: raise ValueError('Use a simple folder name.')
                    name,args='create_directory',{'path':str(base/match[1])}
                except ValueError as exc:
                    self.message('system',str(exc));return True
            match=re.fullmatch(r'find (?:every|all) Python files? (?:inside|in) (.+)',clean,re.I)
            if match:name,args='search_files',{'query':'py','file_type':'.py','root':match[1]}
            match=re.fullmatch(r'(?:open folder|open terminal in|show in explorer|create folder) (.+)',clean,re.I)
            if match:
                name='open_folder' if lower.startswith('open folder') else 'open_terminal' if lower.startswith('open terminal') else 'reveal_in_explorer' if lower.startswith('show') else 'create_directory'
                args={'path':match[1]}
            if name is None:
                match=re.fullmatch(r'(?:open|launch) (.+)',clean,re.I)
                if match and not match[1].startswith(('file ','http','folder ')) and not re.search(r'\b(?:supervised\s+browser|browser\s+session)\b',match[1],re.I):
                    name,args='open_app',{'app':match[1]}
        if name is None:return False
        self.message('user',text)
        async with self.lock:
            result=await self.handle_tool_call(name,args)
            if name=='resolve_path' and result.get('ok'):result['message']='Your project is at '+result['path']
            if name=='search_files' and result.get('ok'):result['message']=f"Found {result['count']} matching files in the scanned directory, sir."
            self.report_local_result(name,result)
        return True
    def report_memory_result(self, result):
        answer = 'That memory was saved, sir.' if result.get('ok') else result.get('error', 'The memory operation failed.')
        self.message('assistant', spoken_text(answer));self.set_state('IDLE', task=None);self.queue_announcement(answer)

    def report_local_result(self, name, result):
        if result.get('confirmation_required'):
            message = result.get('message','Confirm the selected action.') + ' Shall I continue, sir?'
            self.message('assistant', message)
            self.set_state('WAITING_FOR_USER', task=None)
            return
        if not result.get('ok'):
            self.message('system', result.get('error', 'That operation could not finish.'))
            self.set_state('IDLE', task=None)
            return
        if result.get('analysis'):
            answer=result['analysis']
        elif name in MEMORY_SCHEMAS:
            answer=memory_summary(name,result)
            self.broadcast({'type':'continuity_result','tool':name,'data':result})
        elif name == 'screen_capture':
            answer='The screen image was captured locally, sir. It has not been sent for analysis.'
            self.broadcast({'type':'screen_preview','available':True})
        elif name == 'process_file':
            answer='The document was processed locally; its extracted content is available in the result panel, sir.'
            self.broadcast({'type':'file_content','path':result.get('path','Document'),'text':result.get('text') or str(result.get('metadata',{}))})
        elif name == 'reminder':
            job=result.get('job',{})
            answer=f"Reminder {result.get('status','updated')}, sir."+(f" Due at {job['due_at']}." if job.get('due_at') else '')
        elif name in {'background_monitor','proactive','computer_settings','computer_control','youtube_video'}:
            answer=result.get('message') or f"{name.replace('_',' ').capitalize()}: {result.get('status','result available')}, sir."
            if name=='computer_settings' and 'targets' in result:answer=f"Found {len(result['targets'])} Windows settings targets; they are available in Automation, sir."
            elif name=='computer_control' and 'windows' in result:answer=f"Found {len(result['windows'])} controllable windows; they are available in Automation, sir."
            elif name=='computer_control' and 'controls' in result:answer=f"Inspected the window and found {len(result['controls'])} controls; their details are available in Automation, sir."
            elif name=='background_monitor' and 'watches' in result:answer=f"There are {len(result['watches'])} background watches, sir."
            if result.get('verified') is False:answer+=' The change is not verified.'
            self.broadcast({'type':'phase2_result','tool':name,'data':result})
        elif name == 'browser_control':
            answer=f"Browser action {result.get('status','finished')}, sir."
        elif name == 'web_search':
            answer=f"Found {len(result.get('results',[]))} web results, sir."+(' '+result['warning'] if result.get('warning') else '')
            self.broadcast({'type':'file_content','path':'Web search results','text':'\n\n'.join(f"{r['title']}\n{r['url']}\n{r.get('snippet','')}" for r in result.get('results',[]))})
        elif name == 'read_file':
            answer = 'The file is available on screen, sir.'
            if result.get('truncated'):
                answer += ' Only the beginning was read.'
            self.broadcast({'type': 'file_content', 'path': result['path'], 'text': result['content']})
        elif name == 'system_info':
            answer = f"This computer runs {result['system']} {result['release']}, sir."
        else:
            answer = result.get('message', 'The operation completed, sir.')
        self.message('assistant', spoken_text(answer))
        self.set_state('SPEAKING' if self.state.get('lumina_speaking') else 'IDLE', task=None,current_tool=None)
        if not result.get('analysis'):
            self.queue_announcement(answer)

    async def confirm_action(self, confirmation_id, *, speak=False, output_client=None):
        pending=self.tools.pending.get(confirmation_id,{})
        name=pending.get('name','unknown')
        self.analysis_task=asyncio.current_task()
        self.analysis_client=output_client
        self.analysis_audio_enabled=speak
        speech_id=None
        self.set_state('EXECUTING',current_tool=name)
        self.broadcast({'type':'analysis_progress','client_id':output_client,'stage':'processing','tool':name})
        try:
            result=await self.tools.confirm(confirmation_id)
            self.continuity_tool(name, result)
            image_data=result.pop('image_data',None)
            question=pending.get('analysis')
            if result.get('ok') and question:
                analyze=getattr(self.provider,'analyze_context',None)
                if analyze is None:
                    result={**result,'ok':False,'error':'Capture or extraction succeeded, but online analysis is unavailable.'}
                else:
                    try:
                        kwargs={'image':self.tools.screen.last_frame} if name=='screen_capture' else {'image':base64.b64decode(image_data)} if image_data else {'text':result.get('text','')}
                        if name=='screen_capture' and not kwargs['image']:raise ValueError('No current frame')
                        if 'text' in kwargs and not kwargs['text'].strip():raise ValueError('No extractable text; OCR may be required')
                        self.interrupt()
                        speech_id=self.state['speech_id']
                        self.set_state('THINKING',task='Analyzing your evidence',current_tool=name)
                        self.broadcast({'type':'analysis_progress','client_id':output_client,'stage':'analyzing','tool':name})
                        async def emit(event):
                            if self.state['speech_id']!=speech_id:return
                            if event['type']=='audio' and self.analysis_audio_enabled:
                                self.broadcast({'type':'analysis_audio','client_id':output_client,
                                    'data':base64.b64encode(event['data']).decode('ascii'),
                                    'sample_rate':event['sample_rate'],'speech_id':speech_id})
                            elif event['type']=='transcript' and event.get('role')=='assistant':
                                self.broadcast({'type':'analysis_transcript','client_id':output_client,
                                    'text':event['text'],'speech_id':speech_id})
                        streaming=getattr(self.provider,'stream_analysis',None)
                        answer=await streaming(question,emit,**kwargs) if streaming else await analyze(question,**kwargs)
                        result={**result,'analysis':answer,'status':'analyzed','uploaded':True,
                            'analysis_truncated':bool(result.get('truncated') or len(kwargs.get('text',''))>60000)}
                    except asyncio.CancelledError:raise
                    except Exception:
                        result={**result,'ok':False,'status':'analysis_failed','error':'Local processing succeeded, but the configured reasoning provider could not analyze it. No success was assumed.'}
            self.audit_event('confirmation','succeeded' if result.get('ok') else 'failed',tool=name)
            self.broadcast({'type':'confirmation_resolved','confirmation_id':confirmation_id})
            self.broadcast({'type':'capability_result','tool':name,'data':result})
            self.report_local_result(name,result)
            return result
        except asyncio.CancelledError:
            self.broadcast({'type':'confirmation_resolved','confirmation_id':confirmation_id})
            self.audit_event('confirmation','cancelled',tool=name)
            raise
        finally:
            self.broadcast({'type':'analysis_complete','client_id':output_client,'speech_id':speech_id})
            self.analysis_task=None
            if self.state.get('state') in {'EXECUTING','THINKING','INTERRUPTED'}:self.set_state('IDLE',current_tool=None)

    def cancel_analysis(self, client_id):
        if self.analysis_task and self.analysis_client==client_id:
            self.analysis_task.cancel()

    def set_state(self, state=None, **changes):
        previous_provider=self.state.get('provider_status')
        if state:
            assert state in STATES
            changes["state"] = state
        self.state.update(changes)
        current_provider=self.state.get('provider_status')
        if current_provider!=previous_provider and current_provider in {'unavailable','connected','failed'}:
            kind='provider_recovered' if current_provider=='connected' else 'provider_failed'
            self.record_automation_event(kind,'provider:'+str(uuid.uuid4()),
                'The online provider is connected.' if kind=='provider_recovered' else 'The online provider is unavailable; local features remain available.')
        self.state["revision"] += 1
        self.session_log.write('state', state=self.state.get('state'), current_tool=self.state.get('current_tool'),
                               task=self.state.get('task'))
        self.broadcast({"type": "state", "data": self.snapshot()})

    def snapshot(self):
        return {**self.state, "graph_revision": self.graph["revision"], "messages": self.messages[-40:]}

    def broadcast(self, event):
        for queue in tuple(self.clients):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow UI connections must reconnect rather than accumulating audio forever.
                self.clients.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "disconnect", "reason": "Client could not keep up."})

    def message(self, role, text, *, capture_memory=True):
        if role=='user':
            self.authorize_delegation(text)
            if capture_memory:self.capture_user_evidence(text)
        self.message_id += 1
        self.messages.append({"id": self.message_id, "role": role, "text": text[:12000]})
        self.messages = self.messages[-40:]
        self.session_log.write('message', role=role, text=text[:2000])
        self.set_state()

    def fail(self, message):
        self.state["errors"] = [*self.state["errors"][-4:], message]
        self.set_state("ERROR", task=None, current_tool=None, lumina_speaking=False, user_speaking=False)
        self.message("system", message)

    async def refresh(self):
        epoch = self.graph_epoch
        graph = await asyncio.to_thread(self.index.overview)
        # A refresh never owns a search view, including refreshes started after a search.
        if epoch == self.graph_epoch and self.graph["mode"] == "overview":
            self.graph = {**graph, "mode": "overview", "revision": self.graph["revision"] + 1}
            self.set_state()
        return self.graph

    async def reset_graph(self):
        self.graph_epoch += 1
        self.graph = {**self.graph, "mode": "overview", "revision": self.graph["revision"] + 1}
        return await self.refresh()

    async def handle_tool_call(self, name, arguments, *, memory_online=True):
        call_id=str(uuid.uuid4())
        started=time.monotonic()
        self.session_log.write('tool.started',call_id=call_id,tool=name,
            action=arguments.get('action') if isinstance(arguments,dict) else None)
        self.audit_event('tool', 'requested', tool=name)
        self.set_state("EXECUTING", current_tool=name)
        try:
            result = (self.tools.continuity.execute(name, arguments, online=False)
                      if name in MEMORY_SCHEMAS and not memory_online
                      else await self.tools.execute(name, arguments))
        except asyncio.CancelledError:
            self.session_log.write('tool.cancelled',call_id=call_id,tool=name,elapsed_ms=round((time.monotonic()-started)*1000))
            raise
        if name == 'query_knowledge_graph':
            try: self.broadcast({'type':'knowledge_filter','query':arguments['query']})
            except Exception: pass  # Cosmetic failure must never discard context.
        self.audit_event('tool', 'awaiting_confirmation' if result.get('confirmation_required') else 'succeeded' if result.get('ok') else 'failed', tool=name)
        self.continuity_tool(name, result)
        self.session_log.write('tool.result', call_id=call_id, elapsed_ms=round((time.monotonic()-started)*1000), tool=name, status=result.get('status'), ok=result.get('ok'),
                               code=result.get('code'), error=result.get('error'), action=arguments.get('action') if isinstance(arguments,dict) else None, confirmation_required=result.get('confirmation_required'),
                               result_count=len(result['items']) if name in MEMORY_SCHEMAS and isinstance(result.get('items'),list) else None,
                               truncated=result.get('truncated'))
        if not hasattr(self,'capability_commands'):
            from .capability_commands import CapabilityCommands
            self.capability_commands=CapabilityCommands(self)
        self.capability_commands.observe(name,arguments,result)
        if result.get('confirmation_required'):
            self.broadcast({'type': 'confirmation', 'data': result})
        if result.get("ok") and name == "find_files":
            self.graph_epoch += 1
            self.graph = {**result["graph"], "mode": "search", "query": result["query"],
                          "count": result["count"], "partial": result["partial"],
                          "scan_incomplete": result["scan_incomplete"], "revision": self.graph["revision"] + 1}
            summary = {k: v for k, v in result.items() if k not in ("graph", "results")}
            self.state["last_search"] = summary
        # Never send visualization-only nodes to Gemini as search hits.
        response = {k: v for k, v in result.items() if k != "graph"}
        self.set_state("THINKING", current_tool=None, last_tool_result=response)
        return response

    async def local_search(self, query):
        async with self.lock:
            self.set_state("THINKING", task="Local file search")
            self.message("user", query)
            result = await self.handle_tool_call("find_files", {"query": query})
            if result.get("ok"):
                partial = "partial " if result["partial"] else ""
                answer = f"Found {result['count']} {partial}direct match{'es' if result['count'] != 1 else ''}."
                if result["scan_incomplete"]:
                    answer += " The scan was limited; this count covers only the entries searched."
                if result["results"]:
                    answer += f" The closest is {result['results'][0]['filename']}."
                self.message("local", answer)
                self.set_state("IDLE", task=None)
            else:
                self.fail(result["error"])
            return result

    async def text(self, text):
        async with self.lock:
            self.message("user", text)
            self.set_state("THINKING", task=text[:100])
            if not self.provider:
                self.message("system", "Online reasoning is not configured. Local tools remain available, sir.")
                self.set_state("WAITING_FOR_USER", task=None)
                return
            try:
                answer = await self.provider.generate(text, self.handle_tool_call)
                self.message("assistant", spoken_text(answer))
                self.set_state("IDLE", task=None, provider_status="connected")
            except ProviderUnavailable as exc:
                self.set_state(provider_status="unavailable")
                self.fail(str(exc))

    def interrupt(self):
        self.state["speech_id"] += 1
        self.set_state("INTERRUPTED", lumina_speaking=False, user_speaking=False, current_tool=None)
        self.broadcast({"type": "interrupt", "speech_id": self.state["speech_id"]})

    def close_session_log(self):
        self.memory_operation('consolidate', session_id=self.session_id)
        self.session_log.close()

