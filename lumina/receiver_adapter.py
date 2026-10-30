"""One trusted-harness registered, private-pipe receiver. No launch/enroll tool."""
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
import secrets
import time

from .computer_action import ActionAdapter, TargetEvidence, ExecutionResult, Verification
from .receiver_protocol import OPERATION, opaque


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ReceiverRegistration:
    pid: int
    fixture: str


class ReceiverAdapter(ActionAdapter):
    operations = (OPERATION,)

    def __init__(self, authority, observations, process, registration, *, owner, timeout=.75):
        if (type(registration) is not ReceiverRegistration or not opaque(registration.fixture) or
                not opaque(owner) or not isinstance(process,asyncio.subprocess.Process) or
                process.pid != registration.pid or process.pid == os.getpid() or process.returncode is not None or
                process.stdin is None or process.stdout is None or type(timeout) not in (int,float) or not 0 < timeout <= 2):
            raise ValueError('invalid_receiver_registration')
        authority.check()
        current = observations.latest()
        if current is None:
            raise PermissionError('fresh_session_required')
        self.authority,self.observations,self.process = authority,observations,process
        self.registration,self.owner,self.timeout = registration,owner,timeout
        self.session_token = observations._session_token
        self.context = dict(owner=owner,session=current.session_id,session_key=secrets.token_hex(16),
                            epoch=authority.epoch,generation=authority.generation)
        self.bindings,self.payloads,self.receipts = {},{},{}
        self.pending,self.jobs = {},set()
        self.target,self.state = None,None
        self.revoked,self.closed,self.broken = False,False,False
        self.revocation = None
        self.closing = None
        self.send_lock = asyncio.Lock()
        authority.register_revoker(self._stop)
        self.reader = asyncio.create_task(self._read_responses())
        self.session_watch = asyncio.create_task(self._watch_session(observations.subscribe()))

    async def _watch_session(self, consumer):
        try:
            while True:
                await consumer.next()
        except StopAsyncIteration:
            self._stop('session_invalidated')
        finally:
            consumer.close()

    def _track(self, coroutine):
        task=asyncio.create_task(coroutine)
        self.jobs.add(task);self.authority.track(task)
        def done(future):
            self.jobs.discard(future)
            if not future.cancelled():future.exception()
        task.add_done_callback(done)
        return task

    async def _read_responses(self):
        try:
            while line := await self.process.stdout.readline():
                if len(line)>8192:raise ValueError('receiver_reply_limit')
                row=json.loads(line)
                if type(row) is not dict or set(row)!={'id','body'} or not opaque(row['id']):
                    raise ValueError('receiver_reply_schema')
                waiting=self.pending.get(row['id'])
                if waiting is not None and not waiting.done():waiting.set_result(row['body'])
        except (ValueError, OSError, asyncio.CancelledError):
            pass
        finally:
            self.broken=True
            for waiting in tuple(self.pending.values()):
                if not waiting.done():waiting.set_exception(ConnectionError('receiver_disconnected'))

    async def _rpc(self, body, *, guard=None):
        async def request():
            key=secrets.token_hex(16);waiting=asyncio.get_running_loop().create_future()
            try:
                async with asyncio.timeout(self.timeout):
                    async with self.send_lock:
                        if self.broken or self.closed or len(self.pending)>=8:
                            raise ConnectionError('receiver_unavailable')
                        if guard is not None:guard()
                        self.pending[key]=waiting
                        data=json.dumps({'id':key,'body':body},allow_nan=False).encode()+b'\n'
                        if len(data)>8192:raise ValueError('receiver_request_limit')
                        self.process.stdin.write(data)
                        await self.process.stdin.drain()
                    return await asyncio.shield(waiting)
            finally:
                self.pending.pop(key,None)
                if not waiting.done():waiting.cancel()
                elif not waiting.cancelled():waiting.exception()
        # A cancelled controller awaiter does not cancel a submitted pipe write.
        return await asyncio.shield(self._track(request()))

    def _check(self, action=None, lease=None, cancelled=None):
        self.authority.check()
        if (self.revoked or self.closed or self.broken or
                self.session_token is not self.observations._session_token or
                (self.authority.epoch,self.authority.generation) != (self.context['epoch'],self.context['generation'])):
            raise PermissionError('receiver_revoked')
        current=self.observations.latest()
        if current is None or current.session_id!=self.context['session']:
            raise PermissionError('receiver_session_stale')
        if action is not None:
            if (current.sequence<action.observation_sequence or action.session_id!=current.session_id or
                    time.monotonic()>=action.expires_at or (cancelled is not None and cancelled.is_set())):
                raise PermissionError('receiver_action_stale')
        if lease is not None:self.authority.validate(lease)

    async def open(self):
        reply=await self._rpc(dict(kind='open',fixture=self.registration.fixture,context=self.context),guard=self._check)
        self._check()
        if reply!={'status':'opened','fixture':self.registration.fixture}:
            raise PermissionError('receiver_enrollment_rejected')

    async def read_state(self):
        row=await self._rpc(dict(kind='read',fixture=self.registration.fixture))
        if (type(row) is not dict or set(row)!={'status','fixture','value','revision'} or
                row['status']!='state' or row['fixture']!=self.registration.fixture or
                row['value'] not in ('empty','ready') or type(row['revision']) is not int or not 0<=row['revision']<=128):
            raise ValueError('receiver_state_invalid')
        return {'value':row['value'],'revision':row['revision']}

    def target_for(self, state):
        return TargetEvidence(self.registration.fixture,'fixture-value',digest(state),0,
                              foreground=False,patterns=self.operations)

    async def refresh(self):
        self._check();state=await self.read_state();self._check()
        self.target,self.state=self.target_for(state),state
        return state

    def validate_proposal(self, operation, target, text, expected_digest):
        self._check()
        if (operation!=OPERATION or target!=self.target or self.state is None or text is not None or
                expected_digest!=digest(dict(value='ready',revision=self.state['revision']+1))):
            raise ValueError('receiver_scope_invalid')

    def bind(self, action, lease, scope):
        self._check(action,lease)
        self.validate_proposal(action.operation,action.target,action.text,action.expected_digest)
        if digest(scope)!=lease.digest or lease.owner!=self.owner:
            raise PermissionError('receiver_lease_mismatch')
        self.bindings[action.action_id]=(action,lease,dict(self.state))

    async def revalidate(self, action):
        self._check(action)
        return self.target_for(await self.read_state())

    def _matches(self, action, receipt, state):
        def state_record(value):
            return (type(value) is dict and set(value)=={'value','revision'} and
                    type(value['value']) is str and value['value'] in ('empty','ready') and
                    type(value['revision']) is int and 0<=value['revision']<=128)
        p=self.payloads.get(action.action_id)
        return (p is not None and type(receipt) is dict and
                set(receipt)=={'status','reason','attempt','operation','fixture','scope','prior','result'} and
                state_record(receipt['prior']) and state_record(receipt['result']) and
                receipt['status'] in ('applied','already_processed') and receipt['reason']=='applied' and
                receipt['attempt']==action.action_id and receipt['operation']==OPERATION and
                receipt['fixture']==self.registration.fixture and receipt['scope']==p['scope'] and
                receipt['prior']==dict(value=p['expected_value'],revision=p['expected_revision']) and
                receipt['result']==state==dict(value='ready',revision=p['expected_revision']+1) and
                digest(state)==action.expected_digest)

    async def reconcile(self, action):
        """Read-only evidence, original attempt. Never clears authority quarantine."""
        receipt=await self._rpc(dict(kind='query',fixture=self.registration.fixture,attempt=action.action_id))
        state=await self.read_state()
        matched=self._matches(action,receipt,state)
        if matched:self.receipts[action.action_id]=receipt
        return {'matched':matched,'receipt':receipt,'state':state,'retry_allowed':False}

    async def dispatch(self, action, cancelled):
        binding=self.bindings.pop(action.action_id,None)
        if binding is None or binding[0] is not action or action.action_id in self.payloads:
            return ExecutionResult('failed')
        _,lease,before=binding
        guard=lambda:self._check(action,lease,cancelled)
        guard()
        payload=dict(**self.context,attempt=action.action_id,fixture=self.registration.fixture,
                     grant=secrets.token_hex(24),scope=lease.digest,operation=OPERATION,
                     expected_revision=before['revision'],expected_value=before['value'],desired='ready',
                     expires=min(action.expires_at,time.monotonic()+2,
                        self.observations.latest().capture_not_before_monotonic+self.observations.freshness_seconds))
        self.payloads[action.action_id]=payload
        authorized=await self._rpc(dict(kind='authorize',payload=payload),guard=guard)
        if authorized!={'status':'authorized','fixture':self.registration.fixture,'attempt':action.action_id}:
            return ExecutionResult('failed')
        try:
            receipt=await self._rpc(dict(kind='apply',payload=payload),guard=guard)
        except (TimeoutError,ConnectionError,OSError):
            # Never re-send apply or create another attempt after possible delivery.
            evidence=await self.reconcile(action)
            guard()
            return ExecutionResult('complete' if evidence['matched'] else 'unknown')
        guard()
        self.receipts[action.action_id]=receipt
        return ExecutionResult('complete' if type(receipt) is dict and receipt.get('status') in ('applied','already_processed') else 'failed')

    async def verify(self, action, outcome):
        self._check(action)
        state=await self.read_state()
        matched=self._matches(action,self.receipts.get(action.action_id),state)
        return Verification(action.action_id,action.target.window_id,action.target.control_id,digest(state),
                            'matched' if matched else 'inconclusive')

    def _stop(self, reason):
        self.revoked=True;self.bindings.clear()
        if self.revocation is None and not self.closed:
            async def revoke():
                acknowledged=False
                try:
                    result=await self._rpc(dict(kind='revoke',fixture=self.registration.fixture))
                    acknowledged=(type(result) is dict and set(result)=={'status','fixture','revision'} and
                            result['status']=='revoked' and result['fixture']==self.registration.fixture and
                            type(result['revision']) is int)
                except (Exception,asyncio.CancelledError):pass
                if not acknowledged:self.authority.note_external_uncertainty()
                return acknowledged
            self.revocation=self._track(revoke())

    async def cancel(self, action_id):
        self._stop('cancelled')
        acknowledged=await asyncio.shield(self.revocation) if self.revocation else False
        return acknowledged and not any(not job.done() for job in self.jobs)

    async def cleanup(self, action_id):
        if self.revoked:return await self.cancel(action_id)
        return not any(not job.done() for job in self.jobs)

    def status(self):
        revocation='not_requested'
        if self.revocation is not None:
            revocation='pending'
            if self.revocation.done():
                revocation='unconfirmed'
                if not self.revocation.cancelled() and self.revocation.exception() is None and self.revocation.result() is True:
                    revocation='acknowledged'
        return {'revocation':revocation,'pending_requests':len(self.pending),
                'owned_jobs':sum(not job.done() for job in self.jobs),
                'reaped':self.process.returncode is not None,
                'admission_closed':self.revoked or self.closed or self.broken or self.authority.stop_requested.is_set()}

    async def close(self):
        if self.closing is None:
            self.closing=asyncio.create_task(self._close())
            self.authority.track(self.closing)
        return await asyncio.shield(self.closing)

    async def _close(self):
        acknowledged=await self.cancel('close')
        self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(),2)
        except TimeoutError:
            self.process.kill()
            try:await asyncio.wait_for(self.process.wait(),2)
            except TimeoutError:acknowledged=False
        self.closed=True
        self.reader.cancel();self.session_watch.cancel()
        await asyncio.gather(self.reader,self.session_watch,return_exceptions=True)
        settled=acknowledged and self.process.returncode is not None and not any(not job.done() for job in self.jobs)
        if not settled:self.authority.note_external_uncertainty()
        return {'ok':settled,'settled':settled,'receiver_revoked':acknowledged,'reaped':self.process.returncode is not None}
