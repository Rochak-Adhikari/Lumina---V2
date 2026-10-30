"""Canonical retained-process evidence and offline simulation contract.

Simulation supplies synthetic tokens. The separately admitted native_process
bridge supplies retained capabilities through the same evidence predicates.
Neither contract permits arbitrary PID discovery or adoption.
M11 owns authorization, deadlines, quarantine and cleanup state throughout.
process_ownership.py remains noncanonical comparison material preserved in place;
its known-child/Job label must not be treated as this domain-evidence contract.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import math

from .control_authority import (
    OwnedWorker, SimulatedWorkerCleanupAdapter, WorkerCleanupGrant, WorkerCleanupReceipt,
)


@dataclass(frozen=True)
class ProcessCreation:
    owner: str
    task_id: str
    worker_id: str
    worker_generation: str
    authorization_id: str
    attempt_id: str


@dataclass(frozen=True, eq=False)
class RetainedProcess:
    creation: ProcessCreation
    pid: int  # Diagnostic only. Never used to find, reopen or terminate a target.
    instance_id: str
    process_handle: object
    descendant_scope: object


@dataclass(frozen=True)
class ProcessInspection:
    """One fresh read of one retained resource for one admitted cleanup attempt.

    Identity is checked with `is`, not by copying fields. This is a trusted fake
    inspector contract, not attestation against malicious in-process Python.
    """
    resource: RetainedProcess
    ownership: str
    cleanup_attempt: str
    issued_at: float


@dataclass(frozen=True)
class ProcessObservation:
    resource: RetainedProcess
    instance_id: str
    process_handle: object
    descendant_scope: object
    revision: int
    root_state: str  # running, exited, inaccessible, invalid, unknown
    exit_code: int | None
    descendants_covered: bool
    admission_closed: bool
    active_descendants: int | None
    descendants_exit_verified: bool = False
    inspection: ProcessInspection | None = None
    observed_at: float | None = None


@dataclass(frozen=True)
class ProcessReleaseEvidence:
    resource: RetainedProcess
    removal_attempt: str
    process_handle_closed: bool
    descendant_scope_closed: bool
    inspection: ProcessInspection | None = None
    observed_at: float | None = None


class SimulatedProcessControl(ABC):
    """Counter-only creator's retained resource. No arbitrary target selection.

    Methods run synchronously inside M11's fake effect gate, never spawn work,
    await, call native APIs or re-enter the authority. A termination return is
    merely an acknowledgement; it is never used as exit evidence.
    """
    @property
    @abstractmethod
    def created_resource(self) -> RetainedProcess: ...

    @abstractmethod
    def request_termination(self, resource, attempt): ...

    @abstractmethod
    def release(self, resource, attempt): ...


class SimulatedProcessInspector(ABC):
    """Separate fake-world state reader; never derives exit from the command reply.

    inspect reads retained instance and descendant-domain state anew for the
    exact inspection request. A new envelope around cached state is insufficient.
    Complete coverage and closed admission alone do not prove every descendant
    exited: descendants_exit_verified must come from the separate state reader.
    wait_changed
    must avoid lost wakeups using the supplied revision and return only after a
    change. Neither call may mutate, terminate, release or create a process.
    """
    @abstractmethod
    def inspect(self, resource, inspection) -> ProcessObservation: ...

    @abstractmethod
    async def wait_changed(self, resource, revision): ...

    @abstractmethod
    def inspect_release(self, resource, inspection) -> ProcessReleaseEvidence: ...


@dataclass(frozen=True)
class ProcessExitEvidence:
    ownership: str
    cleanup_attempt: str
    creation_attempt: str
    observation: ProcessObservation


class ProcessLifetimeEvidence:
    """Shared retained-resource evidence checks; grants no execution authority.

    Fake and separately admitted native adapters use the identical predicates.
    The native adapter is never a SimulatedWorkerCleanupAdapter.
    """
    def _initialize_evidence(self, control, inspector):
        resource = control.created_resource
        if (type(resource) is not RetainedProcess or type(resource.creation) is not ProcessCreation or
                type(resource.pid) is not int or resource.pid <= 0 or
                type(resource.instance_id) is not str or not resource.instance_id or
                resource.process_handle is None or resource.descendant_scope is None or
                not all(type(v) is str and v for v in vars(resource.creation).values())):
            raise PermissionError('retained_process_identity_required')
        self._resource = resource
        self._control = control
        self._inspector = inspector
        self._binding = None
        self._authority = None
        self._used_attempts = set()
        self.last_observation = None
        self.exit_evidence = None
        self.release_evidence = None
        self.released = False

    @property
    def resource(self):
        return self._resource

    def _check_registration(self, authority, grant):
        c = self.resource.creation
        b = getattr(grant, 'binding', None)
        if (authority is not self._authority or type(grant) is not WorkerCleanupGrant or
                type(b) is not OwnedWorker or b is not self._binding or
                b.resource is not self.resource or b.adapter is not self or
                (b.owner, b.task_id, b.generation) != (c.owner, c.task_id, c.worker_generation) or
                self._control.created_resource is not self.resource or self.released or
                not authority.worker_cleanup_registered(grant) or grant.token in self._used_attempts):
            raise PermissionError('process_cleanup_registration_mismatch')

    def _inspection(self, grant):
        now = self._authority.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise PermissionError('process_inspection_clock_invalid')
        return ProcessInspection(self.resource, grant.binding.token, grant.token, now)

    def _fresh(self, evidence, inspection):
        now = self._authority.clock()
        observed = evidence.observed_at
        return (evidence.inspection is inspection and
                type(observed) in (int, float) and math.isfinite(observed) and
                type(now) in (int, float) and math.isfinite(now) and
                inspection.issued_at <= observed <= now and
                0 <= now - inspection.issued_at <= 3.0)

    def _observe(self, grant, *, after=None):
        r = self.resource
        inspection = self._inspection(grant)
        o = self._inspector.inspect(r, inspection)
        if (type(o) is not ProcessObservation or o.resource is not r or
                not self._fresh(o, inspection) or
                o.instance_id != r.instance_id or o.process_handle is not r.process_handle or
                o.descendant_scope is not r.descendant_scope or type(o.revision) is not int or
                o.revision < 0 or (after is not None and o.revision <= after) or
                o.root_state not in ('running', 'exited') or
                (o.root_state == 'exited' and type(o.exit_code) is not int) or
                (o.root_state == 'running' and o.exit_code is not None) or
                o.descendants_covered is not True or type(o.admission_closed) is not bool or
                type(o.descendants_exit_verified) is not bool or
                type(o.active_descendants) is not int or o.active_descendants < 0 or
                (o.descendants_exit_verified and o.active_descendants != 0)):
            raise PermissionError('process_lifetime_unverifiable')
        if self.last_observation is not None and o.revision < self.last_observation.revision:
            raise PermissionError('process_observation_regressed')
        if self.last_observation is not None and (
                (self.last_observation.root_state == 'exited' and o.root_state != 'exited') or
                (self.last_observation.root_state == 'exited' and o.exit_code != self.last_observation.exit_code) or
                (self.last_observation.admission_closed and not o.admission_closed) or
                (self.last_observation.admission_closed and
                 o.active_descendants > self.last_observation.active_descendants) or
                (self._settled(self.last_observation) and not self._settled(o)) or
                (o.revision == self.last_observation.revision and
                 any(getattr(o, field) != getattr(self.last_observation, field) for field in (
                     'root_state', 'exit_code', 'descendants_covered', 'admission_closed',
                     'active_descendants', 'descendants_exit_verified')))):
            raise PermissionError('process_observation_contradictory')
        self.last_observation = o
        return o

    @staticmethod
    def _settled(o):
        # Keep the complete predicate here too: a helper cannot turn a known
        # child count or a containment label into proof of tree quiescence.
        return (type(o) is ProcessObservation and o.root_state == 'exited' and
                type(o.exit_code) is int and o.descendants_covered is True and
                o.admission_closed is True and o.descendants_exit_verified is True and
                type(o.active_descendants) is int and o.active_descendants == 0)

class SimulatedProcessLifetime(ProcessLifetimeEvidence, SimulatedWorkerCleanupAdapter):
    """Canonical fake creator/cleanup adapter; never invokes a native API."""
    def __init__(self, control, inspector):
        if (not isinstance(control, SimulatedProcessControl) or
                not isinstance(inspector, SimulatedProcessInspector)):
            raise PermissionError('process_fixture_interfaces_required')
        self._initialize_evidence(control, inspector)

    def register(self, manager):
        """Trusted fake creation -> existing M11 ownership. No process discovery."""
        c = self.resource.creation
        if (self._binding is not None or manager.workers.get(c.worker_id) is not self or
                manager._get(c.task_id).worker != c.worker_id or
                self._control.created_resource is not self.resource):
            raise PermissionError('process_creation_registration_mismatch')
        binding = manager.register_simulated_cleanup(c.task_id, owner=c.owner,
            generation=c.worker_generation, resource=self.resource)
        self._binding, self._authority = binding, manager.authority
        return binding

    async def cleanup(self, authority, grant):
        self._check_registration(authority, grant)
        self._used_attempts.add(grant.token)
        # Inspect first, then let M11 revalidate expiry/Stop at the actual gate.
        # A slow or reentrant reader cannot consume time inside the Stop lock.
        observation = self._observe(grant)
        def effect():
            if (not self._fresh(observation, observation.inspection) or
                    self._control.created_resource is not self.resource):
                raise PermissionError('process_evidence_changed_before_effect')
            if grant.operation == 'cancel':
                if not self._settled(observation):
                    self._control.request_termination(self.resource, grant.token)
            elif grant.operation == 'remove':
                if self.exit_evidence is None or not self._settled(observation):
                    raise PermissionError('process_exit_not_settled')
                self._control.release(self.resource, grant.token)
            else:
                raise PermissionError('unsupported_process_operation')
        authority.worker_cleanup_effect(grant, self.resource, effect)
        if grant.operation == 'cancel':
            observation = self._observe(grant)
            while not self._settled(observation):
                await self._inspector.wait_changed(self.resource, observation.revision)
                observation = self._observe(grant, after=observation.revision)
            self.exit_evidence = ProcessExitEvidence(grant.binding.token, grant.token,
                self.resource.creation.attempt_id, observation)
        else:
            inspection = self._inspection(grant)
            evidence = self._inspector.inspect_release(self.resource, inspection)
            if (type(evidence) is not ProcessReleaseEvidence or evidence.resource is not self.resource or
                    not self._fresh(evidence, inspection) or
                    evidence.removal_attempt != grant.token or evidence.process_handle_closed is not True or
                    evidence.descendant_scope_closed is not True):
                raise PermissionError('process_release_unverified')
            self.release_evidence = evidence
            self.released = True
        return WorkerCleanupReceipt(grant.token, grant.binding.token,
            grant.binding.generation, grant.operation, True, grant.operation == 'remove')
