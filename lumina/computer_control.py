"""Snapshot-bound UIA control; trusted runtime owns permission and consequence review.

No coordinates, shortcuts, clipboard or raw shell. Private editable values are
represented only by per-provider HMAC; never return or log typed content.

invoke/type accept focus=False (strict original foreground/input state) or
focus=True (explicitly confirmed foreground activation of this exact window).
The latter permits GUI confirmation; provider refuses any control/geometry drift
and checks new user input during activation and immediately before the action.
An OS focus denial requires fresh inspection, not input-thread attachment.

ComputerControl(provider=None, clock=time.monotonic) exposes async execute:
 list_windows(), inspect(window), invoke(snapshot,control,focus=False),
 type(snapshot,control,text,focus=False), execute_confirmed(confirmation,request),
 cancel(confirmation), status(). Windows/controls are returned IDs, not titles.
The trusted caller must present original text through a private confirmation UI,
never log text arguments, and retain only the returned request in its audit log.
Cancel a running asyncio task to kill/reap the helper; cancel(confirmation) only
revokes a pending request. Native effects already submitted cannot be rolled back.
"""
import copy
import hashlib
import hmac
import secrets
import asyncio
import json
import math
from dataclasses import asdict, dataclass, field
from .computer_windows import ConfirmedService, ComputerError
from .control_authority import ControlAuthority
from .computer_action import (ActionState, TERMINAL, TargetEvidence, IntendedAction,
                              ExecutionResult, Verification, SimulationAdapter,
                              DesktopSimulationAdapter, ObservationRef, SafeError,
                              Text, Ask, Wait, Done, Focus)
from .computer_geometry import (TargetBinding, GroundingProof, binding_scope,
                                validate_observation, validate_target, reground)


class ComputerControl(ConfirmedService):
    inspection_actions = frozenset({'list_windows', 'inspect', 'inspect_control', 'invoke', 'type'})
    def __init__(self, provider=None, **kwargs):
        super().__init__(provider, **kwargs)
        self.snapshots = {}
        self._text_key = secrets.token_bytes(32)

    async def _dispatch(self, action, args):
        if action == 'list_windows':
            self._keys(args, set(), {'process_id'})
            if args and (type(args['process_id']) is not int or args['process_id'] <= 0):
                raise ComputerError('invalid_arguments')
            return await self._call('windows', **args)
        if action in {'inspect', 'inspect_control'}:
            self._keys(args, {'window', 'control'} if action == 'inspect_control' else {'window'})
            if any(not isinstance(value, str) or not 0 < len(value) <= 2048 or '\x00' in value
                   for value in args.values()):
                raise ComputerError('invalid_arguments')
            result = await self._call('inspect', window=args['window'])
            if result.get('ok') and result.get('window') != args['window']:
                raise ComputerError('window_identity_changed')
            if result.get('ok') and action == 'inspect_control':
                matches = [c for c in result.get('controls', []) if c.get('id') == args['control']]
                if len(matches) != 1:
                    raise ComputerError('ambiguous_or_missing_control')
                # Re-query the same window; never turn cached UI text/bounds into
                # a mutation capability or interpret them as instructions.
                return {k: v for k, v in {**result, 'controls': matches,
                        'read_only': True, 'mutation_supported': False}.items() if k != 'snapshot'}
            if result['ok']:
                token = secrets.token_urlsafe(24)
                self.snapshots = {k: v for k, v in self.snapshots.items() if self.clock() - v[0] < 60}
                if len(self.snapshots) >= 64:
                    self.snapshots.pop(next(iter(self.snapshots)))
                self.snapshots[token] = (self.clock(), copy.deepcopy(result))
                result['snapshot'] = token
            return result
        if action in ('invoke', 'type'):
            self._keys(args, {'snapshot', 'control'} | ({'text'} if action == 'type' else set()), {'focus'})
            focus = args.get('focus', False)
            if type(focus) is not bool:
                raise ComputerError('invalid_focus')
            item = self.snapshots.get(args['snapshot'])
            if item is None or self.clock() - item[0] >= 60:
                raise ComputerError('stale_snapshot')
            snapshot = item[1]
            matches = [c for c in snapshot['controls'] if c['id'] == args['control']]
            if len(matches) != 1:
                raise ComputerError('ambiguous_or_missing_control')
            control = matches[0]
            pattern = 'Invoke' if action == 'invoke' else 'Value'
            if pattern not in control['patterns'] or not control['enabled'] or control['password']:
                raise ComputerError('unsupported_control')
            private = dict(operation=action, window=snapshot['window'], expected=snapshot, focus=focus,
                           control=copy.deepcopy(control))
            public = dict(operation=action, snapshot=args['snapshot'], window=snapshot['window'], focus=focus,
                          control=copy.deepcopy(control), consequence='caller_must_review_exact_action')
            if action == 'type':
                text = args['text']
                if not isinstance(text, str) or len(text) > 8192 or '\x00' in text:
                    raise ComputerError('invalid_text')
                private['text'] = text
                public['text_length'] = len(text)
                public['text_binding'] = hmac.new(self._text_key, text.encode(), hashlib.sha256).hexdigest()
            return self._prepare(public, private)
        if action == 'execute_confirmed':
            self._keys(args, {'confirmation', 'request'})
            request = self._consume(args['confirmation'], args['request'])
            # Invalidate all snapshots before a possible mutation, including timeout.
            self.snapshots.clear()
            return await self._call('control_apply', **{k: v for k, v in request.items() if k != 'operation'},
                                    verb=request['operation'])
        raise ComputerError('unsupported_action')


@dataclass
class _ActionRecord:
    spec: IntendedAction
    confirmation: str
    scope: dict
    generation: int
    state: ActionState = ActionState.PROPOSED
    history: list = field(default_factory=lambda: [ActionState.PROPOSED])
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    reason: str | None = None
    dispatched: bool = False
    outcome: str = 'not_started'
    semantic: str = 'not_submitted'
    verification: Verification | None = None
    cancellation: str = 'not_requested'
    cleanup: str = 'not_needed'
    lease: object = None
    observation_epoch: object = None
    admission: str = 'not_admitted'
    binding: object = None


class IsolatedComputerControl(ConfirmedService):
    """Safety core using existing confirmation storage and mutation serialization.

    Runtime may inject exact owned-window, external-fixture or cooperative
    receiver adapters. WindowsProvider can never be selected by default.
    propose/approve/execute/cancel/stop/resume are trusted test-owner APIs, not
    model tools. Approval is consumed through ConfirmedService._consume, then
    its immutable action scope and expiry are rechecked before dispatch.
    """
    def __init__(self, observations, adapter, *, authority=None, owner='fixture', timeout=5.0, cleanup_timeout=.5, **kwargs):
        from .windows_input import WindowsInputAdapter, FakeInputExecutor
        from .practice_input import NativePracticeAdapter
        self.native_input = type(adapter) is NativePracticeAdapter
        self.input_facade = type(adapter) is WindowsInputAdapter or self.native_input
        if (isinstance(adapter, WindowsInputAdapter) and not self.input_facade or
                isinstance(adapter, FakeInputExecutor)):
            raise TypeError('exact_input_facade_required')
        from .owned_windows import OwnedWindowsAdapter
        from .external_windows import ExternalWindowsAdapter
        from .receiver_adapter import ReceiverAdapter
        self.native_owned = type(adapter) is OwnedWindowsAdapter
        self.native_external = type(adapter) is ExternalWindowsAdapter
        self.receiver_adapter = type(adapter) is ReceiverAdapter
        self.native_adapter = self.native_owned or self.native_external or self.receiver_adapter
        if not isinstance(adapter, SimulationAdapter) and not self.native_adapter and not self.native_input:
            raise TypeError('An explicit simulation or admitted Runtime adapter is required')
        if (self.native_adapter or self.native_input) and (authority is None or adapter.authority is not authority or
                                  adapter.observations is not observations):
            raise TypeError('Runtime adapter requires its authority and stream')
        for value in (timeout, cleanup_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError('Timeout must be positive, finite and at most 60 seconds')
        super().__init__(provider=adapter, **kwargs)
        self.observations, self.adapter = observations, adapter
        self.timeout, self.cleanup_timeout = timeout, cleanup_timeout
        self.mode, self.generation = 'running', 0
        self._actions = {}
        self._jobs = set()
        self._job = None
        self._quarantined = False
        self._text_key = secrets.token_bytes(32)
        self.authority = authority if authority is not None else ControlAuthority()
        self.owner = owner
        # Trusted offline principal: deliberately never serialized or sent to HTTP.
        self.approval_owner = object()
        self.authority.register_revoker(self._authority_stop)
        if self.input_facade:
            adapter.attach(self)

    def _authority_stop(self, reason):
        self._suspend('user_takeover' if reason == 'user_takeover' else 'emergency_stop')

    @staticmethod
    def _canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

    @staticmethod
    def _digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)

    def _transition(self, record, state, reason=None):
        if record.state not in TERMINAL:
            record.state, record.reason = state, reason
            record.history.append(state)

    def _check(self, record, *, approval=True):
        if record.state in TERMINAL:
            raise ComputerError(record.reason or 'terminal_action')
        try:
            self.authority.check()
            if (record.scope['authority_epoch'] != self.authority.epoch or
                    record.scope['authority_generation'] != self.authority.generation):
                raise PermissionError('dispatch_suspended')
            if record.lease is not None:
                self.authority.validate(record.lease)
        except PermissionError:
            raise ComputerError('dispatch_suspended') from None
        if self.mode != 'running' or record.generation != self.generation or record.stop.is_set():
            raise ComputerError('dispatch_suspended')
        if self.observations.session_id != record.spec.session_id:
            raise ComputerError('session_invalidated')
        if record.observation_epoch is not self.observations._evidence_revoked:
            raise ComputerError('session_invalidated')
        current = self.observations.latest()
        if current is None or current.sequence < record.spec.observation_sequence:
            raise ComputerError('stale_observation')
        if approval and not record.spec.expires_at - 60 <= self.clock() < record.spec.expires_at:
            raise ComputerError('approval_expired')
        if self.native_input and record.dispatched and not approval:
            self.adapter.validate_after(record.spec, record.binding)
        elif record.binding is not None:
            self._validate_desktop_binding(record.binding, record.spec.desktop, record.spec.target)
        elif record.spec.desktop is not None and record.spec.desktop.observation != ObservationRef(
                current.session_id, current.source_id, current.sequence):
            # P1.1 never rebinds coordinates to a newer frame. P1.2 owns proofs.
            raise ComputerError('desktop_observation_changed')
        return current

    def _binding_signature(self, binding):
        return hmac.new(self._text_key, self._canonical(binding_scope(binding)).encode(), hashlib.sha256).hexdigest()

    def prepare_desktop_binding(self, target, *, for_focus=False):
        """Freeze current inference evidence before a delayed result; no capture."""
        try:
            self.authority.check()
        except PermissionError:
            raise ComputerError('dispatch_suspended') from None
        if (self.mode != 'running' or self._quarantined or self.native_adapter or
                (not isinstance(self.adapter, DesktopSimulationAdapter) and not self.native_input)):
            raise ComputerError('desktop_simulation_required')
        observation = self.observations.latest()
        snapshot = self._grounding_snapshot(observation)
        if for_focus and not self.native_input:
            raise ComputerError('native_focus_required')
        checked = validate_target(snapshot, snapshot, allow_unfocused=for_focus)
        if isinstance(checked, SafeError): raise ComputerError(checked.code)
        if snapshot.evidence != target:
            raise ComputerError('target_mismatch')
        validated = validate_observation(observation, snapshot, self.clock())
        if isinstance(validated, SafeError): raise ComputerError(validated.code)
        binding = TargetBinding(validated, snapshot, self.owner, self.authority.epoch,
            self.authority.generation, self.clock() + 60, self.observations._evidence_revoked,
            validated, GroundingProof(validated.reference, validated.reference, 'original_frame'))
        from dataclasses import replace
        return replace(binding, signature=self._binding_signature(binding))

    def _grounding_snapshot(self, observation):
        try:
            return self.adapter.grounding_snapshot(observation)
        except Exception:
            raise ComputerError('target_inspection_failed') from None

    def _validate_desktop_binding(self, binding, proposal, target, *, allow_new=False):
        try:
            self.authority.check()
            if (type(binding) is not TargetBinding or not hmac.compare_digest(binding.signature, self._binding_signature(binding)) or
                    binding.owner != self.owner or binding.authority_epoch != self.authority.epoch or
                    binding.generation != self.authority.generation or
                    binding.revoked is not self.observations._evidence_revoked):
                raise ComputerError('binding_revoked_or_invalid')
            if binding.target.evidence != target:
                raise ComputerError('target_mismatch')
        except ComputerError:
            raise
        except (PermissionError, TypeError, ValueError, AttributeError, OverflowError):
            raise ComputerError('binding_revoked_or_invalid') from None
        observation = self.observations.latest()
        result = reground(proposal, binding, observation, self._grounding_snapshot(observation),
                          self.clock(), allow_new=allow_new, allow_unfocused=self.native_input and isinstance(proposal.action, Focus))
        if isinstance(result, SafeError): raise ComputerError(result.code)
        return result

    def reground_desktop(self, action_id):
        """Explicit read-only proof refresh, never a new operation/approval scope."""
        record = self._actions.get(action_id)
        if record is None or record.state not in (ActionState.AWAITING_APPROVAL, ActionState.APPROVED) or record.binding is None:
            raise ComputerError('reground_unavailable')
        try:
            record.binding = self._validate_desktop_binding(record.binding, record.spec.desktop,
                                                           record.spec.target, allow_new=True)
            self._check(record)
        except ComputerError as exc:
            self._reject(record, exc.code)
        return self.snapshot(action_id)

    def propose_desktop(self, proposal, target, *, expected_digest, binding=None, allow_reground=False):
        """Trusted fake-only seam; no native adapter or implicit approval."""
        return self.propose('owned_input' if self.native_input else 'simulate_desktop', target, expected_digest=expected_digest,
                            desktop=proposal, binding=binding, allow_reground=allow_reground)

    def propose(self, operation, target, *, expected_digest, text=None, desktop=None, binding=None, allow_reground=False):
        """Fixed admitted operations; policy is derived, never model supplied."""
        try:
            self.authority.check()
        except PermissionError:
            raise ComputerError('dispatch_suspended') from None
        if self.mode != 'running' or self._quarantined:
            raise ComputerError('dispatch_suspended')
        operations = (('owned_input',) if self.native_input else self.adapter.operations if self.native_adapter else
                      ('invoke', 'type', 'simulate_desktop') if isinstance(self.adapter, DesktopSimulationAdapter)
                      else ('invoke', 'type'))
        if operation in ('simulate_desktop', 'owned_input'):
            from .computer_use_model import normalize
            observation = self.observations.latest()
            if (self.native_adapter or (not isinstance(self.adapter, DesktopSimulationAdapter) and not self.native_input) or
                    observation is None or desktop is None or text is not None):
                raise ComputerError('desktop_simulation_required')
            if type(allow_reground) is not bool:
                raise ComputerError('invalid_binding')
            # Never invent original target evidence after an untrusted result
            # has arrived. The caller freezes this before requesting inference.
            if binding is None:
                raise ComputerError('binding_required')
            if type(binding) is not TargetBinding:
                raise ComputerError('invalid_binding')
            try:
                reference = binding.inference.reference
            except AttributeError:
                raise ComputerError('invalid_binding') from None
            desktop = normalize(desktop, reference)
            if isinstance(desktop, SafeError) or isinstance(desktop.action, (Ask, Wait)):
                raise ComputerError('invalid_desktop_proposal')
            binding = self._validate_desktop_binding(binding, desktop, target, allow_new=allow_reground)
        elif desktop is not None or binding is not None or allow_reground:
            raise ComputerError('invalid_operation')
        if (operation not in operations or type(target) is not TargetEvidence or
                not self._digest(expected_digest)):
            raise ComputerError('invalid_operation')
        if desktop and isinstance(desktop.action, Focus) and desktop.action.window != target.window_id:
            raise ComputerError('invalid_target')
        if (any(not isinstance(v, str) or not 1 <= len(v) <= 256 or '\x00' in v
                for v in (target.window_id, target.control_id, target.revision)) or
                type(target.input_epoch) is not int or target.input_epoch < 0 or
                any(type(v) is not bool for v in (target.foreground, target.enabled, target.password)) or
                type(target.patterns) is not tuple or any(p not in operations for p in target.patterns)):
            raise ComputerError('invalid_target')
        if (not target.enabled or (not self.native_adapter and not target.foreground and not (self.native_input and desktop and isinstance(desktop.action, Focus))) or
                target.password or operation not in target.patterns):
            raise ComputerError('unsupported_target')
        if ((operation in ('invoke', 'clear_owned_text', 'select_owned_text') and text is not None) or
                (operation in ('type', 'set_owned_text') and (not isinstance(text, str) or len(text) > 8192 or '\x00' in text))):
            raise ComputerError('invalid_arguments')
        if self.native_owned and ((text is not None and len(text) > 2048) or target != self.adapter.target):
            raise ComputerError('unsupported_target')
        if self.native_input:
            self.adapter.validate_proposal(desktop, target)
        if self.native_external or self.receiver_adapter:
            self.adapter.validate_proposal(operation,target,text,expected_digest)
        observation = self.observations.latest()
        if observation is None:
            raise ComputerError('stale_observation')
        # Bounded records, without silently forgetting running/uncertain work.
        if len(self._actions) >= 128:
            raise ComputerError('action_capacity')
        action = IntendedAction(
            secrets.token_urlsafe(24), observation.session_id, desktop.observation.sequence if desktop else observation.sequence,
            operation, target, 'reversible_local' if self.native_adapter else 'sensitive' if operation == 'type' or (desktop and isinstance(desktop.action, Text)) else 'consequential',
            'owned_surface_only' if self.native_owned else 'registered_fixture_only' if self.native_external or self.receiver_adapter else 'exact_operation', binding.deadline if binding else self.clock() + 60, expected_digest, text, desktop)
        scope = asdict(action)
        payload = scope.pop('desktop')
        if payload is not None:
            # Bind all arguments without exposing literal text/question content.
            scope['desktop'] = {'kind': desktop.action.kind,
                'observation': asdict(desktop.observation),
                'binding': hmac.new(self._text_key, self._canonical(payload).encode(), hashlib.sha256).hexdigest()}
            scope['desktop']['geometry_binding'] = binding.signature
        scope.update(owner=self.owner, authority_epoch=self.authority.epoch,
                     authority_generation=self.authority.generation,
                     evaluator_version='native-practice-readback-v1' if self.native_input else 'receiver-state-readback-v1' if self.receiver_adapter else 'owned-window-readback-v1' if self.native_owned else 'external-win32-readback-v1' if self.native_external else 'simulation-postcondition-v1')
        scope.pop('text')
        # Fixed JSON representation also distinguishes booleans from numbers.
        scope['target']['patterns'] = list(target.patterns)
        if text is not None:
            scope.update(text_length=len(text), text_binding=hmac.new(
                self._text_key, text.encode(), hashlib.sha256).hexdigest())
        prepared = self._prepare(scope, {'action_id': action.action_id})
        record = _ActionRecord(action, prepared['confirmation'], copy.deepcopy(scope), self.generation)
        record.observation_epoch = self.observations._evidence_revoked
        record.binding = binding
        self._actions[action.action_id] = record
        self._transition(record, ActionState.AWAITING_APPROVAL)
        return {**prepared, 'action_id': action.action_id}

    def approve(self, action_id, confirmation, request, *, owner=None):
        """Fixture/trusted-owner consent only. Never inferred from screen content."""
        record = self._actions.get(action_id)
        if record is None:
            return {'ok': False, 'error': 'unknown_action'}
        if owner != self.owner:
            return {'ok': False, 'error': 'approval_owner_mismatch'}
        try:
            self._check(record)
            if record.state != ActionState.AWAITING_APPROVAL:
                raise ComputerError('approval_state')
            if confirmation != record.confirmation or self._canonical(request) != self._canonical(record.scope):
                raise ComputerError('approval_scope_mismatch')
            approved = self._consume(confirmation, request)
            if approved != {'action_id': action_id}:
                raise ComputerError('approval_scope_mismatch')
            self._transition(record, ActionState.APPROVED)
        except (ComputerError, ValueError, TypeError) as exc:
            reason = exc.code if isinstance(exc, ComputerError) else 'invalid_request'
            self._reject(record, reason)
        return self.snapshot(action_id)

    def _reject(self, record, reason):
        state = (ActionState.EXPIRED if reason in ('approval_expired', 'proposal_expired') else
                 ActionState.CANCELLED if reason in ('session_invalidated', 'dispatch_suspended') else
                 ActionState.FAILED)
        self._transition(record, state, reason)
        self.pending.pop(record.confirmation, None)

    def snapshot(self, action_id):
        record = self._actions[action_id]
        # Lazily revoke pending approval when source/expiry changed.
        if record.state in (ActionState.AWAITING_APPROVAL, ActionState.APPROVED):
            try:
                self._check(record)
            except ComputerError as exc:
                self._reject(record, exc.code)
        return {'ok': record.state == ActionState.SUCCEEDED,
                'action_id': action_id, 'state': record.state.value,
                'approval_id': record.confirmation,
                'history': [s.value for s in record.history],
                'scope': copy.deepcopy(record.scope), 'reason': record.reason,
                'outcome': record.outcome, 'cancellation': record.cancellation,
                'admission': record.admission,
                'submission_receipt': asdict(self.adapter.receipt(action_id)) if self.input_facade else None,
                'grounding': ({'inference_sequence': record.binding.inference.reference.sequence,
                    'dispatch_sequence': record.binding.current.reference.sequence,
                    'method': record.binding.proof.method} if record.binding else None),
                'semantic': record.semantic,
                'cleanup': record.cleanup, 'control_state': self.mode,
                'verification': asdict(record.verification) if record.verification else None}

    def cancel_action(self, action_id, *, reason='cancelled'):
        record = self._actions.get(action_id)
        if record and record.state not in TERMINAL:
            # Fixed codes only; do not store user/model text as failure reasons.
            reason = reason if reason in ('cancelled', 'emergency_stop', 'user_takeover', 'session_invalidated') else 'cancelled'
            self._transition(record, ActionState.CANCELLED, reason)
            record.stop.set()
            record.cancellation = 'requested' if record.dispatched else 'not_needed'
            if record.dispatched and record.outcome == 'not_started':
                record.outcome = 'unknown'
            self.pending.pop(record.confirmation, None)

    def emergency_stop(self):
        self.authority.stop()

    def user_takeover(self):
        self.authority.takeover()

    def _suspend(self, mode):
        if self.mode == 'closed':
            return
        # Takeover must never downgrade a latched emergency stop.
        if self.mode != 'emergency_stop':
            self.mode = mode
        self.generation += 1
        self.pending.clear()
        for action_id in self._actions:
            self.cancel_action(action_id, reason=mode)

    def resume(self):
        """Explicit trusted transition; no old proposal or consent is restored."""
        if (self.mode in ('running', 'closed') or self._quarantined or
                any(not job.done() for job in self._jobs) or self.lock.locked() or
                self.observations.latest() is None):
            return {'ok': False, 'error': 'resume_requires_safe_fresh_state'}
        if not self.authority.resume():
            return {'ok': False, 'error': 'resume_requires_safe_fresh_state'}
        self.generation += 1
        self.mode = 'running'
        return {'ok': True, 'status': 'resumed'}

    async def execute(self, action, **args):
        # Reuse the existing service lock and process-wide mutation lock.
        # No inherited status/cancel/provider path is exposed by this core.
        if action != 'execute_confirmed':
            return {'ok': False, 'error': 'unsupported_action'}
        try:
            return await super().execute(action, **args)
        except asyncio.CancelledError:
            # Also covers cancellation while waiting for the shared service lock,
            # before _dispatch has had a chance to take ownership.
            action_id = args.get('action_id')
            if isinstance(action_id, str):
                self.cancel_action(action_id)
            raise

    def _track(self, coroutine):
        job = asyncio.create_task(coroutine)
        self.authority.track(job)
        self._jobs.add(job)
        def finished(task):
            self._jobs.discard(task)
            if not task.cancelled():
                task.exception()  # Drain late failures; never update action state.
        job.add_done_callback(finished)
        return job

    async def _step(self, factory, record):
        async def guarded():
            # Scheduling a coroutine is a yield boundary: check again when it
            # actually starts, before entering any adapter method.
            self._check(record, approval=record.state != ActionState.VERIFYING)
            if record.state == ActionState.EXECUTING:
                if self.input_facade:
                    self.adapter.preflight()
                    self._check(record)
                self.authority.submitting(record.lease)
                record.admission = 'admitted'
                record.dispatched = True
                record.semantic = 'unknown'
            try:
                return await factory()
            except Exception:
                # Even a provider-raised ComputerError is untrusted here.
                raise ComputerError('adapter_failed') from None
        job = self._job = self._track(guarded())
        stopping = asyncio.create_task(record.stop.wait())
        try:
            done, _ = await asyncio.wait((job, stopping), timeout=self.timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if record.stop.is_set():
                raise ComputerError('cancelled')
            if job not in done:
                raise ComputerError('adapter_timeout')
            return job.result()
        finally:
            stopping.cancel()
            await asyncio.gather(stopping, return_exceptions=True)

    async def _maintenance(self, coroutine):
        job = self._track(coroutine)
        done, _ = await asyncio.wait((job,), timeout=self.cleanup_timeout)
        if job not in done:
            job.cancel()
            return False
        try:
            return job.result() is True
        except (Exception, asyncio.CancelledError):
            return False

    async def _abort(self, record):
        # Never assume Task.cancel() confirms termination of adapter effects.
        record.stop.set()
        self._quarantined = True
        record.cancellation = 'requested'
        record.cleanup = 'unconfirmed'
        if record.dispatched and record.outcome == 'not_started':
            record.outcome = 'unknown'
        if self._job and not self._job.done():
            self._job.cancel()
        stopped = await self._maintenance(self.adapter.cancel(record.spec.action_id))
        cleaned = await self._maintenance(self.adapter.cleanup(record.spec.action_id))
        settled = not any(not task.done() for task in self._jobs)
        record.cancellation = 'confirmed' if stopped and settled else 'unconfirmed'
        record.cleanup = 'confirmed' if cleaned else 'unconfirmed'
        self._quarantined = not (stopped and cleaned and settled)

    async def _watch_session(self, consumer, record):
        try:
            while True:
                await consumer.next()
        except StopAsyncIteration:
            self.cancel_action(record.spec.action_id, reason='session_invalidated')
        finally:
            consumer.close()

    async def _dispatch(self, action, args):
        self._keys(args, {'action_id', 'request'})
        record = self._actions.get(args['action_id'])
        if record is None:
            raise ComputerError('unknown_action')
        if record.state in TERMINAL:
            return self.snapshot(record.spec.action_id)
        watcher = None
        entered_adapter = False
        try:
            self._check(record)
            if self._quarantined:
                raise ComputerError('cancellation_unresolved')
            if record.state != ActionState.APPROVED:
                raise ComputerError('approval_required')
            if self._canonical(args['request']) != self._canonical(record.scope):
                raise ComputerError('approval_scope_mismatch')
            digest = hashlib.sha256(self._canonical(record.scope).encode()).hexdigest()
            record.lease = self.authority.issue(record.spec.action_id, self.owner, digest)
            self.authority.begin(record.lease, self.owner, digest,
                                 operation_class='owned_input' if self.native_input else 'receiver_fixture' if self.receiver_adapter else 'owned_window' if self.native_owned else 'external_fixture' if self.native_external else 'simulation')
            if self.native_adapter or self.native_input:
                self.adapter.bind(record.spec, record.lease, record.scope)
            watcher = asyncio.create_task(self._watch_session(self.observations.subscribe(), record))
            self._transition(record, ActionState.REVALIDATING)
            entered_adapter = True
            target = await self._step(lambda: self.adapter.revalidate(record.spec), record)
            self._check(record)  # Expiry, stop and freshness after awaited validation.
            if self._canonical(args['request']) != self._canonical(record.scope):
                raise ComputerError('approval_scope_mismatch')
            if (type(target) is not TargetEvidence or
                    self._canonical(asdict(target)) != self._canonical(asdict(record.spec.target))):
                raise ComputerError('target_drift')
            self._transition(record, ActionState.EXECUTING)
            async def dispatch_or_check():
                if record.spec.desktop is not None and isinstance(record.spec.desktop.action, Done):
                    # A completion claim can only request verification. It must
                    # never reach a mutation adapter, even a simulation double.
                    return ExecutionResult('complete')
                return await self.adapter.dispatch(record.spec, record.stop)
            outcome = await self._step(dispatch_or_check, record)
            if type(outcome) is not ExecutionResult or outcome.outcome not in ('complete', 'failed', 'partial', 'unknown'):
                raise ComputerError('invalid_adapter_result')
            record.outcome = outcome.outcome
            self._check(record, approval=False)
            if outcome.outcome != 'complete':
                raise ComputerError('execution_' + outcome.outcome)
            self._transition(record, ActionState.VERIFYING)
            verified = await self._step(lambda: self.adapter.verify(record.spec, outcome), record)
            self._check(record, approval=False)
            if (type(verified) is not Verification or verified.action_id != record.spec.action_id or
                    verified.window_id != record.spec.target.window_id or
                    verified.control_id != record.spec.target.control_id or
                    verified.verdict not in ('matched', 'failed', 'inconclusive') or
                    (verified.observed_digest is not None and not self._digest(verified.observed_digest))):
                raise ComputerError('invalid_verification')
            record.verification = verified
            if (verified.verdict == 'failed' and verified.observed_digest is not None and
                    verified.observed_digest != record.spec.expected_digest):
                record.semantic = 'verified_failure'
            if verified.verdict != 'matched' or verified.observed_digest != record.spec.expected_digest:
                raise ComputerError('postcondition_unverified')
            record.semantic = 'verified_success'
            cleaned = await self._maintenance(self.adapter.cleanup(record.spec.action_id))
            record.cleanup = 'confirmed' if cleaned else 'unconfirmed'
            if not cleaned:
                self._quarantined = True
                raise ComputerError('cleanup_unconfirmed')
            self._check(record, approval=False)
            self._transition(record, ActionState.SUCCEEDED)
        except asyncio.CancelledError:
            self.cancel_action(record.spec.action_id)
            if entered_adapter:
                await self._abort(record)
            raise
        except Exception as exc:
            reason = exc.code if isinstance(exc, ComputerError) else 'adapter_failed'
            self._reject(record, reason)
            if entered_adapter:
                await self._abort(record)
        finally:
            if watcher:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            if record.lease is not None:
                self.authority.finish(record.lease,
                    settled=not self._jobs and not self._quarantined,
                    cleanup=record.cleanup in ('confirmed', 'not_needed'),
                    outcome=record.outcome, semantic=record.semantic)
        return self.snapshot(record.spec.action_id)

    async def close(self):
        self.emergency_stop()
        self.mode = 'closed'
        # Active dispatch owns bounded cancellation/cleanup. Do not wait forever
        # for an adapter that ignores cancellation, or claim it was terminated.
        return {'ok': not self._jobs and not self._quarantined,
                'status': 'closed', 'outstanding': sum(not job.done() for job in self._jobs)}
