"""Runtime safety state for simulation and bounded owned-window effects.

Trusted Python injection is not a sandbox. No public tool can arm this authority.
The durable marker contains only opaque identities and fixed lifecycle values.
"""
from dataclasses import dataclass
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import secrets
import time
import math
import threading
import asyncio
from contextvars import ContextVar
from abc import ABC, abstractmethod


# Trusted request context, never supplied by a model/tool argument.
inspection_owner = ContextVar('inspection_owner', default='runtime')
_inspection = ContextVar('inspection', default=None)


@dataclass(eq=False)
class Inspection:
    authority: object
    owner: str
    boundary: tuple
    deadline: float
    task: object = None
    revoked: bool = False
    scope: str | None = None
    consumed: bool = False


@dataclass(frozen=True)
class SettlementEvidence:
    operation_id: str
    epoch: str
    observed_at: float
    verdict: str
    settled: bool
    cleanup: bool
    reference: str


class SettlementInspector(ABC):
    """Trusted independent fake-world inspection; never a model/HTTP input.

    Must inspect submission, effects, owned work and cleanup independently of
    controller results. Python injection is not an authentication sandbox.
    """
    @abstractmethod
    def inspect(self, operation_id, epoch) -> SettlementEvidence: ...


def denied():
    return {'ok': False, 'status': 'live_effects_disabled', 'error': 'live_effects_disabled'}


def blocked_effect(function):
    """Keep legacy implementation for later review, deny before any side effect."""
    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def blocked(*args, **kwargs):
            return denied()
    else:
        @wraps(function)
        def blocked(*args, **kwargs):
            return denied()
    return blocked


@dataclass(frozen=True)
class Lease:
    token: str
    action_id: str
    owner: str
    digest: str
    epoch: str
    generation: int


@dataclass(frozen=True, eq=False)
class OwnedWorker:
    token: str
    task_id: str
    owner: str
    generation: str
    adapter: object
    resource: object


@dataclass(frozen=True, eq=False)
class WorkerCleanupGrant:
    token: str
    binding: OwnedWorker
    operation: str
    epoch: str
    generation: int
    stop_serial: int
    expires: float
    shutdown: bool = False


@dataclass(frozen=True)
class WorkerCleanupReceipt:
    attempt: str
    ownership: str
    worker_generation: str
    operation: str
    quiescent: bool
    removed: bool = False


class SimulatedWorkerCleanupAdapter(ABC):
    """Trusted counter-only fixtures. No native adapter implements this contract.

    cleanup must await all its work and use worker_cleanup_effect at its actual
    synchronous fake-effect boundary. Returning an acknowledgement is insufficient.
    This Python injection interface does not authenticate humans or fence an OS API.
    """
    @abstractmethod
    async def cleanup(self, authority, grant) -> WorkerCleanupReceipt: ...


class ControlAuthority:
    def __init__(self, marker_path=None, *, clock=time.monotonic):
        self.epoch = secrets.token_hex(16)
        self.generation = 0
        self.mode = 'disarmed'
        self._leases = {}
        self._operations = {}
        self._revokers = []
        self._jobs = set()
        self.marker_path = Path(marker_path) if marker_path else None
        self.quarantined = bool(self.marker_path and self.marker_path.exists())
        self.clock = clock
        self._foreign_marker = self.quarantined
        self._external_uncertainty = self.quarantined
        self._decisions = []
        self._marker_bytes = None
        self.persistence_failed = False
        # A native Stop button can latch this without waiting for asyncio.
        self.stop_requested = threading.Event()
        self._stop_lock = threading.Lock()
        self._stop_serial = 0
        # Read-only jobs cannot create effects and must not be used as evidence
        # of mutation settlement. Keep their cancellation/cleanup visible.
        self._inspections = set()
        self._inspection_stop_serial = 0
        self._owned_workers = {}
        self._cleanup_grants = {}

    def register_worker_cleanup(self, task_id, owner, generation, adapter, resource):
        """Trusted fixture enrollment only; never adopt legacy records or PIDs."""
        self.check()
        from .native_process import NativeFixtureLifetime
        native = type(adapter) is NativeFixtureLifetime and adapter.enrollable(self, resource)
        if ((not isinstance(adapter, SimulatedWorkerCleanupAdapter) and not native) or resource is None or
                not all(type(v) is str and v for v in (task_id, owner, generation)) or
                task_id in self._owned_workers):
            raise PermissionError('worker_ownership_unavailable')
        self._persist()
        self.check()
        binding = OwnedWorker(secrets.token_hex(24), task_id, owner, generation, adapter, resource)
        self._owned_workers[task_id] = {'binding': binding, 'quiescent': False, 'attempt': None}
        return binding

    def _worker(self, binding):
        record = self._owned_workers.get(getattr(binding, 'task_id', None))
        if type(binding) is not OwnedWorker or not record or record['binding'] is not binding:
            raise PermissionError('worker_ownership_unavailable')
        return record

    def issue_worker_cleanup(self, binding, owner, operation, *, shutdown=False):
        record = self._worker(binding)
        if owner != binding.owner or operation not in ('cancel', 'remove'):
            raise PermissionError('worker_cleanup_scope_mismatch')
        if shutdown:
            if operation != 'cancel' or self.mode not in ('shutdown', 'quarantined') or not self.stop_requested.is_set():
                raise PermissionError('shutdown_cleanup_unavailable')
        else:
            self.check()
        if (record['attempt'] is not None or
                (operation == 'remove') != record['quiescent']):
            raise PermissionError('worker_cleanup_unsettled_or_complete')
        now = self.clock()
        self._cleanup_grants = {k: v for k, v in self._cleanup_grants.items() if v.expires > now}
        if len(self._cleanup_grants) >= 64:
            raise PermissionError('worker_cleanup_capacity')
        grant = WorkerCleanupGrant(secrets.token_hex(24), binding, operation, self.epoch,
                                   self.generation, self._stop_serial, now + 60, shutdown)
        self._cleanup_grants[grant.token] = grant
        return grant

    def _validate_worker_grant(self, grant, binding, owner, operation):
        self._worker(binding)
        if (type(grant) is not WorkerCleanupGrant or grant.binding is not binding or
                owner != binding.owner or grant.operation != operation or
                grant.epoch != self.epoch or grant.generation != self.generation or
                grant.stop_serial != self._stop_serial or self.clock() >= grant.expires):
            raise PermissionError('worker_cleanup_revoked_or_mismatched')
        if grant.shutdown:
            if operation != 'cancel' or self.mode not in ('shutdown', 'quarantined'):
                raise PermissionError('shutdown_cleanup_unavailable')
        else:
            self.check()

    def begin_worker_cleanup(self, grant, binding, owner, operation):
        self._validate_worker_grant(grant, binding, owner, operation)
        record = self._worker(binding)
        if (self._cleanup_grants.get(grant.token) is not grant or record['attempt'] is not None or
                (operation == 'remove') != record['quiescent']):
            raise PermissionError('worker_cleanup_replayed_or_unsettled')
        self._cleanup_grants.pop(grant.token)
        record['attempt'] = grant.token
        self._operations[grant.token] = {'lease': grant, 'operation_id': grant.token,
            'epoch': self.epoch, 'operation_class': ('worker_cleanup_simulation'
                if isinstance(binding.adapter, SimulatedWorkerCleanupAdapter) else 'native_fixture_cleanup'),
            'phase': 'registered', 'submission': 'not_started', 'settled': False,
            'cleanup': False, 'outcome': 'unknown'}
        try:
            self._persist()
            self._validate_worker_grant(grant, binding, owner, operation)
        except BaseException:
            self.uncertain_worker_cleanup(grant)
            raise

    def worker_cleanup_effect(self, grant, resource, effect):
        """One synchronous fake effect, ordered against the native Stop latch.

        No native call, await, detached work or reentrant authority call is allowed
        inside effect. A future OS adapter requires its own reviewed boundary.
        """
        with self._stop_lock:
            self._validate_worker_grant(grant, grant.binding, grant.binding.owner, grant.operation)
            record = self._worker(grant.binding)
            op = self._operations.get(grant.token)
            if (not isinstance(grant.binding.adapter, SimulatedWorkerCleanupAdapter) or
                    resource is not grant.binding.resource or record['attempt'] != grant.token or
                    not op or op['lease'] is not grant or op['phase'] != 'registered' or
                    inspect.iscoroutinefunction(effect)):
                raise PermissionError('worker_cleanup_effect_denied')
            op.update(phase='dispatch', submission='may_have_started')
            result = effect()
            if inspect.isawaitable(result):
                raise TypeError('cleanup_effect_must_be_synchronous')
            return result

    def native_fixture_creation(self, adapter, lease, step):
        """Fixed native call, serialized with Stop admission; no free callback.

        A native call already admitted may complete after a Stop request begins.
        This lock does not forcibly cancel Windows or promise bounded stop latency.
        """
        from .native_process import NativeFixtureLifetime
        with self._stop_lock:
            if type(adapter) is not NativeFixtureLifetime:
                raise PermissionError('native_fixture_required')
            adapter.session.validate()
            self.validate(lease)
            if (adapter.creation_lease is not lease or
                    self.clock() >= adapter.creation_expires or adapter.sealed or
                    self._operations[lease.token]['operation_class'] != 'native_fixture_creation'):
                raise PermissionError('native_creation_revoked')
            self._operations[lease.token].update(phase='dispatch', submission='may_have_started')
            return adapter._creation_step(step)

    def transfer_native_fixture(self, adapter, lease, binding):
        """Transfer a verified creation obligation into existing worker ownership."""
        with self._stop_lock:
            self.validate(lease)
            if (binding.adapter is not adapter or binding.resource is not adapter.resource or
                    not adapter.enrollable(self, adapter.resource) or
                    self._worker(binding)['binding'] is not binding or
                    self._operations[lease.token]['operation_class'] != 'native_fixture_creation'):
                raise PermissionError('native_creation_transfer_invalid')
            self._operations.pop(lease.token)

    def native_fixture_cleanup(self, adapter, grant, observation):
        """One exact native fixture operation; never enters the simulated gate."""
        from .native_process import NativeFixtureLifetime
        with self._stop_lock:
            if type(adapter) is not NativeFixtureLifetime or grant.binding.adapter is not adapter:
                raise PermissionError('native_fixture_required')
            adapter.session.validate()
            self._validate_worker_grant(grant, grant.binding, grant.binding.owner, grant.operation)
            record = self._worker(grant.binding)
            op = self._operations.get(grant.token)
            if (grant.binding.resource is not adapter.resource or record['attempt'] != grant.token or
                    not op or op['lease'] is not grant or op['phase'] != 'registered' or
                    op['operation_class'] != 'native_fixture_cleanup'):
                raise PermissionError('native_cleanup_denied')
            adapter.check_effect(observation, grant)
            op.update(phase='dispatch', submission='may_have_started')
            adapter._cleanup_effect(grant, observation)

    def uncertain_worker_cleanup(self, grant):
        op = self._operations.get(grant.token)
        if op is None or op['lease'] is not grant:
            raise PermissionError('worker_cleanup_attempt_unknown')
        op.update(phase='uncertain', outcome='unknown')
        self.quarantined = True
        self.stop('quarantined')

    def worker_cleanup_registered(self, grant):
        return (type(grant) is WorkerCleanupGrant and
                self._operations.get(grant.token, {}).get('lease') is grant)

    def finish_worker_cleanup(self, grant, receipt):
        record = self._worker(grant.binding)
        op = self._operations.get(grant.token)
        valid = (type(receipt) is WorkerCleanupReceipt and receipt.attempt == grant.token and
                 receipt.ownership == grant.binding.token and
                 receipt.worker_generation == grant.binding.generation and
                 receipt.operation == grant.operation and receipt.quiescent is True and
                 receipt.removed is (grant.operation == 'remove'))
        if op is None or op['lease'] is not grant or record['attempt'] != grant.token:
            raise PermissionError('worker_cleanup_attempt_unknown')
        op['receipt_available'] = valid
        # Timeout/error uncertainty is sticky. A late producer cannot reconcile it.
        if not valid or op['phase'] != 'dispatch':
            self.uncertain_worker_cleanup(grant)
            return False
        # Settlement does not rearm dispatch or undo Stop, including a later Stop.
        self._operations.pop(grant.token)
        record.update(quiescent=True, attempt=None)
        if grant.operation == 'remove':
            self._owned_workers.pop(grant.binding.task_id)
        return True

    def inspection_boundary(self):
        with self._stop_lock:
            if (self.mode in ('closed', 'shutdown') or
                    self._inspection_stop_serial != self._stop_serial):
                raise PermissionError('inspection_suspended')
            return self.epoch, self.generation, self._stop_serial

    def resume_inspection(self):
        """Explicit UI acknowledgement, read-only. Never arms mutations."""
        with self._stop_lock:
            if self.mode in ('closed', 'shutdown') or self._inspections:
                return False
            self._inspection_stop_serial = self._stop_serial
        return True

    def cancel_inspections(self, owner=None):
        for item in tuple(self._inspections):
            if owner is None or item.owner == owner:
                if not item.revoked:
                    item.revoked = True
                    item.task.cancel()

    async def settle_inspections(self, timeout=1):
        tasks = {item.task for item in self._inspections if not item.task.done()}
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
        return all(task.done() for task in tasks)

    def validate_inspection(self, item):
        if (item not in self._inspections or item.authority is not self or
                item.revoked or item.task is not asyncio.current_task() or
                item.boundary != self.inspection_boundary() or
                self.clock() >= item.deadline):
            raise PermissionError('inspection_revoked')

    def check_inspection(self):
        self.validate_inspection(_inspection.get())

    def inspection_permit(self, operation, arguments, *, consume=False):
        item = _inspection.get()
        if item is None:
            raise PermissionError('inspection_authority_required')
        self.validate_inspection(item)
        if operation not in {'windows', 'inspect', 'settings_list', 'settings_get'}:
            raise PermissionError('inspection_operation_denied')
        scope = json.dumps([operation, arguments], sort_keys=True, allow_nan=False)
        if item.scope is None:
            item.scope = scope
        if item.scope != scope or (consume and item.consumed):
            raise PermissionError('inspection_scope_mismatch')
        if consume:
            item.consumed = True
        return item

    async def inspect(self, callback, *, timeout=15):
        """Bounded admission, cancellation and stale-result rejection for reads.

        A timed-out/uncooperative job stays tracked until it actually exits.
        Neither cancellation nor a returned timeout claims that its helper died.
        """
        try:
            boundary = self.inspection_boundary()
        except PermissionError as exc:
            return {'ok': False, 'error': str(exc), 'status': str(exc)}
        if len(self._inspections) >= 16:
            return {'ok': False, 'error': 'inspection_capacity'}
        item = Inspection(self, inspection_owner.get(), boundary, self.clock() + timeout)
        async def run():
            token = _inspection.set(item)
            try:
                self.validate_inspection(item)
                result = await callback()
                self.validate_inspection(item)
                return result
            except PermissionError as exc:
                return {'ok': False, 'error': str(exc), 'status': str(exc)}
            finally:
                _inspection.reset(token)
        item.task = asyncio.create_task(run())
        self._inspections.add(item)
        def settled(task):
            self._inspections.discard(item)
            if not task.cancelled():
                task.exception()  # Consume late errors without accepting late results.
        item.task.add_done_callback(settled)
        try:
            done, _ = await asyncio.wait({item.task}, timeout=timeout)
            if done:
                try:
                    current = self.inspection_boundary() == item.boundary and self.clock() < item.deadline
                except PermissionError:
                    current = False
                if item.task.cancelled() or item.revoked or not current:
                    return {'ok': False, 'error': 'inspection_revoked', 'settled': item.task.done()}
                return item.task.result()
            item.revoked = True
            item.task.cancel()
            return {'ok': False, 'error': 'inspection_timeout', 'settled': item.task.done()}
        except asyncio.CancelledError:
            if not item.revoked:
                item.revoked = True
                item.task.cancel()
            raise

    def request_stop(self):
        """Thread-safe revocation latch; callbacks/state cleanup remain loop-owned."""
        with self._stop_lock:
            self._stop_serial += 1
            self.stop_requested.set()

    def register_revoker(self, callback):
        # Establish conservative durable ownership before accepting work whose
        # revocation could fail. No callback is registered on storage failure.
        self._persist()
        self._revokers.append(callback)

    def note_external_uncertainty(self):
        """Existing independent work is not proven stopped by this process."""
        self.quarantined = True
        self._external_uncertainty = True
        self.stop('quarantined')
        self._persist()

    def _persist(self):
        if self.marker_path is None:
            return
        try:
            if self._foreign_marker:
                return  # Never adopt, modify or delete an earlier marker.
            if self.marker_path.exists():
                if self._marker_bytes is None:
                    raise ValueError('unowned_marker')
            else:
                if self._marker_bytes is not None:
                    raise ValueError('owned_marker_missing')
                payload = json.dumps({'version': 2, 'epoch': self.epoch,
                    'unresolved': True, 'reason': 'runtime_requires_reconciliation',
                    'operations': [], 'decisions': []}, sort_keys=True).encode()
                # Never select truncation based on a second existence check.
                with self.marker_path.open('xb') as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._marker_bytes = payload
            if (getattr(self.marker_path.lstat(), 'st_file_attributes', 0) & 0x400 or
                    self.marker_path.is_symlink() or
                    self.marker_path.read_bytes() != self._marker_bytes):
                raise ValueError('marker_readback_failed')
            # Immutable unresolved sentinel: no update, truncation or deletion.
            # This is not an operation journal; disk-backed reconciliation is denied.
        except (OSError, ValueError, AttributeError):
            self.quarantined = True
            self.mode = 'quarantined'
            self.persistence_failed = True
            raise PermissionError('safety_marker_unavailable') from None

    def check(self):
        if self.mode != 'running' or self.quarantined or self.stop_requested.is_set():
            raise PermissionError('dispatch_suspended')

    def resume(self):
        if (self.mode in ('running', 'closed') or self.quarantined or self._operations or self._jobs or
                any(not r['quiescent'] for r in self._owned_workers.values())):
            return False
        boundary = (self.epoch, self.generation, self.mode)
        with self._stop_lock:
            stop_serial = self._stop_serial
        try:
            self._persist()
        except PermissionError:
            return False
        if boundary != (self.epoch, self.generation, self.mode) or self.quarantined:
            return False
        with self._stop_lock:
            if stop_serial != self._stop_serial:
                return False
            self.generation += 1
            self._leases.clear()
            self.stop_requested.clear()
            self._inspection_stop_serial = self._stop_serial
            self.mode = 'running'
        return True

    def issue(self, action_id, owner, digest):
        self.check()
        if not all(isinstance(v, str) and v for v in (action_id, owner, digest)):
            raise PermissionError('invalid_lease')
        if len(self._leases) >= 128 or any(l.action_id == action_id for l in self._leases.values()):
            raise PermissionError('lease_capacity_or_duplicate')
        lease = Lease(secrets.token_hex(24), action_id, owner, digest, self.epoch, self.generation)
        self._leases[lease.token] = lease
        return lease

    def begin(self, lease, owner, digest, *, operation_class='simulation'):
        self.check()
        if operation_class not in ('simulation', 'owned_window', 'external_fixture', 'receiver_fixture', 'native_fixture_creation', 'owned_input'):
            raise PermissionError('unsupported_operation_class')
        if (type(lease) is not Lease or self._leases.get(lease.token) is not lease or
                lease.owner != owner or lease.digest != digest or lease.epoch != self.epoch or
                lease.generation != self.generation):
            raise PermissionError('lease_revoked_or_mismatched')
        self._leases.pop(lease.token)
        self._operations[lease.token] = {'lease': lease, 'operation_id': lease.token,
            'epoch': self.epoch, 'operation_class': operation_class, 'phase': 'registered',
            'submission': 'not_started', 'settled': False, 'cleanup': False,
            'outcome': 'unknown'}
        self._persist()
        self.validate(lease)

    def submitting(self, lease):
        # Logical admission and the synchronous Stop latch share one short gate.
        # Persistence and adapter/OS calls stay outside it. Already admitted work
        # can produce a later effect; this gate does not revoke native execution.
        self.validate(lease)
        self._persist()
        with self._stop_lock:
            self.validate(lease)
            if self._operations[lease.token]['submission'] != 'not_started':
                raise PermissionError('operation_already_admitted')
            self._operations[lease.token].update(phase='dispatch', submission='may_have_started',
                admission_generation=self.generation, admission_stop_serial=self._stop_serial)

    def reconciliation_inventory(self):
        """Non-sensitive snapshot; no leases, request digests or private payloads."""
        return [{k: v for k, v in op.items() if k != 'lease'}
                for op in self._operations.values()]

    def reconcile(self, operation_id, inspector, *, operator):
        """Explicit trusted Python inspection only. Never auto-resume or retry.

        Foreign/old markers and independent workers lack a verified ownership
        contract and remain blocked. Current-epoch fake operations are supported.
        """
        if self.marker_path is not None:
            raise PermissionError('durable_reconciliation_disabled')
        if (self.mode in ('running', 'closed') or self._foreign_marker or
                not isinstance(inspector, SettlementInspector) or
                type(operator) is not str or len(operator) != 32 or
                any(c not in '0123456789abcdef' for c in operator)):
            raise PermissionError('reconciliation_unavailable')
        op = self._operations.get(operation_id)
        if op is None:
            raise PermissionError('unknown_operation')
        if op['operation_class'] != 'simulation':
            raise PermissionError('native_reconciliation_disabled')
        boundary = (self.epoch, self.generation, self.mode)
        try:
            evidence = inspector.inspect(operation_id, op['epoch'])
        except Exception:
            raise PermissionError('inspection_failed') from None
        # A trusted inspector can call other services; those can synchronously
        # stop, take over or close this authority. Inspection grants no right
        # to undo that newer safety decision.
        if boundary != (self.epoch, self.generation, self.mode):
            raise PermissionError('reconciliation_revoked')
        if (type(evidence) is not SettlementEvidence or
                evidence.operation_id != operation_id or evidence.epoch != op['epoch'] or
                type(evidence.observed_at) not in (int, float) or
                not math.isfinite(evidence.observed_at) or
                not 0 <= self.clock() - evidence.observed_at <= 5 or
                type(evidence.settled) is not bool or type(evidence.cleanup) is not bool or
                type(evidence.verdict) is not str or
                evidence.verdict not in {'not_submitted', 'success', 'failure', 'partial', 'unknown', 'running'} or
                type(evidence.reference) is not str or len(evidence.reference) != 64 or
                any(c not in '0123456789abcdef' for c in evidence.reference)):
            raise PermissionError('invalid_settlement_evidence')
        resolved = (evidence.verdict in {'not_submitted', 'success', 'failure'} and
                    evidence.settled and evidence.cleanup and not self._jobs)
        if len(self._decisions) >= 128:
            raise PermissionError('reconciliation_capacity')
        self._decisions.append({'operation_id': operation_id, 'operator': operator,
            'reference': evidence.reference, 'verdict': evidence.verdict, 'resolved': resolved})
        if resolved:
            self._operations.pop(operation_id)
        # Persist evidence before clearing in-memory quarantine. Keep a durable
        # decision record even when the last operation is resolved.
        try:
            self._persist()
        except PermissionError:
            self._operations[operation_id] = op
            self._decisions[-1]['resolved'] = False
            raise
        if boundary != (self.epoch, self.generation, self.mode):
            self._operations[operation_id] = op
            self._decisions[-1]['resolved'] = False
            self.quarantined = True
            raise PermissionError('reconciliation_revoked')
        if resolved and not self._operations and not self._external_uncertainty:
            self.quarantined = False
            self.mode = 'disarmed'
        return {'resolved': resolved, 'remaining': len(self._operations), 'retry_allowed': False}

    def validate(self, lease):
        self.check()
        if (type(lease) is not Lease or lease.generation != self.generation or
                self._operations.get(lease.token, {}).get('lease') is not lease):
            raise PermissionError('lease_revoked_or_mismatched')

    def track(self, task):
        self._jobs.add(task)
        task.add_done_callback(self._jobs.discard)

    def finish(self, lease, *, settled, cleanup, outcome, semantic=None):
        if type(lease) is not Lease:
            raise PermissionError('lease_revoked_or_mismatched')
        operation = self._operations.get(lease.token)
        if operation is None:
            return
        if operation['lease'] is not lease:
            raise PermissionError('lease_revoked_or_mismatched')
        if operation['phase'] == 'uncertain':
            return  # A late adapter result cannot replace independent inspection.
        if semantic is None:
            semantic = 'not_submitted' if outcome == 'not_started' else 'unknown'
        # A revoked producer's result cannot settle submitted work, even when
        # verification finished before stop and cleanup returned afterwards.
        # Never-submitted work can still close after stop, but only if our own
        # submission record agrees. These are in-process simulation guarantees.
        not_submitted = (operation['submission'] == 'not_started' and
                         outcome == 'not_started' and semantic == 'not_submitted')
        verified = (operation['submission'] == 'may_have_started' and
                    outcome == 'complete' and
                    semantic in ('verified_success', 'verified_failure') and
                    lease.epoch == self.epoch and lease.generation == self.generation and
                    self.mode == 'running' and not self.quarantined and
                    not self.stop_requested.is_set())
        if (settled is not True or cleanup is not True or
                any(not task.done() for task in self._jobs) or
                not (not_submitted or verified)):
            operation.update(phase='uncertain', outcome='partial' if outcome == 'partial' else 'unknown',
                             semantic='unknown', settled=settled is True, cleanup=cleanup is True)
            self.quarantined = True
            self.stop('quarantined')
        else:
            self._operations.pop(lease.token)
        self._persist()

    def stop(self, reason='emergency_stop'):
        self.request_stop()
        self.cancel_inspections()
        if self.mode == 'closed':
            return
        if reason not in ('emergency_stop', 'user_takeover', 'quarantined', 'shutdown'):
            reason = 'emergency_stop'
        self.generation += 1
        self._leases.clear()
        self._cleanup_grants.clear()
        if self.quarantined:
            self.mode = 'quarantined'
        elif self.mode != 'emergency_stop' or reason == 'shutdown':
            self.mode = reason
        for callback in tuple(self._revokers):
            try:
                callback(reason)
            except Exception:
                self.quarantined = True
                self._external_uncertainty = True
                self.mode = 'quarantined'
        if self.quarantined or self._external_uncertainty or self._operations or self._jobs:
            try:
                self._persist()
            except PermissionError:
                # Stop is already latched. A prior durable sentinel stays
                # unresolved; missing storage never permits this object to arm.
                self.quarantined = True
                self.persistence_failed = True

    def takeover(self):
        self.stop('user_takeover')

    def status(self):
        return {'mode': self.mode, 'generation': self.generation,
                'quarantined': self.quarantined, 'unresolved': len(self._operations),
                'outstanding': len(self._jobs), 'live_enabled': False,
                'inspections_pending': len(self._inspections),
                'owned_workers_unsettled': sum(not r['quiescent'] for r in self._owned_workers.values()),
                'persistence_failed': self.persistence_failed}

    def close(self):
        self.stop('shutdown')
        if self._operations or self._jobs or any(not r['quiescent'] for r in self._owned_workers.values()):
            self.quarantined = True
        self._persist()
        self.mode = 'closed'
        return self.status()
