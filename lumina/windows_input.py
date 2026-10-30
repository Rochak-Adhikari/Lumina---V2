"""Shared input facade and P2.1 inert executor. No Windows APIs or fallback.

Fake executors are trusted in-process test dependencies, not a containment
boundary against arbitrary Python. The exact practice adapter has separate
registration; production input admission remains unavailable.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from .computer_action import (DesktopSimulationAdapter, IntendedAction, ExecutionResult,
                              ActionState, SafeError, Ask, Wait, Done)
from .computer_geometry import TargetBinding
from .computer_use_model import normalize
from .computer_windows import ComputerError


@dataclass(frozen=True)
class NativeExecutionRequest:
    action: IntendedAction = field(repr=False)
    binding: TargetBinding = field(repr=False)


@dataclass(frozen=True)
class SubmissionReceipt:
    submission: Literal['rejected', 'not_submitted', 'submitted', 'unknown']
    accepted: int = 0


class FakeInputExecutor(DesktopSimulationAdapter):
    """Offline dependencies only. No production executor implementation exists."""
    available = True

    def check_ready(self):
        """Synchronous fake health check; never grants native authority."""

    @abstractmethod
    async def submit(self, request: NativeExecutionRequest, cancelled) -> SubmissionReceipt: ...

    async def dispatch(self, action, cancelled):
        raise PermissionError('facade_required')


class _InputFacade:
    """Shared controller checks; subclasses have explicit exact-type admission."""
    operation = 'simulate_desktop'
    def __init__(self, executor=None):
        if executor is not None and not isinstance(executor, FakeInputExecutor):
            raise TypeError('fake_executor_required')
        self._executor = executor
        self._controller = None
        self._receipts = {}

    def attach(self, controller):
        if self._controller is not None or controller.adapter is not self:
            raise TypeError('facade_already_bound')
        self._controller = controller

    def preflight(self):
        if self._executor is None or self._executor.available is not True:
            raise ComputerError('executor_unavailable')
        self._executor.check_ready()

    def grounding_snapshot(self, observation):
        self.preflight()
        return self._executor.grounding_snapshot(observation)

    async def revalidate(self, action):
        self.preflight()
        return await self._executor.revalidate(action)

    def receipt(self, action_id):
        # Absent means this facade never entered the executor for that ID.
        return self._receipts.get(action_id, SubmissionReceipt('rejected'))

    async def dispatch(self, action, cancelled):
        core = self._controller
        record = core._actions.get(action.action_id) if core and type(action) is IntendedAction else None
        try:
            self.preflight()
            if (record is None or record.spec is not action or record.stop is not cancelled or
                    record.state != ActionState.EXECUTING or not record.dispatched or
                    record.admission != 'admitted' or action.action_id in self._receipts or
                    action.operation != self.operation or action.desktop is None or
                    isinstance(action.desktop.action, (Ask, Wait, Done))):
                raise ComputerError('facade_admission_required')
            core._check(record)
            if isinstance(normalize(action.desktop, record.binding.inference.reference), SafeError):
                raise ComputerError('invalid_desktop_proposal')
            core.authority.validate(record.lease)
        except (ComputerError, PermissionError, AttributeError, TypeError):
            return ExecutionResult('failed')
        # Last synchronous check; no await before entering the executor.
        # This does not promise atomic focus/OS effects. The authority already
        # recorded logical admission; an admitted call can outlive Stop.
        if cancelled.is_set() or core.authority.stop_requested.is_set():
            return ExecutionResult('failed')
        self._receipts[action.action_id] = SubmissionReceipt('unknown')
        receipt = await self._executor.submit(NativeExecutionRequest(action, record.binding), cancelled)
        if cancelled.is_set() or core.authority.stop_requested.is_set():
            return ExecutionResult('unknown')
        if (type(receipt) is not SubmissionReceipt or type(receipt.accepted) is not int or
                receipt.accepted < 0 or receipt.submission not in ('not_submitted', 'submitted', 'unknown') or
                receipt.submission == 'not_submitted' and receipt.accepted != 0 or
                receipt.submission == 'submitted' and receipt.accepted == 0):
            return ExecutionResult('unknown')
        self._receipts[action.action_id] = receipt
        return ExecutionResult('complete' if receipt.submission == 'submitted' else
                               'failed' if receipt.submission == 'not_submitted' else 'unknown')

    async def verify(self, action, outcome):
        return await self._executor.verify(action, outcome)

    async def cancel(self, action_id):
        if self._executor is None: return True
        return await self._executor.cancel(action_id)

    async def cleanup(self, action_id):
        if self._executor is None: return True
        return await self._executor.cleanup(action_id)


class WindowsInputAdapter(_InputFacade, DesktopSimulationAdapter):
    """Explicit fake-only facade; never wraps a native executor."""


@dataclass(frozen=True)
class InputEvent:
    """Pure synthetic event, not a Win32 structure or executable payload."""
    kind: str
    value: object = field(repr=False)


def input_plan(request):
    """Compile an already bound proposal to one finite in-memory batch."""
    from .computer_action import Move, Click, Scroll, Key, Text, Chord, Focus
    from .computer_geometry import to_physical
    if type(request) is not NativeExecutionRequest:
        raise ComputerError('invalid_input_request')
    proposal = normalize(request.action.desktop, request.binding.inference.reference)
    if isinstance(proposal, SafeError): raise ComputerError(proposal.code)
    a = proposal.action
    events = []
    if type(a) in (Move, Click, Scroll):
        point = to_physical(a.point, request.binding.current.desktop, request.binding.current.frame_size)
        if isinstance(point, SafeError): raise ComputerError(point.code)
        events.append(InputEvent('move', point))
        if type(a) is Click:
            for _ in range(a.count):
                events.extend((InputEvent('down', ('button', a.button)), InputEvent('up', ('button', a.button))))
        elif type(a) is Scroll: events.append(InputEvent('scroll', (a.axis, a.amount)))
    elif type(a) in (Key, Chord, Text):
        if type(a) is Text:
            raw = a.text.encode('utf-16-le')
            units = [int.from_bytes(raw[i:i+2], 'little') for i in range(0, len(raw), 2)]
            for unit in units:
                events.extend((InputEvent('down', ('unicode', unit)), InputEvent('up', ('unicode', unit))))
        else:
            keys = (a.key,) if type(a) is Key else a.keys
            # Inert fixture scope excludes shortcuts that can escape its surface.
            if 'Alt' in keys or set(keys) == {'Control', 'Escape'}:
                raise ComputerError('unsupported_fixture_shortcut')
            events.extend(InputEvent('down', ('key', key)) for key in keys)
            events.extend(InputEvent('up', ('key', key)) for key in reversed(keys))
    elif type(a) is Focus and a.window == request.action.target.window_id:
        events.append(InputEvent('focus', a.window))
    else:
        raise ComputerError('unsupported_input_action')
    return tuple(events)


class BoundedFakeInputExecutor(FakeInputExecutor):
    """Inert batch/cleanup contract only. Must never wrap an OS executor.

    Subclasses supply in-memory send/readback. Existing controller owns all
    deadlines, approval, revocation and quarantine. No second authority exists.
    """
    def __init__(self):
        self._input_active = False
        self._input_owner = None
        self._held = set()
        self._touched = ()
        self._attempted = self._accepted = 0

    @abstractmethod
    def modifiers_clear(self): ...

    @abstractmethod
    async def send_batch(self, events, cancelled):
        """Return exact accepted prefix length; exception means unknown prefix."""

    @abstractmethod
    async def release_batch(self, events): ...

    @abstractmethod
    async def released(self, tokens):
        """Independent synthetic readback, not release acknowledgement."""

    def check_ready(self):
        if self._input_active or self._held:
            raise ComputerError('input_cleanup_unresolved')
        if self.modifiers_clear() is not True:
            raise ComputerError('physical_modifier_conflict')

    def input_status(self):
        return dict(active=self._input_active, potentially_held=len(self._held),
                    attempted=self._attempted, accepted=self._accepted)

    async def submit(self, request, cancelled):
        self.check_ready()
        events = input_plan(request)
        if cancelled.is_set(): return SubmissionReceipt('not_submitted')
        self._input_owner = request.action.action_id
        self._attempted, self._accepted = len(events), 0
        self._input_active = True
        # Any down may have happened if send throws or its result is lost.
        self._held = {e.value for e in events if e.kind == 'down'}
        self._touched = tuple(dict.fromkeys(e.value for e in events if e.kind == 'down'))
        try:
            count = await self.send_batch(events, cancelled)
            if type(count) is not int or not 0 <= count <= len(events):
                return SubmissionReceipt('unknown')
            self._accepted = count
            held = set()
            for e in events[:count]:
                if e.kind == 'down': held.add(e.value)
                elif e.kind == 'up': held.discard(e.value)
            self._held = held
            return SubmissionReceipt('not_submitted' if count == 0 else
                'submitted' if count == len(events) else 'unknown', count)
        finally:
            self._input_active = False

    async def cancel(self, action_id):
        # Awaiter cancellation is owned by the controller; no termination claim.
        return not self._input_active

    async def cleanup(self, action_id):
        if self._input_active: return False
        if self._input_owner is None: return True
        if action_id != self._input_owner: return False
        tokens = frozenset(self._held)
        if tokens:
            await self.release_batch(tuple(InputEvent('up', t) for t in reversed(self._touched) if t in tokens))
        # Even a full accepted batch requires independent release evidence.
        if await self.released(self._touched) is not True: return False
        self._held.clear()
        self._touched = ()
        self._input_owner = None
        return True
