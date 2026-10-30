"""Local, provider-neutral task coordination. Adapters receive no OS authority here."""
from .control_authority import blocked_effect
import asyncio
from dataclasses import dataclass, field
from typing import Callable, Protocol
from uuid import uuid4
import time


@dataclass(frozen=True)
class WorkerResult:
    text: str
    summary: str
    needs_input: bool = False
    goal_status: str | None = None


class WorkerAdapter(Protocol):
    """Configured adapters must enforce the runtime's permission policy themselves."""

    async def run(self, session_id: str, message: str) -> WorkerResult: ...
    async def send_message(self, session_id: str, message: str) -> None: ...
    async def cancel(self, session_id: str) -> None: ...


@dataclass
class _Session:
    id: str
    worker: str
    status: str = "RUNNING"
    summary: str = ""
    result: str | None = None
    messages: list[str] = field(default_factory=list)
    runner: asyncio.Task | None = None
    workspace: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    cleanup_binding: object = None
    cleanup_task: asyncio.Task | None = None
    cleanup_worker: asyncio.Task | None = None
    cleanup_grant: object = None
    goal: object = None


class TaskManager:
    """Starts only at a trusted, explicitly authorized user-action boundary.

    Do not expose the authorized flag as a model-controlled tool argument.
    No adapter is created, downloaded, or selected implicitly.
    """

    def __init__(self, workers: dict[str, WorkerAdapter] | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 format_summary: Callable[[str], str] | None = None,
                 on_continuity: Callable[[dict], None] | None = None, *, authority=None):
        from .control_authority import ControlAuthority
        self.authority = authority if authority is not None else ControlAuthority()
        self.workers = dict(workers or {})
        self._sessions: dict[str, _Session] = {}
        self.on_event = on_event
        self.format_summary = format_summary
        self.on_continuity = on_continuity
        self.cleanup_timeout = 5.0
        self._closing = False
        self.authority.register_revoker(lambda reason: self.stop_goals(reason=reason))
        # Do not restore or launch independent workers in the fake-only milestone.
        # Conservatively retain uncertainty, including records from older runs.
        if any(getattr(adapter, 'records', {}) or getattr(adapter, 'processes', {})
               for adapter in self.workers.values()):
            self.authority.note_external_uncertainty()

    @blocked_effect
    def _restore_workers(self):
        for name,adapter in self.workers.items():
            if getattr(adapter,'persistent',False):
                for task_id,record in adapter.records.items():
                    adapter.restore(task_id)
                    status=record.get('task_status') or {'CANCELLED':'CANCELLED','TERMINATED':'CANCELLED','FAILED':'ERROR','COMPLETED':'COMPLETED','WAITING':'WAITING_FOR_USER'}.get(record.get('status'),'RUNNING')
                    if record.get('status') in {'CANCELLED','TERMINATED'}:status='CANCELLED'
                    self._sessions[task_id]=_Session(task_id,name,status=status,summary=record.get('summary',''),messages=[record['instruction']],workspace=record['workspace'],completed_at=record.get('completed_at'))

    @blocked_effect
    async def restore_monitors(self):
        for session in self._sessions.values():
            self._observe(session)
            if getattr(self.workers[session.worker],'persistent',False) and session.runner is None and session.status=='RUNNING':
                session.runner=asyncio.create_task(self._run(session,None))

    def list_workers(self) -> list[str]:
        return list(self.workers)

    def list_tasks(self) -> list[dict]:
        return [self.read_agent_session(task_id) for task_id in self._sessions]

    @staticmethod
    def _message(message: str) -> str:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("A task message is required.")
        if len(message) > 12000:
            raise ValueError("The task message is too long.")
        return message  # The user's original wording, including whitespace.

    def _get(self, task_id: str) -> _Session:
        if not isinstance(task_id, str) or task_id not in self._sessions:
            raise ValueError("That task is unavailable.")
        return self._sessions[task_id]

    def _emit(self, session: _Session):
        self._observe(session)
        adapter=self.workers.get(session.worker)
        if getattr(adapter,'persistent',False):
            adapter.save_task_state(session.id,session.status,session.summary,session.completed_at)
        if self.on_event:
            # An unavailable UI subscriber must not change a worker's outcome.
            try:
                self.on_event({"type": "agent_result", **({'client_id': session.goal.owner} if session.goal else {}), "data": {
                    "task_id": session.id, "worker": session.worker,
                    "status": session.status, "summary": session.summary,
                    **({'kind': 'local_goal', 'goal': session.goal.snapshot()} if session.goal else {})}})
            except Exception:
                pass

    def _observe(self, session):
        if session.goal is not None:
            return  # In-session task evidence, never broad personal memory.
        if self.on_continuity:
            try:
                self.on_continuity({'task_id':session.id,'status':session.status,
                    'description':session.messages[0][:4000] if session.messages else '', 'workspace':session.workspace})
            except Exception:
                pass  # Memory availability never changes a real task outcome.

    @blocked_effect
    async def start_task(self, worker: str, message: str, *, authorized: bool = False, workspace=None) -> dict:
        if authorized is not True:
            raise PermissionError("Starting an agent task requires your instruction.")
        if not isinstance(worker, str) or worker not in self.workers:
            raise ValueError("That worker is not configured.")
        message = self._message(message)
        session = _Session(uuid4().hex, worker, messages=[message])
        if workspace is not None and not hasattr(self.workers[worker], 'manager'):
            raise ValueError('This worker does not support workspace selection.')
        session.workspace = str(workspace) if workspace is not None else None
        self._sessions[session.id] = session
        self._observe(session)
        session.runner = asyncio.create_task(self._run(session, message))
        return self.read_agent_session(session.id)

    async def _run(self, session: _Session, message: str):
        if session.status!='RUNNING':return
        try:
            adapter=self.workers.get(session.worker)
            result = (await session.goal.run() if session.goal else
                      await adapter.monitor(session.id) if message is None else
                      await adapter.run(session.id, message, workspace=session.workspace) if session.workspace else
                      await adapter.run(session.id, message))
            if session.status != "RUNNING" or session.runner is not asyncio.current_task():
                return  # A cancelled worker cannot publish a late success.
            if not isinstance(result, WorkerResult) or not isinstance(result.text, str) or not isinstance(result.summary, str):
                raise ValueError("Invalid worker response")
            session.result = result.text
            summary = self.format_summary(result.summary) if self.format_summary else result.summary
            session.summary = " ".join(summary.split())[:400]
            session.status = "WAITING_FOR_USER" if result.needs_input else "COMPLETED"
            if session.goal and result.goal_status in {'COMPLETED','WAITING_FOR_USER','ERROR','CLEANUP_UNKNOWN'}:
                session.status = result.goal_status
        except asyncio.CancelledError:
            if session.goal and session.status == 'RUNNING':
                self.stop_goal(session.id, owner=session.goal.owner, cancel=True)
            return
        except Exception:
            if session.status != "RUNNING" or session.runner is not asyncio.current_task():
                return
            session.status = "ERROR"
            adapter=self.workers.get(session.worker)
            wid=getattr(adapter,'task_workers',{}).get(session.id)
            session.summary = (adapter.manager.snapshot(wid).get('error') if wid else None) or "The worker could not complete this turn."
        session.completed_at=time.time() if session.status not in {'WAITING_FOR_USER','RUNNING'} else None
        self._emit(session)

    def create_goal(self, goal):
        if self._closing or sum(s.goal is not None for s in self._sessions.values()) >= 32:
            raise PermissionError('goal_capacity_or_shutdown')
        session = _Session(uuid4().hex, 'local_goal', status='WAITING_FOR_USER',
                           messages=[goal.label], goal=goal)
        self._sessions[session.id] = session
        goal.session = session
        self._emit(session)
        return session

    def start_goal(self, task_id, *, owner):
        session = self._get(task_id)
        if (not session.goal or session.goal.owner != owner or self._closing or
                session.status != 'WAITING_FOR_USER' or
                (session.runner is not None and not session.runner.done())):
            raise PermissionError('goal_start_unavailable')
        session.goal.check(active=True, starting=True)
        session.status, session.completed_at = 'RUNNING', None
        session.runner = asyncio.create_task(self._run(session, None))
        self._emit(session)
        return self.read_agent_session(task_id)

    def goal_progress(self, goal, summary):
        session = goal.session
        if session.status == 'RUNNING':
            session.summary = summary
            self._emit(session)

    def stop_goal(self, task_id, *, owner, cancel=False, reason='user_pause'):
        session = self._get(task_id)
        if not session.goal or session.goal.owner != owner:
            raise PermissionError('goal_owner_mismatch')
        if session.status in {'COMPLETED','ERROR','CANCELLED','CLEANUP_UNKNOWN'}:
            return self.read_agent_session(task_id)
        unknown = session.goal.revoke(reason)
        session.status = 'CLEANUP_UNKNOWN' if unknown else 'CANCELLED' if cancel else 'WAITING_FOR_USER'
        session.summary = ('Action outcome is unknown; no retry is permitted.' if unknown else
                           'Goal cancelled; verified checkpoints retained.' if cancel else
                           'Goal paused; review the remaining scope before resuming.')
        if (session.runner is not None and not session.runner.done() and
                session.runner is not asyncio.current_task()):
            session.runner.cancel()
        self._emit(session)
        return self.read_agent_session(task_id)

    def stop_goals(self, *, reason, owner=None):
        for session in tuple(self._sessions.values()):
            if session.goal and (owner is None or session.goal.owner == owner):
                self.stop_goal(session.id, owner=session.goal.owner,
                               cancel=reason in {'shutdown','disconnect'}, reason=reason)

    def read_agent_session(self, task_id: str) -> dict:
        session = self._get(task_id)
        if session.goal:
            return {'task_id':session.id, 'worker':session.worker, 'kind':'local_goal',
                    'status':session.status, 'summary':session.summary, 'instruction':session.messages[0],
                    'created_at':session.created_at, 'completed_at':session.completed_at,
                    'goal':session.goal.snapshot()}
        adapter=self.workers[session.worker]
        wid=getattr(adapter,'task_workers',{}).get(task_id)
        worker=adapter.manager.snapshot(wid) if wid else {}
        return {"task_id": session.id, "worker": session.worker,
                "status": session.status, "summary": session.summary,
                "messages": list(session.messages), 'instruction':session.messages[0],
                'worker_id':wid,'workspace':worker.get('workspace',session.workspace),
                'created_at':session.created_at,'completed_at':session.completed_at,
                'exit_code':worker.get('exit_code'),'changed_files':worker.get('changed_files',[]),
                'test_results':worker.get('test_results',[]),'error':worker.get('error')}

    def get_agent_result(self, task_id: str) -> dict:
        session = self._get(task_id)
        return {"task_id": session.id, "status": session.status,
                "summary": session.summary, "result": session.result}

    @blocked_effect
    async def send_agent_message(self, task_id: str, message: str, *, authorized: bool = False) -> dict:
        if authorized is not True:
            raise PermissionError("Messaging an agent requires your instruction.")
        session = self._get(task_id)
        message = self._message(message)
        if session.status != "RUNNING":
            raise ValueError("This task is not running; resume it to continue.")
        await self.workers[session.worker].send_message(task_id, message)
        session.messages.append(message)
        return self.read_agent_session(task_id)

    @blocked_effect
    async def resume_task(self, task_id: str, message: str, *, authorized: bool = False) -> dict:
        if authorized is not True:
            raise PermissionError("Resuming an agent task requires your instruction.")
        session = self._get(task_id)
        message = self._message(message)
        if session.status not in {"WAITING_FOR_USER", "COMPLETED", "ERROR"}:
            raise ValueError("This task cannot be resumed in its current state.")
        session.status, session.summary, session.result = "RUNNING", "", None
        session.completed_at=None
        adapter=self.workers[session.worker]
        if getattr(adapter,'persistent',False):adapter.save_task_state(task_id,'RUNNING')
        session.messages.append(message)
        self._observe(session)
        session.runner = asyncio.create_task(self._run(session, message))
        return self.read_agent_session(task_id)

    def register_simulated_cleanup(self, task_id, *, owner, generation, resource):
        """Trusted test injection, no HTTP/tool enrollment and no native adoption.

        Legacy runner coroutines may spawn independently and are not enrollable.
        A native worker needs retained OS ownership and an effect boundary first.
        """
        from .control_authority import SimulatedWorkerCleanupAdapter
        session = self._get(task_id)
        if not isinstance(self.workers.get(session.worker), SimulatedWorkerCleanupAdapter):
            raise PermissionError('simulated_worker_required')
        if self._closing or session.runner is not None or session.cleanup_binding is not None:
            raise PermissionError('worker_ownership_unavailable')
        session.cleanup_binding = self.authority.register_worker_cleanup(
            task_id, owner, generation, self.workers[session.worker], resource)
        return session.cleanup_binding

    def register_native_fixture(self, adapter):
        """Only a newly created exact Runtime-owned fixture; no PID adoption."""
        from .native_process import NativeFixtureLifetime
        if (type(adapter) is not NativeFixtureLifetime or self._closing or
                adapter.session.manager is not self or not adapter.enrollable(self.authority, adapter.resource)):
            raise PermissionError('native_fixture_registration_denied')
        c = adapter.resource.creation
        if c.task_id in self._sessions or c.worker_id in self.workers:
            raise PermissionError('native_fixture_already_registered')
        binding = self.authority.register_worker_cleanup(c.task_id, c.owner,
                    c.worker_generation, adapter, adapter.resource)
        self.workers[c.worker_id] = adapter
        self._sessions[c.task_id] = _Session(c.task_id, c.worker_id,
            messages=['Fixed disposable native fixture'], cleanup_binding=binding)
        return binding

    def _cleanup_binding(self, session):
        binding = session.cleanup_binding
        if (binding is None or binding.task_id != session.id or
                binding.adapter is not self.workers.get(session.worker) or session.runner is not None):
            raise PermissionError('worker_ownership_unavailable')
        return binding

    def prepare_cleanup(self, task_id, *, owner, operation):
        if self._closing:
            raise PermissionError('worker_manager_closing')
        session = self._get(task_id)
        return self.authority.issue_worker_cleanup(self._cleanup_binding(session), owner, operation)

    def _cleanup_unknown(self, session):
        session.status = 'CLEANUP_UNKNOWN'
        session.summary = 'Worker cleanup is unconfirmed; ownership and task state are retained.'
        self.authority.uncertain_worker_cleanup(session.cleanup_grant)

    async def _perform_cleanup(self, session, grant):
        try:
            session.cleanup_worker = asyncio.create_task(grant.binding.adapter.cleanup(self.authority, grant))
            self.authority.track(session.cleanup_worker)
            try:
                receipt = await asyncio.wait_for(asyncio.shield(session.cleanup_worker), self.cleanup_timeout)
            except TimeoutError:
                self._cleanup_unknown(session)
                # Retain the actual adapter until it ends, even if every caller left.
                receipt = await asyncio.shield(session.cleanup_worker)
            if self.authority.finish_worker_cleanup(grant, receipt):
                session.status = 'REMOVED' if grant.operation == 'remove' else 'CANCELLED'
                session.summary = 'Owned fixture cleanup confirmed.'
                session.completed_at = time.time()
                if grant.operation == 'remove':
                    self._sessions.pop(session.id)
            else:
                self._cleanup_unknown(session)
        except BaseException:
            # Includes cancellation of the actual worker at loop shutdown. The
            # caller is shielded separately; no cancellation implies settlement.
            self._cleanup_unknown(session)
        # Do not call legacy _emit/save_task_state: that is an unscoped disk write.
        # HTTP/read_agent_session exposes the state without invoking another adapter.

    async def _await_cleanup(self, session):
        try:
            await asyncio.wait_for(asyncio.shield(session.cleanup_task), self.cleanup_timeout)
        except TimeoutError:
            self._cleanup_unknown(session)
        # CancelledError deliberately propagates to the caller, never to cleanup.
        if session.status == 'REMOVED':
            return {'task_id': session.id, 'status': 'REMOVED'}
        return self.read_agent_session(session.id)

    async def _cleanup(self, task_id, owner, grant, operation, *, shutdown=False):
        session = self._get(task_id)
        binding = self._cleanup_binding(session)
        if (self._closing and not shutdown) or (getattr(grant, 'shutdown', False) and not shutdown):
            raise PermissionError('worker_manager_closing_or_internal_grant')
        already_registered = self.authority.worker_cleanup_registered(grant)
        try:
            self.authority.begin_worker_cleanup(grant, binding, owner, operation)
        except PermissionError:
            if not already_registered and self.authority.worker_cleanup_registered(grant):
                session.cleanup_grant = grant
                self._cleanup_unknown(session)
            raise
        session.cleanup_grant = grant
        session.status = 'CANCELLING' if operation == 'cancel' else 'REMOVING'
        session.cleanup_task = asyncio.create_task(self._perform_cleanup(session, grant))
        self.authority.track(session.cleanup_task)
        return await self._await_cleanup(session)

    async def cancel_task(self, task_id: str, *, owner=None, grant=None) -> dict:
        return await self._cleanup(task_id, owner, grant, 'cancel')

    async def remove_task(self, task_id: str, *, owner=None, grant=None) -> dict:
        return await self._cleanup(task_id, owner, grant, 'remove')

    async def close(self):
        self._closing = True
        self.authority.stop('shutdown')
        for session in tuple(self._sessions.values()):
            if session.goal:
                self.stop_goal(session.id, owner=session.goal.owner, cancel=True, reason='shutdown')
                if session.runner and not session.runner.done():
                    await asyncio.wait({session.runner}, timeout=self.cleanup_timeout)
                continue
            if session.cleanup_task is not None:
                # Never submit another attempt, including after an unknown result.
                await self._await_cleanup(session)
            elif session.cleanup_binding is not None:
                binding = self._cleanup_binding(session)
                try:
                    grant = self.authority.issue_worker_cleanup(binding, binding.owner, 'cancel', shutdown=True)
                    await self._cleanup(session.id, binding.owner, grant, 'cancel', shutdown=True)
                except PermissionError:
                    self.authority.note_external_uncertainty()
            else:
                # Unowned legacy monitors/workers are neither cancelled nor removed.
                # Cancelling one can itself invoke native cleanup in its finally.
                self.authority.note_external_uncertainty()
