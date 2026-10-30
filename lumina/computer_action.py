"""Typed action contracts; adapter admission and authority remain controller-owned."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class ActionState(str, Enum):
    PROPOSED = 'proposed'
    AWAITING_APPROVAL = 'awaiting_approval'
    APPROVED = 'approved'
    REVALIDATING = 'revalidating'
    EXECUTING = 'executing'
    VERIFYING = 'verifying'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    EXPIRED = 'expired'


TERMINAL = frozenset({ActionState.SUCCEEDED, ActionState.FAILED,
                      ActionState.CANCELLED, ActionState.EXPIRED})


@dataclass(frozen=True)
class TargetEvidence:
    """Opaque structured identities/digests, never UI instructions or coordinates."""
    window_id: str
    control_id: str
    revision: str
    input_epoch: int
    foreground: bool = True
    enabled: bool = True
    password: bool = False
    patterns: tuple[str, ...] = ('invoke',)


@dataclass(frozen=True)
class ObservationRef:
    """Original inference frame only; no physical-coordinate authority."""
    session_id: str
    source_id: str
    sequence: int


@dataclass(frozen=True)
class Move:
    point: tuple[float, float]
    kind: str = field(default='move', init=False)


@dataclass(frozen=True)
class Click:
    point: tuple[float, float]
    button: Literal['left', 'right', 'middle']
    count: int
    kind: str = field(default='click', init=False)


@dataclass(frozen=True)
class Scroll:
    point: tuple[float, float]
    axis: Literal['vertical', 'horizontal']
    amount: int
    kind: str = field(default='scroll', init=False)


@dataclass(frozen=True)
class Drag:
    start: tuple[float, float]
    end: tuple[float, float]
    duration: float
    kind: str = field(default='drag', init=False)


@dataclass(frozen=True)
class Key:
    key: str
    kind: str = field(default='key', init=False)


@dataclass(frozen=True)
class Text:
    text: str = field(repr=False)
    kind: str = field(default='text', init=False)


@dataclass(frozen=True)
class Chord:
    keys: tuple[str, ...]
    kind: str = field(default='chord', init=False)


@dataclass(frozen=True)
class Focus:
    window: str
    kind: str = field(default='focus', init=False)


@dataclass(frozen=True)
class Wait:
    condition: str
    kind: str = field(default='wait', init=False)


@dataclass(frozen=True)
class Ask:
    question: str = field(repr=False)
    kind: str = field(default='ask', init=False)


@dataclass(frozen=True)
class Done:
    predicate: str
    kind: str = field(default='done', init=False)


DesktopAction = Move | Click | Scroll | Drag | Key | Text | Chord | Focus | Wait | Ask | Done


@dataclass(frozen=True)
class DesktopProposal:
    observation: ObservationRef
    action: DesktopAction


@dataclass(frozen=True)
class SafeError:
    code: str
    may_have_effect: bool = False
    retry_read_only: bool = False


@dataclass(frozen=True)
class IntendedAction:
    action_id: str
    session_id: str
    observation_sequence: int
    operation: Literal['invoke', 'type', 'set_owned_text', 'clear_owned_text', 'select_owned_text', 'set_external_fixture', 'increment_external_fixture', 'reset_external_fixture', 'toggle_external_fixture', 'set_fixture_ready', 'simulate_desktop', 'owned_input']
    target: TargetEvidence
    risk: Literal['consequential', 'sensitive', 'reversible_local']
    approval_policy: Literal['exact_operation', 'owned_surface_only', 'registered_fixture_only']
    expires_at: float
    expected_digest: str
    text: str | None = field(default=None, repr=False)
    desktop: DesktopProposal | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ExecutionResult:
    outcome: Literal['complete', 'failed', 'partial', 'unknown']


@dataclass(frozen=True)
class Verification:
    action_id: str
    window_id: str
    control_id: str
    observed_digest: str | None
    verdict: Literal['matched', 'failed', 'inconclusive']


class ActionAdapter(ABC):
    """Shared lifecycle contract, with explicit controller-side adapter admission.

    This ABC grants no execution authority. SimulationAdapter remains fake-only;
    real adapter admission is limited to exact Runtime-registered adapter types.
    """
    @abstractmethod
    async def revalidate(self, action: IntendedAction) -> TargetEvidence: ...

    @abstractmethod
    async def dispatch(self, action: IntendedAction, cancelled) -> ExecutionResult: ...

    @abstractmethod
    async def verify(self, action: IntendedAction, outcome: ExecutionResult) -> Verification: ...

    @abstractmethod
    async def cancel(self, action_id: str) -> bool:
        """True only when the adapter can confirm its operation stopped."""

    @abstractmethod
    async def cleanup(self, action_id: str) -> bool:
        """Bounded resource cleanup; True confirms completion."""


class SimulationAdapter(ActionAdapter):
    """Explicit fake dependency; never a base class for native adapters."""


class DesktopSimulationAdapter(SimulationAdapter):
    """Trusted offline test double opt-in; no live adapter may inherit this.

    dispatch handles typed proposals in memory only. Ask/Wait are not dispatched;
    Done performs no mutation and still requires independent verify readback.
    """

    def grounding_snapshot(self, observation):
        """Trusted fake metadata only; missing full identity/geometry fails closed.

        Future native evidence acquisition requires its separate adapter gate.
        No UIA/native fallback is available through this interface.
        """
        return None
