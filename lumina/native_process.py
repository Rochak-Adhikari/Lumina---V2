"""Runtime-owned fixed Windows fixture family, never a general worker launcher.

Only a trusted local Python principal can enroll/arm it. No HTTP/model route or
claim of human authentication. Closure relies on the reviewed fixed sleep-only
programs and sole creator; it is NOT containment for arbitrary application code.
"""
import asyncio
import hashlib
import json
import os
import secrets
from .control_authority import WorkerCleanupReceipt
from .process_lifetime import (ProcessCreation, RetainedProcess, ProcessObservation,
    ProcessExitEvidence, ProcessReleaseEvidence, ProcessLifetimeEvidence)

_INTERNAL = object()


async def _retained_call(authority, method, *arguments):
    """Keep native work owned even if its coroutine's observer goes away."""
    job = asyncio.create_task(asyncio.to_thread(method, *arguments))
    authority.track(job)
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        await asyncio.shield(job)
        raise


class NativeFixtureSession:
    def __init__(self, runtime, principal):
        if type(principal) is not object:
            raise PermissionError('local_fixture_principal_required')
        self.runtime, self.principal = runtime, principal
        self.authority, self.manager = runtime.control_authority, runtime.tasks
        self.pid = os.getpid()
        self.owner = secrets.token_hex(24)
        self.prepared = None
        self.adapter = self.creation_task = None

    def validate(self, principal=_INTERNAL):
        if (os.getpid() != self.pid or self.runtime._native_fixture_session is not self or
                self.runtime.control_authority is not self.authority or
                self.runtime.tasks is not self.manager or self.manager.authority is not self.authority or
                (principal is not _INTERNAL and principal is not self.principal)):
            raise PermissionError('local_fixture_session_mismatch')

    def arm(self, principal):
        self.validate(principal)
        if self.adapter is not None:
            return False
        return self.authority.resume()

    def prepare_create(self, principal):
        self.validate(principal)
        self.authority.check()
        if self.prepared is not None or self.adapter is not None:
            raise PermissionError('fixture_creation_already_prepared')
        self.expires = self.authority.clock() + 60
        self.scope = {'operation':'create_fixed_sleep_family', 'root_seconds':2, 'child_seconds':8,
            'owner':self.owner, 'epoch':self.authority.epoch, 'generation':self.authority.generation,
            'expires':self.expires, 'process_count':2}
        digest = hashlib.sha256(json.dumps(self.scope, sort_keys=True).encode()).hexdigest()
        self.prepared = self.authority.issue(secrets.token_hex(24), self.owner, digest)
        return self.prepared

    async def create(self, principal, approval):
        self.validate(principal)
        if (self.prepared is None or approval is not self.prepared or self.adapter is not None or
                self.authority.clock() >= self.expires):
            raise PermissionError('fixture_creation_approval_invalid')
        digest = hashlib.sha256(json.dumps(self.scope, sort_keys=True).encode()).hexdigest()
        self.authority.begin(approval, self.owner, digest, operation_class='native_fixture_creation')
        self.prepared = None
        self.adapter = NativeFixtureLifetime(self, approval, self.expires)
        # Retain actual work before scheduling. Awaiter cancellation cannot orphan it.
        self.creation_task = asyncio.create_task(self._create())
        self.authority.track(self.creation_task)
        self.creation_task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(self.creation_task), 10)
        except TimeoutError:
            self.authority.note_external_uncertainty()
            raise

    async def _create(self):
        a = self.adapter
        try:
            for step in ('job', 'root', 'child'):
                await _retained_call(self.authority, self.authority.native_fixture_creation,
                                     a, a.creation_lease, step)
            a.sealed = True  # no creation entry point can reopen this family
            await _retained_call(self.authority, a.establish)
            a._binding = self.manager.register_native_fixture(a)
            a._authority = self.authority
            self.authority.transfer_native_fixture(a, a.creation_lease, a._binding)
            return a
        except BaseException:
            a.creation_uncertain = True
            a.sealed = True
            self.authority.note_external_uncertainty()
            raise

    def cleanup_approval(self, principal, operation):
        self.validate(principal)
        if self.adapter is None or self.adapter._binding is None:
            raise PermissionError('fixture_not_enrolled')
        return self.manager.prepare_cleanup(self.adapter.resource.creation.task_id,
                                           owner=self.owner, operation=operation)

    async def cleanup(self, principal, approval):
        self.validate(principal)
        if self.adapter is None or approval.binding is not self.adapter._binding:
            raise PermissionError('fixture_cleanup_approval_invalid')
        method = self.manager.cancel_task if approval.operation == 'cancel' else self.manager.remove_task
        return await method(approval.binding.task_id, owner=self.owner, grant=approval)


class NativeFixtureInspector:
    """Fresh original-handle reads, independent of the termination return."""
    def __init__(self, adapter):
        self.adapter = adapter
        self.revision = 0
        self.facts = None

    def inspect(self, resource, inspection):
        a = self.adapter
        if resource is not a.resource or not a.enrollable(a.session.authority, resource):
            raise PermissionError('native_resource_mismatch')
        states = []
        for member, birth in zip(a.members, a.births):
            if a.api.birth(member) != birth or not a.api.in_job(member, a.job):
                raise PermissionError('native_instance_or_job_changed')
            states.append(a.api.state(member))
        accounting = a.api.accounting(a.job)
        a.last_accounting = accounting
        if accounting['total'] != 2 or not 0 <= accounting['active'] <= 2:
            raise PermissionError('native_family_accounting_inconsistent')
        root_state, exit_code = states[0]
        child_running = sum(s[0] != 'exited' for s in states[1:])
        # A transient accounting lag never creates a false zero. Original
        # handles stay open throughout wait/exit and accounting verification.
        active = max(child_running, accounting['active'] - int(root_state == 'running'))
        verified = child_running == 0 and active == 0
        facts = (root_state, exit_code, a.sealed, active, verified)
        if facts != self.facts:
            self.revision += 1
            self.facts = facts
        return ProcessObservation(resource, resource.instance_id, resource.process_handle,
            resource.descendant_scope, self.revision, root_state, exit_code, True,
            a.sealed, active, verified, inspection, a.session.authority.clock())

    def inspect_release(self, resource, inspection):
        a = self.adapter
        return ProcessReleaseEvidence(resource, a.removal_attempt,
            all(m.process.closed and m.thread.closed for m in a.members), a.job.closed,
            inspection, a.session.authority.clock())


class NativeFixtureLifetime(ProcessLifetimeEvidence):
    """Exact-class native bridge. Not a simulation adapter or a default worker."""
    def __init__(self, session, lease, expires):
        self.session, self.creation_lease, self.creation_expires = session, lease, expires
        self.api = self.job = None
        self.members = ()
        self.births = ()
        self.sealed = self.creation_uncertain = False
        self._resource = self._created_resource = self._binding = None
        self.removal_attempt = None
        self.last_accounting = None
        self.termination_submitted = False
        self.native_calls = []  # fixed operation names only, no content

    @property
    def created_resource(self):
        return self._created_resource

    def _creation_step(self, step):
        if step == 'job' and self.job is None and not self.members:
            from .windows_process_api import WindowsFixtureAPI
            self.api = WindowsFixtureAPI()
            self.job = self.api.new_job()  # retained before configuration may fail
            self.native_calls.append('create_job')
            self.api.configure(self.job)
        elif step in ('root', 'child') and self.job is not None and len(self.members) == (0 if step == 'root' else 1):
            member = self.api.create(self.job, step, self.members[0] if step == 'child' else None)
            self.members += (member,)  # retained before independent queries can fail
            self.native_calls.append('create_'+step)
        else:
            raise PermissionError('native_creation_step_invalid')

    def establish(self):
        if not self.sealed or len(self.members) != 2:
            raise PermissionError('native_family_incomplete')
        self.births = tuple(self.api.birth(m) for m in self.members)
        if not all(self.api.in_job(m, self.job) for m in self.members):
            raise PermissionError('native_job_assignment_unverified')
        self.last_accounting = self.api.accounting(self.job)
        if self.last_accounting['total'] != 2:
            raise PermissionError('native_family_coverage_unverified')
        c = ProcessCreation(self.session.owner, secrets.token_hex(16), 'native-fixture-'+secrets.token_hex(8),
            secrets.token_hex(16), self.creation_lease.token, self.creation_lease.action_id)
        self._created_resource = RetainedProcess(c, self.members[0].pid, str(self.births[0]),
                                                self.members[0].process, self.job)
        self._initialize_evidence(self, NativeFixtureInspector(self))

    def enrollable(self, authority, resource):
        self.session.validate()
        return (authority is self.session.authority and self.session.adapter is self and
            resource is not None and resource is self._created_resource and self.sealed and
            not self.creation_uncertain and len(self.members) == len(self.births) == 2 and
            resource.process_handle is self.members[0].process and resource.descendant_scope is self.job)

    def check_effect(self, observation, grant):
        self._check_registration_for_effect(grant)
        if (not self._fresh(observation, observation.inspection) or
                observation is not self.last_observation or not observation.admission_closed):
            raise PermissionError('native_evidence_expired_or_unclosed')
        if grant.operation == 'remove' and (self.exit_evidence is None or not self._settled(observation)):
            raise PermissionError('native_exit_not_verified')

    def _check_registration_for_effect(self, grant):
        if not self.enrollable(self._authority, self.resource) or grant.binding is not self._binding:
            raise PermissionError('native_binding_changed')

    def _cleanup_effect(self, grant, observation):
        if grant.operation == 'cancel':
            if not self._settled(observation):
                if self.termination_submitted:
                    raise PermissionError('native_termination_already_submitted')
                self.termination_submitted = True
                self.native_calls.append('terminate_job')
                self.api.terminate(self.job)
        elif grant.operation == 'remove':
            self.removal_attempt = grant.token
            for member in self.members:
                self.api.close(member.thread)
                self.api.close(member.process)
            self.api.close(self.job)
            self.native_calls.append('release_handles')
        else:
            raise PermissionError('unsupported_native_cleanup')

    async def cleanup(self, authority, grant):
        self._check_registration(authority, grant)
        self._used_attempts.add(grant.token)
        observation = await _retained_call(authority, self._observe, grant)
        await _retained_call(authority, authority.native_fixture_cleanup, self, grant, observation)
        if grant.operation == 'cancel':
            # Bounded independent observer. Timeout never releases handles or
            # clears uncertainty; TaskManager retains the original obligation.
            deadline = asyncio.get_running_loop().time() + 3
            while True:
                observation = await _retained_call(authority, self._observe, grant)
                if self._settled(observation):
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError('native_exit_unconfirmed')
                await asyncio.sleep(.02)
            self.exit_evidence = ProcessExitEvidence(grant.binding.token, grant.token,
                self.resource.creation.attempt_id, observation)
        else:
            inspection = self._inspection(grant)
            evidence = self._inspector.inspect_release(self.resource, inspection)
            if (not self._fresh(evidence, inspection) or evidence.resource is not self.resource or
                    evidence.removal_attempt != grant.token or not evidence.process_handle_closed or
                    not evidence.descendant_scope_closed):
                raise PermissionError('native_release_unverified')
            self.release_evidence, self.released = evidence, True
        return WorkerCleanupReceipt(grant.token, grant.binding.token, grant.binding.generation,
                                    grant.operation, True, grant.operation == 'remove')
