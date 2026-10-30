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
from .control_authority import ControlAuthority
from .memory import MemoryStore
from .session_log import SessionLog
from .greeting import clear_ended, default_state_path, greeting_for, write_ended
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
        self.control_authority = ControlAuthority(config.runtime_root / '.lumina-control-unresolved.json')
        self.owned_window = None
        self.owned_controller = None
        self.owned_client = None
        self.owned_opening = False
        self.window_views = {}
        self.external_adapter = self.external_controller = self.external_owner = None
        self.receiver_adapter = self.receiver_controller = self.receiver_owner = None
        self._native_fixture_session = None
        self.control_authority.register_revoker(lambda reason: self.window_views.clear())
        self.index = FileIndex(config)
        self.session_log = SessionLog(config.runtime_root)
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
        self.tools = ToolRegistry(self.index, self.memory, authority=self.control_authority)
        self.tools.memory_context = self.memory_context
        self.tools.runtime = self
        self.auto_memory_capture = getattr(config, 'auto_memory_capture', True)
        if hasattr(self.memory, 'rt'):
            self.memory.rt = self
        reminders_tz = getattr(getattr(self.tools, 'reminders', None), 'timezone', None)
        if reminders_tz and hasattr(self.memory, 'timezone'):
            self.memory.timezone = reminders_tz
        self.continuity_commands = ContinuityCommands(self)
        self._continuity_workspace = None
        self.sync_memory_workspace()
        from .charter import CharterManager
        self.charter = CharterManager(self.memory)
        self.charter.verify_and_audit()
        self.session_log.write('runtime.initialized', provider=config.provider, worker=config.worker,
                               workspace=str(config.root), memory_path=str(self.memory.path) if self.memory.path else None,
                               memory_status=self.memory_operation('status').get('status'))
        # M4 never constructs a live worker implicitly; explicit injections are
        # inventoried by TaskManager, but launch/resume remain denied.
        if workers is None:
            workers = {}
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
        self.tools.brain_dump.on_change = lambda event: self.broadcast(event)
        self.proactive_dump_capture = False
        self.tools.phase2.busy = lambda: (not self.clients or self.lock.locked() or
            self.state.get('user_speaking') or self.state.get('lumina_speaking') or
            self.state.get('state') in {'LISTENING','THINKING','EXECUTING','SPEAKING','WAITING_FOR_USER'})
        self.agent_summary_tasks = set()
        self.audit = []
        self.tasks = TaskManager(workers, self.agent_event, brief_spoken_text,
                                 on_continuity=self.continuity_task, authority=self.control_authority)
        self.tools.worker_status=lambda:[{k:v for k,v in s.items() if k not in {'output','events'}} for s in self.worker_sessions()]
        self.tools.agent_tail=self.read_agent_tail
        self.tools.spawn_agent=self.start_coding_agent
        self.delegation_request=None
        self.last_uploaded_file=None
        self.greeting_path = Path(getattr(config,'greeting_path','') or default_state_path())
        self.greeting_pending = bool(getattr(config,'greetings_enabled',True))
        self.greeting_delivered = False
        self.session_started = False
        for worker in self.tasks.workers.values():
            if hasattr(worker,'manager'): worker.manager.on_event=self.worker_event

    def native_fixture_session(self, principal):
        """Trusted local Python owner only; no HTTP, model, health or client-ID path.

        The capability proves this Runtime/session binding, not human identity.
        It admits only the fixed disposable process family; startup stays disarmed.
        """
        from .native_process import NativeFixtureSession
        if type(principal) is not object or self._native_fixture_session is not None:
            raise PermissionError('native_fixture_owner_required')
        session = NativeFixtureSession(self, principal)
        self._native_fixture_session = session
        return session

    def simulation_controller(self, observations, adapter, *, owner):
        """Trusted offline injection only; no tool or HTTP registration."""
        from .computer_control import IsolatedComputerControl
        if not isinstance(owner, str) or not owner:
            raise ValueError('An approval owner is required')
        return IsolatedComputerControl(observations, adapter,
            authority=self.control_authority, owner=owner)

    def practice_input_session(self, principal):
        """Trusted local P2.2 test enrollment only; no HTTP/model registration."""
        from .practice_input import PracticeSession
        if getattr(self, '_practice_input_session', None) is not None:
            raise PermissionError('practice_session_already_created')
        session = PracticeSession(self, principal)
        self._practice_input_session = session
        return session

    async def close_practice_fixture(self):
        session = getattr(self, '_practice_input_session', None)
        if session is not None and not await session.close():
            self.control_authority.note_external_uncertainty()
            raise RuntimeError('practice_cleanup_unconfirmed')

    def simulation_desktop_task(self, observations, adapter, raw, *, owner, target,
                                expected_digest, goal_predicate, controller=None,
                                binding=None, allow_reground=False):
        """Offline harness only; deliberately absent from HTTP/model registries.

        One typed proposal, existing confirmations/task lifecycle, no native
        fallback. Does not arm the authority or grant approval on creation.
        """
        from .computer_use import SimulatedDesktopTask
        goal = SimulatedDesktopTask(self, observations, adapter, raw, owner=owner,
            target=target, expected_digest=expected_digest, goal_predicate=goal_predicate,
            controller=controller, binding=binding, allow_reground=allow_reground)
        self.tasks.create_goal(goal)
        return goal

    async def goal_request(self, connection, body):
        """Explicit local UI scope only. Never registered as a model action."""
        from .goals import LocalGoal
        action=body.get('action')
        if action=='goal_prepare' and set(body)<={'action','kind','text','planning'}:
            goal=LocalGoal(self,connection,body.get('kind','clarify'),
                           text=body.get('text',''),planning=body.get('planning','local'))
            self.tasks.create_goal(goal)
        else:
            required={'action','task_id','confirmation_id'} if action=='goal_approve' else {'action','task_id'}
            if action not in {'goal_review','goal_approve','goal_pause','goal_cancel','goal_status'} or set(body)!=required:
                raise ValueError('invalid_goal_request')
            session=self.tasks._get(body['task_id'])
            goal=session.goal
            if goal is None or goal.owner!=connection.client_id:
                raise PermissionError('goal_owner_mismatch')
            if action=='goal_approve':
                if type(body['confirmation_id']) is not str:raise ValueError('invalid_confirmation')
                return {'ok':True,'task':goal.approve(body['confirmation_id'])}
            if action in {'goal_pause','goal_cancel'}:
                return {'ok':True,'task':self.tasks.stop_goal(session.id,owner=connection.client_id,
                    cancel=action=='goal_cancel')}
            if action=='goal_status':return {'ok':True,'task':self.tasks.read_agent_session(session.id)}
        try:
            return await goal.review()
        except PermissionError as exc:
            goal.reason=str(exc)
            self.tasks._emit(goal.session)
            return {'ok':False,'reason':goal.reason,'task':self.tasks.read_agent_session(goal.session.id)}

    async def goal_chat(self, connection, text):
        clean=text.strip()
        control=re.fullmatch(r'(pause|resume|cancel|status) goal ([a-f0-9]{32})[.!]?',clean,re.I)
        if control:
            action={'pause':'goal_pause','resume':'goal_review','cancel':'goal_cancel','status':'goal_status'}[control[1].lower()]
            body={'action':action,'task_id':control[2].lower()}
        elif clean.lower().startswith('goal:'):
            request=clean[5:].strip()
            write=re.fullmatch(r'write and select scratchpad text:\s*(.*)',request,re.I|re.S)
            body={'action':'goal_prepare','kind':'scratchpad_text' if write else
                  'inspect_window' if request.lower().rstrip('.!?')=='inspect selected window' else 'clarify'}
            if write:body['text']=write[1]
        else:return False
        result=await self.goal_request(connection,body)
        # Literal scratchpad content stays in the owner's private review, not chat history/model context.
        self.message('user','Local goal request: '+body['action'],capture_memory=False)
        self.message('assistant','Review the exact task scope in Controls before starting.' if result.get('review') else
            'Goal status: '+str(result.get('reason') or result.get('task',{}).get('status','unavailable'))+'.',capture_memory=False)
        self.broadcast({'type':'goal_review','client_id':connection.client_id,'data':result})
        return True

    async def inspect_windows(self, connection, body):
        """Existing structured inspection plus optional local perception context.

        No pixels, OCR, provider call, inferred visual match or stored UI text.
        Structured inspection remains useful when screen sharing is unavailable.
        """
        action = body.get('action')
        stream = getattr(getattr(connection, 'screen_share', None), 'observations', None)
        evidence = None
        if stream is not None and stream.latest() is not None:
            current = stream.latest()
            evidence = stream.evidence(session_id=current.session_id, minimum_sequence=current.sequence)
        result = await self._inspect_windows(connection, body)
        if (result.get('ok') and action in {'list', 'select', 'refresh', 'control'} and
                evidence is not None and not evidence.valid(stream.clock())):
            self.window_views.pop(connection.client_id, None)
            result = {'ok': False, 'error': 'observation_changed_during_inspection'}
        return {**result, 'inspection_action': action, 'capabilities': self.interaction_capabilities(),
                'perception': stream.status() if stream is not None else {'observation': 'unavailable', 'analysis': 'disabled'},
                'evidence': ({'kind': 'structured_ui_with_recent_observation',
                             'session_id': evidence.session_id, 'source_id': evidence.source_id,
                             'sequence': evidence.sequence, 'visual_match_verified': False}
                            if result.get('ok') and evidence is not None else {'kind': 'structured_ui_only'}),
                'message': self.inspection_message(result)}

    @staticmethod
    def interaction_capabilities():
        return {'window_inspection': 'read_only', 'scratchpad': 'owned_surface_only',
                'third_party_mutation': 'disabled_effect_boundary_unverified',
                'file_mutation': 'disabled', 'shell': 'disabled', 'raw_input': 'disabled',
                'uia_toggle': 'disabled', 'browser_mutation': 'disabled'}

    @staticmethod
    def inspection_message(result):
        messages = {
            'observation_changed_during_inspection': 'Screen evidence expired or sharing changed during inspection. Refresh before using this result.',
            'window_inventory_expired': 'The window list expired. Find windows again.',
            'window_not_discovered': 'Choose a window from your current window list.',
            'control_not_discovered': 'Choose a control from the current inspection.',
            'window_identity_changed': 'The selected window changed. Find windows again.',
            'ambiguous_target': 'The inspection returned duplicate target identities. No target was selected.',
            'inspection_revoked': 'Inspection was stopped or replaced. Resume read-only inspection to continue.',
            'inspection_suspended': 'Control is stopped. Resume read-only inspection to continue.',
            'inspection_timeout': 'Window inspection timed out. No action was performed.',
            'timeout': 'Window inspection timed out. No action was performed.',
            'provider_failed': 'Windows inspection is unavailable. No action was performed.',
        }
        error = result.get('error')
        if error: return messages.get(error, 'This inspection is unavailable. No action was performed.')
        if 'windows' in result: return f"Found {len(result['windows'])} windows. Choose one to inspect; selecting it does not focus or change it."
        if 'controls' in result: return f"Read {len(result['controls'])} accessible controls. Editable values are redacted. No application change was performed."
        return {'admission_stopped': 'Control stopped; screen sharing continues.',
                'inspection_resumed': 'Read-only inspection resumed; application changes remain disabled.',
                'inspection_resume_blocked': 'Inspection cleanup is still pending.',
                'selection_cleared': 'Window selection cleared.'}.get(result.get('status'), '')

    async def window_chat(self, connection, text):
        """Exact local user commands, not screen instructions or model grants."""
        clean = text.strip().lower().rstrip('.!?')
        commands = {'list windows': 'list', 'inspect windows': 'list',
                    'inspect selected window': 'refresh', 'refresh window controls': 'refresh',
                    'resume window inspection': 'resume'}
        numbered = re.fullmatch(r'inspect window ([1-9][0-9]{0,2})', clean)
        if clean not in commands and numbered is None: return False
        body = {'action': commands.get(clean, 'select')}
        if numbered:
            view = self.window_views.get(connection.client_id, {})
            rows = view.get('ordered_windows', [])
            index = int(numbered[1]) - 1
            body['window'] = rows[index] if index < len(rows) else ''
        self.message('user', text, capture_memory=False)
        result = await self.inspect_windows(connection, body)
        answer = result['message']
        if result.get('windows'):
            answer += ' Use Inspect Windows to view names, or say “inspect window 1” for the first result.'
        if result.get('ok') and 'controls' in result:
            roles = sorted({str(row.get('role', 'unknown'))[:60] for row in result['controls']})
            # Fixed counts only in conversation history. UI labels stay in the
            # requesting client's transient dialog; no new memory/transmission.
            answer += f' {len(roles)} control types were reported.'
        perception = result['perception']
        if body['action'] in {'list', 'select', 'refresh'}:
            answer += (' A recent shared observation is available; this answer uses structured UI data, not model vision.'
                       if result.get('evidence', {}).get('kind') == 'structured_ui_with_recent_observation'
                       else ' No fresh shared image was used; this is structured UI inspection only.')
        self.message('assistant', answer, capture_memory=False)
        self.broadcast({'type': 'window_inspection', 'client_id': connection.client_id, 'data': result})
        return True

    async def _inspect_windows(self, connection, body):
        """Client-owned read-only selection. Never grants action/focus authority."""
        import os
        action = body.get('action')
        if isinstance(action,str) and action.startswith('external_'):
            return await self.external_fixture_action(connection,body)
        if isinstance(action,str) and action.startswith('receiver_'):
            return await self.receiver_fixture_action(connection,body)
        required = ({'action', 'window'} if action == 'select' else
                    {'action', 'control'} if action == 'control' else {'action'})
        optional = {'scope'} if action == 'list' else set()
        if (action not in {'list', 'select', 'refresh', 'control', 'clear', 'resume', 'stop', 'takeover'} or
                set(body) - required - optional or required - set(body)):
            raise ValueError('invalid_window_inspection')
        owner = connection.client_id
        authority = self.control_authority
        if action in {'stop', 'takeover'}:
            authority.stop('user_takeover' if action == 'takeover' else 'emergency_stop')
            return {'ok': True, 'status': 'admission_stopped', 'perception_stopped': False,
                    'inspections_pending': authority.status()['inspections_pending'],
                    **({'receiver':self.receiver_adapter.status()} if self.receiver_adapter is not None else {})}
        authority.cancel_inspections(owner)
        if action == 'clear':
            self.window_views.pop(owner, None)
            return {'ok': True, 'status': 'selection_cleared'}
        if action == 'resume':
            self.window_views.pop(owner, None)
            resumed = authority.resume_inspection()
            return {'ok': resumed, 'read_only': True,
                    'status': 'inspection_resumed' if resumed else 'inspection_resume_blocked',
                    'mutation_supported': False}
        if authority.mode == 'closed':
            return {'ok': False, 'error': 'runtime_closed'}
        service = self.tools.phase2.services['computer_control']
        # Request identity prevents a slow prior response replacing a newer selection.
        previous = self.window_views.get(owner)
        if action == 'list':
            scope = body.get('scope', 'external_fixture' if self.external_owner == owner else 'desktop')
            if scope not in {'desktop', 'scratchpad', 'external_fixture'}:
                raise ValueError('invalid_window_scope')
            if scope == 'scratchpad' and (self.owned_client != owner or self.owned_window is None):
                return {'ok': False, 'error': 'owned_window_owner_mismatch'}
            if scope == 'external_fixture' and (self.external_owner != owner or self.external_adapter is None):
                return {'ok': False, 'error': 'external_fixture_not_registered_for_client'}
            if owner not in self.window_views and len(self.window_views) >= 64:
                return {'ok': False, 'error': 'inspection_capacity'}
            view = {'windows': set(), 'controls': set(), 'selected': None, 'at': time.monotonic()}
            arguments = ({'process_id': os.getpid()} if scope == 'scratchpad' else
                         {'process_id': self.external_adapter.registration.pid} if scope == 'external_fixture' else {})
            operation = 'list_windows'
        else:
            if previous is None or not 0 <= time.monotonic() - previous['at'] < 60:
                self.window_views.pop(owner, None)
                return {'ok': False, 'error': 'window_inventory_expired'}
            selected = body.get('window') if action == 'select' else previous['selected']
            if not isinstance(selected, str) or selected not in previous['windows']:
                return {'ok': False, 'error': 'window_not_discovered'}
            view = {**previous, 'selected': selected}
            arguments, operation = {'window': selected}, 'inspect'
            if action == 'control':
                control = body['control']
                if not isinstance(control, str) or control not in previous.get('controls', set()):
                    return {'ok': False, 'error': 'control_not_discovered'}
                arguments['control'], operation = control, 'inspect_control'
        self.window_views[owner] = view
        boundary = (authority.epoch, authority.generation)
        from .control_authority import inspection_owner
        owner_token = inspection_owner.set(owner)
        try:
            # The request owns this bounded read; cancellation propagates to the
            # existing provider's kill/reap finally. It is not an effect-producing
            # authority job and must not quarantine an unrelated verified action.
            result = await service.execute(operation, **arguments)
        except BaseException:
            if self.window_views.get(owner) is view:
                self.window_views.pop(owner, None)
            raise
        finally:
            inspection_owner.reset(owner_token)
        if (self.window_views.get(owner) is not view or
                boundary != (authority.epoch, authority.generation) or authority.mode == 'closed'):
            return {'ok': False, 'error': 'inspection_revoked'}
        if not result.get('ok'):
            self.window_views.pop(owner, None)
            return {'ok': False, 'error': result.get('error', 'inspection_unavailable')}
        if action == 'list':
            rows = result.get('windows', [])[:128]
            if len({row['id'] for row in rows}) != len(rows):
                self.window_views.pop(owner, None)
                return {'ok': False, 'error': 'ambiguous_target'}
            view['windows'] = {row['id'] for row in rows}
            view['ordered_windows'] = [row['id'] for row in rows]
            view['at'] = time.monotonic()
            return {'ok': True, 'windows': rows, 'read_only': True, 'limit': 128}
        if result.get('window') != view['selected']:
            self.window_views.pop(owner, None)
            return {'ok': False, 'error': 'window_identity_changed'}
        controls = result.get('controls', [])
        if len({row['id'] for row in controls}) != len(controls):
            self.window_views.pop(owner, None)
            return {'ok': False, 'error': 'ambiguous_target'}
        view['controls'] = {row['id'] for row in controls}
        # Do not expose legacy snapshot tokens as a new mutation capability.
        public = {k: v for k, v in {**result, 'read_only': True,
                'mutation_supported': False}.items() if k != 'snapshot'}
        adapter = self.external_adapter
        if adapter is not None and self.external_owner == owner and view['selected'].startswith(
                f'{adapter.registration.window}:{adapter.registration.pid}:'):
            public['fixture_controls'] = [row['id'] for row in result.get('controls', [])
                                         if row.get('native_hwnd') == adapter.registration.control]
            public['fixture_buttons'] = [{'id':row['id'],'operation':adapter.button_operations()[row['native_hwnd']]}
                                         for row in result.get('controls',[]) if row.get('native_hwnd') in adapter.button_operations()]
            from .fixture_toggle import NATIVE_TOGGLE_READY
            public['fixture_toggles'] = [row['id'] for row in result.get('controls',[])
                if NATIVE_TOGGLE_READY and adapter.registration.toggle is not None and row.get('native_hwnd')==adapter.registration.toggle]
            if adapter.registration.toggle is not None and not NATIVE_TOGGLE_READY:
                public['toggle_unavailable']='Native checkbox control is not validated; inspection remains available.'
        return public

    def register_external_fixture(self, connection, process, registration):
        """Trusted isolated-harness injection only. No HTTP/tool enrollment route.

        This does not arm control or resolve existing uncertainty. The caller
        owns creation and cleanup of the independent disposable process.
        """
        from .external_windows import ExternalWindowsAdapter
        from .computer_control import IsolatedComputerControl
        if self.external_adapter is not None or self.control_authority.quarantined:
            raise PermissionError('external_registration_unavailable')
        adapter = ExternalWindowsAdapter(self.control_authority,connection.screen_share.observations,
                    self.tools.phase2.services['computer_control'],process,registration)
        self.external_adapter = adapter
        self.external_owner = connection.client_id
        self.external_controller = IsolatedComputerControl(adapter.observations,adapter,
                    authority=self.control_authority,owner=connection.client_id,timeout=5)
        return adapter

    async def external_fixture_action(self, connection, body):
        from .external_windows import INITIAL, EDITED, digest
        adapter,core = self.external_adapter,self.external_controller
        if adapter is None or core is None or connection.client_id != self.external_owner:
            return {'ok':False,'error':'external_fixture_not_registered_for_client'}
        action=body.get('action')
        edit_proposal=action=='external_propose' and set(body)=={'action','control','restore'} and type(body['restore']) is bool
        button_proposal=action=='external_button_propose' and set(body)=={'action','control','operation'} and body['operation'] in ('increment_external_fixture','reset_external_fixture')
        toggle_proposal=action=='external_toggle_propose' and set(body)=={'action','control'}
        if toggle_proposal:
            from .fixture_toggle import NATIVE_TOGGLE_READY
            if not NATIVE_TOGGLE_READY:return {'ok':False,'error':'native_toggle_not_validated'}
        if edit_proposal or button_proposal or toggle_proposal:
            view=self.window_views.get(connection.client_id)
            if (view is None or not 0 <= time.monotonic()-view['at'] < 60 or
                    not isinstance(body['control'],str) or body['control'] not in view.get('controls',set())):
                return {'ok':False,'error':'external_control_not_discovered'}
            self.control_authority.check()
            await adapter.refresh(view['selected'],body['control'])
            if toggle_proposal:
                expected=adapter.toggle_postcondition(adapter.current_value)
                prepared=core.propose('toggle_external_fixture',adapter.target,expected_digest=digest(expected))
                return {**prepared,'review':{'window':adapter.target.window_id,'control':adapter.target.control_id,
                    'operation':'toggle_external_fixture','before':adapter.current_value,'after':expected,
                    'scope':'registered disposable checkbox only; restoration requires separate approval'}}
            if button_proposal:
                operation=body['operation']
                expected=adapter.button_postcondition(operation,adapter.current_value)
                prepared=core.propose(operation,adapter.target,expected_digest=digest(expected))
                return {**prepared,'review':{'window':adapter.target.window_id,'control':adapter.target.control_id,
                    'operation':operation,'before':adapter.current_value,'after':expected,
                    'scope':'registered disposable counter only'}}
            value=INITIAL if body['restore'] else EDITED
            prepared=core.propose('set_external_fixture',adapter.target,expected_digest=digest(value),text=value)
            return {**prepared,'review':{'window':adapter.target.window_id,'control':adapter.target.control_id,
                                        'value':value,'scope':'registered disposable test field only'}}
        if action=='external_approve' and set(body)=={'action','action_id','confirmation','request'}:
            if not all(isinstance(body[k],str) for k in ('action_id','confirmation')) or not isinstance(body['request'],dict):
                raise ValueError('invalid_external_approval')
            try: pending=core.snapshot(body['action_id'])
            except KeyError: return {'ok':False,'error':'unknown_action'}
            if pending['state']!='awaiting_approval':
                return {'ok':False,'error':'approval_not_pending'}
            accepted=core.approve(body['action_id'],body['confirmation'],body['request'],owner=connection.client_id)
            if accepted.get('state')!='approved': return accepted
            return await core.execute('execute_confirmed',action_id=body['action_id'],request=body['request'])
        if action=='external_deny' and set(body)=={'action','action_id'} and isinstance(body['action_id'],str):
            core.cancel_action(body['action_id'])
            return {'ok':True,'status':'proposal_cancelled'}
        if action=='external_status' and set(body)=={'action','action_id'} and isinstance(body['action_id'],str):
            try:result=core.snapshot(body['action_id'])
            except KeyError:return {'ok':False,'error':'unknown_action'}
            return {key:result[key] for key in ('action_id','state','reason','outcome','semantic','cancellation','cleanup')}
        raise ValueError('invalid_external_request')

    async def close_external_fixture(self):
        if self.external_adapter is None: return {'ok':True,'settled':True}
        self.control_authority.stop()
        await self.external_controller.close()
        result=await self.external_adapter.close()
        if result['settled']:
            self.external_adapter=self.external_controller=self.external_owner=None
        return result

    async def register_receiver_fixture(self, connection, process, registration):
        """Trusted disposable-harness injection; never an HTTP/model enroll API."""
        from .receiver_adapter import ReceiverAdapter
        from .computer_control import IsolatedComputerControl
        if self.receiver_adapter is not None or self.control_authority.quarantined:
            raise PermissionError('receiver_registration_unavailable')
        adapter=ReceiverAdapter(self.control_authority,connection.screen_share.observations,
                                process,registration,owner=connection.client_id)
        self.receiver_adapter,self.receiver_owner=adapter,connection.client_id
        self.receiver_controller=IsolatedComputerControl(adapter.observations,adapter,
                                    authority=self.control_authority,owner=connection.client_id)
        await adapter.open()
        return adapter

    async def receiver_fixture_action(self, connection, body):
        from .receiver_adapter import digest
        from .receiver_protocol import OPERATION
        adapter,core=self.receiver_adapter,self.receiver_controller
        if adapter is None or core is None or connection.client_id!=self.receiver_owner:
            return {'ok':False,'error':'receiver_not_registered_for_client'}
        action=body.get('action')
        if action in ('receiver_inspect','receiver_propose') and set(body)=={'action'}:
            state=await adapter.refresh()
            if action=='receiver_inspect':return {'ok':True,'fixture':adapter.registration.fixture,'state':state}
            after=dict(value='ready',revision=state['revision']+1)
            result=core.propose(OPERATION,adapter.target,expected_digest=digest(after))
            return {**result,'review':{'operation':OPERATION,'fixture':adapter.registration.fixture,
                    'before':state,'after':after,'scope':'disposable receiver only'}}
        if action=='receiver_approve' and set(body)=={'action','action_id','confirmation','request'}:
            if not all(isinstance(body[k],str) for k in ('action_id','confirmation')) or not isinstance(body['request'],dict):
                raise ValueError('invalid_receiver_approval')
            try:pending=core.snapshot(body['action_id'])
            except KeyError:return {'ok':False,'error':'unknown_action'}
            if pending['state']!='awaiting_approval':
                return {'ok':False,'error':'approval_not_pending'}
            accepted=core.approve(body['action_id'],body['confirmation'],body['request'],owner=connection.client_id)
            if accepted.get('state')!='approved':return accepted
            return await core.execute('execute_confirmed',action_id=body['action_id'],request=body['request'])
        if action in ('receiver_status','receiver_deny','receiver_reconcile') and set(body)=={'action','action_id'} and isinstance(body['action_id'],str):
            if body['action_id'] not in core._actions:return {'ok':False,'error':'unknown_action'}
            if action=='receiver_deny':core.cancel_action(body['action_id'])
            if action=='receiver_reconcile':
                # Evidence only: cannot resume, retry, alter terminal action or clear quarantine.
                return await adapter.reconcile(core._actions[body['action_id']].spec)
            return {**core.snapshot(body['action_id']),'receiver':adapter.status()}
        raise ValueError('invalid_receiver_request')

    async def close_receiver_fixture(self):
        if self.receiver_adapter is None:return {'ok':True,'settled':True}
        self.control_authority.stop()
        await self.receiver_controller.close()
        result=await self.receiver_adapter.close()
        if result['settled']:
            self.receiver_adapter=self.receiver_controller=self.receiver_owner=None
        return result

    async def owned_window_action(self, connection, body):
        """Explicit application UI only. No model registration or arbitrary target.

        Low-risk policy: at most 2048 literal characters on our ephemeral surface.
        HTTP token is CSRF protection, never evidence of human authentication.
        """
        from .owned_windows import OwnedWindowsAdapter, text_digest
        from .computer_control import IsolatedComputerControl
        action = body.get('action')
        if set(body) != ({'action', 'text'} if action == 'set_text' else {'action'}):
            raise ValueError('invalid_owned_request')
        if action == 'open':
            if self.owned_window is not None or self.owned_opening:
                return {'ok': False, 'error': 'owned_window_already_open'}
            if self.control_authority.quarantined or self.control_authority.mode == 'closed':
                return {'ok': False, 'error': 'unresolved_control_state'}
            if connection.screen_share.observations.latest() is None:
                return {'ok': False, 'error': 'fresh_shared_observation_required'}
            self.owned_opening = True
            adapter = OwnedWindowsAdapter(self.control_authority, connection.screen_share.observations,
                                           arm=self.arm_owned_window)
            self.owned_window, self.owned_client = adapter, connection.client_id
            try:
                result = await adapter.open()
                self.owned_controller = IsolatedComputerControl(adapter.observations, adapter,
                    authority=self.control_authority, owner=connection.client_id, timeout=8)
                return {**result, 'armed': False,
                        'message': 'Use Enable local scratchpad in the native window. Other applications remain disabled.'}
            except BaseException:
                await self.close_owned_window()
                raise
            finally:
                self.owned_opening = False
        if self.owned_client != connection.client_id or self.owned_window is None:
            return {'ok': False, 'error': 'owned_window_owner_mismatch'}
        if action == 'stop':
            self.control_authority.stop()
            return {'ok': True, 'status': 'admission_stopped', 'perception_stopped': False,
                    'unresolved': self.control_authority.status()['unresolved'],
                    'receiver_pending': sum(not f.done() for f in self.owned_window.pending)}
        if action == 'close':
            return await self.close_owned_window()
        if action == 'status':
            return {'ok': True, 'control': self.control_authority.status(),
                    'closed': self.owned_window.closed.is_set(), 'scope': 'owned_window_only'}
        if action not in {'set_text', 'clear', 'select_all'}:
            raise ValueError('invalid_owned_request')
        text = body.get('text') if action == 'set_text' else None
        if action == 'set_text' and (not isinstance(text, str) or len(text) > 2048 or '\x00' in text):
            raise ValueError('invalid_owned_request')
        core, adapter = self.owned_controller, self.owned_window
        if core is None:
            return {'ok': False, 'error': 'owned_window_not_ready'}
        self.control_authority.check()
        observed = await adapter.inspect()
        operation = {'set_text': 'set_owned_text', 'clear': 'clear_owned_text', 'select_all': 'select_owned_text'}[action]
        expected = observed['select_all_digest'] if action == 'select_all' else text_digest(text if text is not None else '')
        proposal = core.propose(operation, adapter.target, expected_digest=expected, text=text)
        # Derived policy applies only to this exact nonpersistent owned surface.
        # No consequential/sensitive operation can enter through this endpoint.
        core.approve(proposal['action_id'], proposal['confirmation'], proposal['request'], owner=self.owned_client)
        return await core.execute('execute_confirmed', action_id=proposal['action_id'], request=proposal['request'])

    def arm_owned_window(self):
        core = self.owned_controller
        if core is None or self.owned_window.closed.is_set() or core.observations.latest() is None:
            return False
        if core.mode != 'running':
            return core.resume()['ok']
        return self.control_authority.resume()

    async def close_owned_window(self):
        self.control_authority.stop()
        if self.owned_controller:
            await self.owned_controller.close()
        result = await self.owned_window.close() if self.owned_window else {'ok': True, 'settled': True}
        # Retain uncertain ownership rather than replacing it with a fresh window.
        if result['settled']:
            self.owned_window = self.owned_controller = self.owned_client = None
        return result

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
            if operation in {'propose','remember','correct','consolidate','continuation','forget','reject_candidate','defer_candidate','daily_reflection'}:
                self.session_log.write('continuity.'+operation,ok=result.get('ok') if isinstance(result,dict) else None,
                    decision=result.get('decision') if isinstance(result,dict) else None)
            return result
        except ValueError as exc:
            return {'ok': False, 'error': str(exc)}
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

    def process_memory_message(self, text, source_event_id=None):
        """Processes incoming user message through multi-chunk extraction and manifest tracking."""
        import hashlib
        from .continuity.chunker import MessageChunker
        from .continuity.manifest import ExtractionManifest
        from .continuity.extractor import MemoryExtractor

        source_id = source_event_id or self.last_user_event_id
        if not source_id:
            source_id = self.capture_user_evidence(text)
        if not source_id:
            return {'ok': False, 'error': 'Could not record user evidence.'}

        chunker = MessageChunker(target_chars=800, max_chars=1400, overlap_chars=100)
        chunks = chunker.chunk_message(text, message_id=str(self.message_id))
        if not chunks:
            return {'ok': True, 'count': 0, 'candidates': []}

        manifest = ExtractionManifest.create_from_chunks(
            str(self.message_id),
            hashlib.sha256(text.encode()).hexdigest()[:12],
            chunks,
            repo=getattr(self.memory, 'repo', None)
        )

        extractor = MemoryExtractor(user_id=getattr(self.memory, 'user_id', 'local-user'))
        chunk_candidate_batches = []

        for chunk in chunks:
            manifest.start_chunk(chunk.chunk_id)
            try:
                candidates = extractor.extract_candidates_from_text(
                    chunk.text,
                    source_event_id=source_id,
                    chunk_index=chunk.index,
                    source_span=(chunk.start_char, chunk.end_char)
                )
                chunk_candidate_batches.append(candidates)
                manifest.record_chunk_result(chunk.chunk_id, candidate_ids=[c.get('predicate', '') for c in candidates])
            except Exception as exc:
                manifest.record_chunk_result(chunk.chunk_id, error=str(exc))

        reconciled = extractor.reconcile_candidates(chunk_candidate_batches)
        if not reconciled:
            manifest.status = 'completed'
            manifest.persist()
            return {'ok': True, 'count': 0, 'manifest': manifest.get_summary()}

        prop_res = self.tools.continuity.execute('memory_propose', {'proposals': reconciled}, online=False)
        manifest.status = 'completed'
        manifest.persist()
        return {
            'ok': prop_res.get('ok', True),
            'proposals': reconciled,
            'result': prop_res,
            'manifest': manifest.get_summary()
        }

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
        if data.get('kind')=='local_goal':
            # Same task event channel, no task contents sent to memory or spoken summaries.
            self.audit_event('local_goal',data['status'].lower(),task_id=data['task_id'])
            self.broadcast(event)
            return
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
            pending=[key for key,value in self.tools.pending.items() if value['expires']>time.monotonic()
                     and self.tools.spoken_confirmation_allowed(key)]
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
            result=await self.tools.confirm(confirmation_id, owner=output_client)
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
        return {**self.state, "graph_revision": self.graph["revision"], "messages": self.messages[-40:],
                "control_safety": self.control_authority.status()}

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

    def record_normal_end(self):
        """A confirmed clean shutdown is the only source of a return greeting."""
        self.greeting_pending = False
        return write_ended(self.greeting_path, datetime.now().astimezone())

    def deliver_greeting(self):
        """At most one greeting per application session; reconnects cannot repeat it.

        Eligibility (time band and 30-minute return window) is evaluated here,
        at delivery time, using the actual local time — never at boot, so a
        delayed first connection cannot produce a stale greeting.

        The greeting text is always surfaced in the conversation and queued as
        an announcement. Spoken delivery through the configured TTS pipeline is
        attempted by the owning WebSocket connection (see ``VoiceConnection``);
        a failure to speak preserves the text and is logged once, never retried.
        """
        if self.greeting_delivered or not self.greeting_pending:
            return None
        text = greeting_for(self.greeting_path, datetime.now().astimezone())
        self.greeting_delivered = True
        self.session_log.write('greeting.delivered', text=text)
        self.message('assistant', text, capture_memory=False)
        self.queue_announcement(text)
        if text == 'Welcome back, sir.':
            clear_ended(self.greeting_path)
        return text

