"""P1.1 offline one-action seam, not the P4 autonomous desktop loop.

Uses Runtime's controller, authority, confirmations and TaskManager. No capture,
provider, native adapter, scheduler, HTTP/tool registration or automatic approval.
"""
import asyncio

from .computer_action import (DesktopSimulationAdapter, ObservationRef, SafeError,
                              Ask, Wait, Done, Focus)
from .computer_use_model import parse, KINDS
from .tasks import WorkerResult


async def request_observation(stream, *, after_sequence=0, deadline):
    """C02 latest-only wait on the existing capture owner, never start capture.

    Cancelling this wait detaches only this subscriber. Source replacement and
    pause are unavailable, never permission to silently choose another source.
    """
    import math
    if (type(after_sequence) is not int or after_sequence < 0 or
            type(deadline) not in (int, float) or not math.isfinite(deadline)):
        return SafeError('invalid_observation_request')
    epoch = stream._evidence_revoked
    if stream.session_id is None or stream.capture_state in ('paused', 'failed'):
        return SafeError('observation_unavailable')
    while True:
        # Existing stream notification covers both frames and lifecycle changes.
        # Read it before state to avoid a lost wakeup; no separate capture loop.
        changed = stream._changed
        if epoch is not stream._evidence_revoked or epoch.is_set():
            return SafeError('session_invalidated')
        remaining = deadline - stream.clock()
        if remaining <= 0: return SafeError('observation_timeout')
        current = stream.latest()
        if current is not None and current.sequence > after_sequence:
            return current
        try:
            await asyncio.wait_for(changed.wait(), timeout=remaining)
        except TimeoutError:
            return SafeError('observation_timeout')


class SimulatedDesktopTask:
    label = 'Simulated desktop action (offline only)'

    def __init__(self, runtime, observations, adapter, raw, *, owner, target,
                 expected_digest, goal_predicate, controller=None, binding=None,
                 allow_reground=False):
        if not isinstance(adapter, DesktopSimulationAdapter):
            raise TypeError('desktop_simulation_required')
        observation = observations.latest()
        if observation is None:
            raise ValueError('fresh_shared_observation_required')
        from .computer_geometry import TargetBinding
        if binding is not None and (type(binding) is not TargetBinding or controller is None):
            raise ValueError('invalid_binding')
        try:
            reference = binding.inference.reference if binding else ObservationRef(
                observation.session_id, observation.source_id, observation.sequence)
        except AttributeError:
            raise ValueError('invalid_binding') from None
        proposal = parse(raw, KINDS, reference)
        if isinstance(proposal, SafeError):
            raise ValueError(proposal.code)
        if (isinstance(proposal.action, Done) and proposal.action.predicate != goal_predicate or
                isinstance(proposal.action, Focus) and proposal.action.window != target.window_id):
            raise ValueError('desktop_scope_mismatch')
        if not isinstance(proposal.action, (Ask, Wait)) and binding is None:
            raise ValueError('binding_required')
        self.rt, self.owner, self.proposal = runtime, owner, proposal
        if controller is not None and (controller.authority is not runtime.control_authority or
                controller.observations is not observations or controller.adapter is not adapter or
                controller.owner != owner):
            raise ValueError('controller_scope_mismatch')
        self.controller = controller if controller is not None else runtime.simulation_controller(observations, adapter, owner=owner)
        self.controller.clock = observations.clock
        self.active, self.reason, self.session = False, None, None
        self.prepared = None
        if isinstance(proposal.action, (Ask, Wait)):
            # Neither starts a timer/loop nor grants action permission.
            self.reason = 'clarification_required' if isinstance(proposal.action, Ask) else 'observation_required'
        else:
            self.prepared = self.controller.propose_desktop(proposal, target,
                expected_digest=expected_digest, binding=binding, allow_reground=allow_reground)
            self.reason = 'exact_approval_required'

    def snapshot(self):
        action = self.controller.snapshot(self.prepared['action_id']) if self.prepared else None
        return {'kind': 'desktop_simulation', 'phase': action['state'] if action else 'proposed',
                'reason': self.reason, 'scope_active': self.active,
                'action_kind': self.proposal.action.kind, 'simulated': True,
                'admission': action['admission'] if action else 'not_admitted',
                'outcome': action['outcome'] if action else 'not_started',
                'verification': action['verification']['verdict'] if action and action['verification'] else 'not_run'}

    def check(self, *, active=True, starting=False):
        if self.prepared is None or active and not self.active:
            raise PermissionError('desktop_scope_revoked')
        if not starting and self.session.status != 'RUNNING':
            raise PermissionError('goal_not_running')
        self.controller._check(self.controller._actions[self.prepared['action_id']])

    def approve(self, *, owner):
        if owner != self.owner or self.session.status != 'WAITING_FOR_USER' or self.prepared is None:
            raise PermissionError('desktop_approval_unavailable')
        p = self.prepared
        result = self.controller.approve(p['action_id'], p['confirmation'], p['request'], owner=owner)
        if result['state'] != 'approved':
            raise PermissionError('desktop_approval_rejected')
        self.active, self.reason = True, None
        return self.rt.tasks.start_goal(self.session.id, owner=owner)

    def revoke(self, reason):
        self.active, self.reason = False, 'desktop_scope_revoked'
        if self.prepared is None:
            return False
        action_id = self.prepared['action_id']
        record = self.controller._actions[action_id]
        uncertain = record.dispatched and record.state.value != 'succeeded'
        self.controller.cancel_action(action_id)
        return uncertain

    async def run(self):
        self.check()
        p = self.prepared
        result = await self.controller.execute('execute_confirmed', action_id=p['action_id'], request=p['request'])
        self.active = False
        if result['ok'] and result['semantic'] == 'verified_success':
            status, summary = 'COMPLETED', 'Simulated postcondition independently verified.'
        elif result['semantic'] == 'unknown':
            status, summary = 'CLEANUP_UNKNOWN', 'Simulated outcome unverified; no retry.'
        else:
            status, summary = 'ERROR', 'Simulated action did not pass verification.'
        return WorkerResult(summary, summary, goal_status=status)
