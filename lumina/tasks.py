"""Local, provider-neutral task coordination. Adapters receive no OS authority here."""
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


class TaskManager:
    """Starts only at a trusted, explicitly authorized user-action boundary.

    Do not expose the authorized flag as a model-controlled tool argument.
    No adapter is created, downloaded, or selected implicitly.
    """

    def __init__(self, workers: dict[str, WorkerAdapter] | None = None,
                 on_event: Callable[[dict], None] | None = None,
                 format_summary: Callable[[str], str] | None = None,
                 on_continuity: Callable[[dict], None] | None = None):
        self.workers = dict(workers or {})
        self._sessions: dict[str, _Session] = {}
        self.on_event = on_event
        self.format_summary = format_summary
        self.on_continuity = on_continuity
        for name,adapter in self.workers.items():
            if getattr(adapter,'persistent',False):
                for task_id,record in adapter.records.items():
                    adapter.restore(task_id)
                    status=record.get('task_status') or {'CANCELLED':'CANCELLED','TERMINATED':'CANCELLED','FAILED':'ERROR','COMPLETED':'COMPLETED','WAITING':'WAITING_FOR_USER'}.get(record.get('status'),'RUNNING')
                    if record.get('status') in {'CANCELLED','TERMINATED'}:status='CANCELLED'
                    self._sessions[task_id]=_Session(task_id,name,status=status,summary=record.get('summary',''),messages=[record['instruction']],workspace=record['workspace'],completed_at=record.get('completed_at'))

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
        adapter=self.workers[session.worker]
        if getattr(adapter,'persistent',False):
            adapter.save_task_state(session.id,session.status,session.summary,session.completed_at)
        if self.on_event:
            # An unavailable UI subscriber must not change a worker's outcome.
            try:
                self.on_event({"type": "agent_result", "data": {
                    "task_id": session.id, "worker": session.worker,
                    "status": session.status, "summary": session.summary}})
            except Exception:
                pass

    def _observe(self, session):
        if self.on_continuity:
            try:
                self.on_continuity({'task_id':session.id,'status':session.status,
                    'description':session.messages[0][:4000] if session.messages else '', 'workspace':session.workspace})
            except Exception:
                pass  # Memory availability never changes a real task outcome.

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
            adapter=self.workers[session.worker]
            result = await adapter.monitor(session.id) if message is None else await adapter.run(session.id, message, workspace=session.workspace) if session.workspace else await adapter.run(session.id, message)
            if session.status != "RUNNING" or session.runner is not asyncio.current_task():
                return  # A cancelled worker cannot publish a late success.
            if not isinstance(result, WorkerResult) or not isinstance(result.text, str) or not isinstance(result.summary, str):
                raise ValueError("Invalid worker response")
            session.result = result.text
            summary = self.format_summary(result.summary) if self.format_summary else result.summary
            session.summary = " ".join(summary.split())[:400]
            session.status = "WAITING_FOR_USER" if result.needs_input else "COMPLETED"
        except asyncio.CancelledError:
            return
        except Exception:
            if session.status != "RUNNING" or session.runner is not asyncio.current_task():
                return
            session.status = "ERROR"
            adapter=self.workers[session.worker]
            wid=getattr(adapter,'task_workers',{}).get(session.id)
            session.summary = (adapter.manager.snapshot(wid).get('error') if wid else None) or "The worker could not complete this turn."
        session.completed_at=time.time()
        self._emit(session)

    def read_agent_session(self, task_id: str) -> dict:
        session = self._get(task_id)
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

    async def cancel_task(self, task_id: str) -> dict:
        session = self._get(task_id)
        adapter=self.workers[session.worker]
        persistent=getattr(adapter,'persistent',False)
        if session.status in {"COMPLETED", "CANCELLED", "ERROR"} and not persistent:
            return self.read_agent_session(task_id)
        if session.status in {"CANCELLING","REMOVING"}:
            raise ValueError("Cancellation is already in progress.")
        session.status = "CANCELLING"
        if session.runner:
            session.runner.cancel()
        try:
            if session.runner:
                await asyncio.wait_for(asyncio.shield(asyncio.gather(session.runner,return_exceptions=True)),timeout=12)
            # Wait for a racing spawn to register its identity before cancellation.
            if persistent and task_id not in adapter.records:
                if session.runner and not session.runner.done():raise RuntimeError('Agent startup is still pending.')
            else:
                await asyncio.wait_for(adapter.cancel(task_id), timeout=30 if persistent else 5)
        except Exception:
            session.status = "CANCEL_FAILED"
            session.summary = "The worker did not confirm cancellation."
        else:
            session.status = "CANCELLED"
            session.summary = "The task was cancelled."
            session.completed_at=time.time()
        self._emit(session)
        return self.read_agent_session(task_id)

    async def remove_task(self, task_id: str) -> dict:
        """Remove only a confirmed inactive agent's registry/UI entries."""
        session=self._get(task_id)
        if session.status in {'CANCELLING','REMOVING'}:
            raise ValueError('An agent lifecycle operation is already in progress.')
        adapter=self.workers[session.worker]
        persistent=getattr(adapter,'persistent',False)
        running=session.runner is not None and not session.runner.done()
        if persistent:
            if task_id not in adapter.records and running:
                raise ValueError('Agent startup is still pending; cancel it before removal.')
        elif running or session.status not in {'COMPLETED','CANCELLED','ERROR'} or task_id in getattr(adapter,'processes',{}):
            raise ValueError('The agent is not confirmed inactive; cancel it before removal.')
        previous=session.status
        session.status='REMOVING'
        try:
            if persistent:await adapter.remove(task_id)
        except BaseException:
            session.status=previous
            raise
        if running:
            session.runner.cancel()
            await asyncio.gather(session.runner,return_exceptions=True)
        wid=getattr(adapter,'task_workers',{}).pop(task_id,None)
        if wid:adapter.manager.sessions.pop(wid,None)
        del self._sessions[task_id]
        return {'task_id':task_id,'status':'REMOVED'}

    async def close(self):
        for session in tuple(self._sessions.values()):
            if getattr(self.workers[session.worker],'persistent',False):
                if session.runner:
                    session.runner.cancel()
                    await asyncio.gather(session.runner,return_exceptions=True)
                continue
            if session.status in {"RUNNING", "WAITING_FOR_USER", "CANCEL_FAILED"}:
                await self.cancel_task(session.id)
