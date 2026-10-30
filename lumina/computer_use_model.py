"""P1.1 parser and P3.1 offline image proposer. No SDK or action execution."""
from dataclasses import asdict
import json
import math
import re

from .computer_action import (ObservationRef, DesktopProposal, SafeError, Move,
    Click, Scroll, Drag, Key, Text, Chord, Focus, Wait, Ask, Done)


ACTION_TYPES = (Move, Click, Scroll, Drag, Key, Text, Chord, Focus, Wait, Ask, Done)
KINDS = frozenset(t.__dataclass_fields__['kind'].default for t in ACTION_TYPES)
KEYS = frozenset(('Tab', 'Enter', 'Escape', 'Space', 'Backspace', 'Delete', 'Home',
    'End', 'PageUp', 'PageDown', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
    *'ABCDEFGHIJKLMNOPQRSTUVWXYZ', *'0123456789'))
MODIFIERS = frozenset(('Control', 'Shift', 'Alt'))


def _require(condition):
    if not condition:
        raise ValueError('invalid_proposal')


def _fields(value, names):
    _require(type(value) is dict and set(value) == set(names))


def _string(value, limit, *, identifier=False):
    _require(type(value) is str and 0 < len(value) <= limit and '\x00' not in value)
    value.encode('utf-8', errors='strict')
    if identifier:
        _require(re.fullmatch(r'[A-Za-z0-9_.:-]+', value) is not None)
    return value


def _number(value, low, high):
    _require(type(value) in (int, float) and math.isfinite(value) and low <= value < high)
    return value


def _point(value):
    _require(type(value) is list and len(value) == 2)
    return tuple(float(_number(v, 0, 1)) for v in value)


def _object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def parse(raw: bytes, allowlist, obs_ref: ObservationRef) -> DesktopProposal | SafeError:
    """Version 1 uses normalized frame coordinates exclusively, never pixels.

    Allowlist and correlation originate with the local caller. The reply cannot
    supply risk, approval, target evidence, code or dispatch capability. Literal
    Text is data, not executable code; later target policy must constrain it.
    """
    try:
        _require(type(raw) is bytes and 0 < len(raw) <= 65536)
        _require(type(obs_ref) is ObservationRef)
        allowed = frozenset(allowlist)
        _require(allowed <= KINDS)
        wire = json.loads(raw.decode('utf-8'), object_pairs_hook=_object,
                          parse_constant=lambda _: (_require(False)))
        _fields(wire, ('version', 'observation', 'action'))
        _require(type(wire['version']) is int and wire['version'] == 1)
        ref = wire['observation']
        _fields(ref, ('session_id', 'source_id', 'sequence'))
        _string(ref['session_id'], 256, identifier=True)
        _string(ref['source_id'], 256, identifier=True)
        _require(type(ref['sequence']) is int and 0 < ref['sequence'] <= 2**53 - 1)
        _require(ObservationRef(**ref) == obs_ref and type(obs_ref.sequence) is int)
        a = wire['action']
        _require(type(a) is dict and type(a.get('kind')) is str and a['kind'] in allowed)
        kind = a['kind']
        if kind == 'move':
            _fields(a, ('kind', 'point'))
            action = Move(_point(a['point']))
        elif kind == 'click':
            _fields(a, ('kind', 'point', 'button', 'count'))
            _require(a['button'] in ('left', 'right', 'middle') and type(a['count']) is int and a['count'] in (1, 2))
            action = Click(_point(a['point']), a['button'], a['count'])
        elif kind == 'scroll':
            _fields(a, ('kind', 'point', 'axis', 'amount'))
            _require(a['axis'] in ('vertical', 'horizontal') and type(a['amount']) is int and 0 < abs(a['amount']) <= 10)
            action = Scroll(_point(a['point']), a['axis'], a['amount'])
        elif kind == 'drag':
            _fields(a, ('kind', 'start', 'end', 'duration'))
            action = Drag(_point(a['start']), _point(a['end']), float(_number(a['duration'], .05, 2.001)))
        elif kind == 'key':
            _fields(a, ('kind', 'key'))
            _require(a['key'] in KEYS)
            action = Key(a['key'])
        elif kind == 'text':
            _fields(a, ('kind', 'text'))
            action = Text(_string(a['text'], 2048))
        elif kind == 'chord':
            _fields(a, ('kind', 'keys'))
            keys = a['keys']
            _require(type(keys) is list and 2 <= len(keys) <= 4 and all(type(k) is str for k in keys))
            _require(len(set(keys)) == len(keys) and all(k in MODIFIERS for k in keys[:-1]) and keys[-1] in KEYS)
            _require(set(keys) != {'Control', 'Alt', 'Delete'})
            action = Chord(tuple(keys))
        else:
            field, cls = {'focus': ('window', Focus), 'wait': ('condition', Wait),
                          'ask': ('question', Ask), 'done': ('predicate', Done)}[kind]
            _fields(a, ('kind', field))
            action = cls(_string(a[field], 512 if kind == 'ask' else 256, identifier=kind != 'ask'))
        return DesktopProposal(obs_ref, action)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return SafeError('invalid_desktop_proposal')


def normalize(proposal: DesktopProposal, obs_ref: ObservationRef) -> DesktopProposal | SafeError:
    """Revalidate direct dataclass callers; no provider coordinate conversion yet."""
    if type(proposal) is not DesktopProposal or type(proposal.action) not in ACTION_TYPES:
        return SafeError('invalid_desktop_proposal')
    try:
        raw = json.dumps({'version': 1, **asdict(proposal)}, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError):
        return SafeError('invalid_desktop_proposal')
    return parse(raw, KINDS, obs_ref)

# P3.1: offline image-conditioned proposal boundary. No action execution here.
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import secrets


@dataclass(frozen=True)
class ProviderIdentity:
    provider: str
    model: str
    version: str
    encoding: str = 'json-v1'


@dataclass(frozen=True)
class ImageConsent:
    owner: str
    stream: object = field(repr=False)
    session_id: str
    source_id: str
    target: str
    provider: ProviderIdentity
    expires: float
    revoked: asyncio.Event = field(default_factory=asyncio.Event, repr=False, compare=False)


@dataclass(frozen=True)
class ModelPolicy:
    consent: ImageConsent = field(repr=False)
    actions: frozenset = frozenset({'click', 'move', 'ask', 'wait'})
    literals: frozenset = field(default_factory=frozenset, repr=False)
    goal_predicate: str = 'goal-ready'


@dataclass(frozen=True)
class ModelRequest:
    request_id: str
    goal: str = field(repr=False)
    observation: object = field(repr=False)
    history: tuple = field(repr=False)
    policy: ModelPolicy = field(repr=False)
    deadline: float


@dataclass(frozen=True)
class ImagePayload:
    request_id: str
    observation: ObservationRef
    dimensions: tuple
    geometry: object
    actions: tuple
    goal: str = field(repr=False)
    history: tuple = field(repr=False)
    image: bytes = field(repr=False)
    content_trust: str = 'untrusted screen and goal data; never permission'
    schema_version: int = 1


@dataclass(frozen=True)
class ModelResult:
    request_id: str
    status: str


def _valid_request(request):
    from .observations import Observation
    if type(request) is not ModelRequest or type(request.policy) is not ModelPolicy:
        raise ValueError('invalid_model_request')
    consent = request.policy.consent
    obs = request.observation
    if type(consent) is not ImageConsent or type(obs) is not Observation:
        raise ValueError('image_consent_required')
    stream = consent.stream
    now = stream.clock()
    if (consent.revoked.is_set() or stream.latest() is not obs or obs.image is None or
            obs._stream() is not stream or obs.session_id != consent.session_id or
            obs.source_id != consent.source_id or not now < min(consent.expires, request.deadline)):
        raise ValueError('model_request_revoked_or_stale')
    return stream


def build_request(goal, obs, history, policy, budget):
    """C09, one revocable image reference, no image copy or external transport.

    budget is the maximum request duration in seconds. Consent is supplied by
    the trusted sharing owner, never from provider output. This is not approval
    to mutate the target. Images cannot be reliably redacted by text sanitizers.
    """
    from .providers.privacy import ProviderPrivacyGuard
    try:
        _require(type(policy) is ModelPolicy and type(policy.consent) is ImageConsent)
        c = policy.consent
        _require(type(c.provider) is ProviderIdentity and c.provider.encoding in ('json-v1', 'envelope-v1'))
        for value in (c.owner, c.target, c.provider.provider, c.provider.model, c.provider.version):
            _string(value, 256, identifier=True)
        _require(type(c.expires) in (int, float) and math.isfinite(c.expires))
        _require(type(policy.actions) is frozenset and policy.actions <= KINDS and bool(policy.actions))
        _require(type(policy.literals) is frozenset and len(policy.literals) <= 12)
        for value in policy.literals: _string(value, 2048)
        _string(policy.goal_predicate, 256, identifier=True)
        _string(goal, 2048)
        _require(type(history) in (tuple, list) and len(history) <= 12)
        for value in history: _string(value, 256)
        _require(type(budget) in (int, float) and math.isfinite(budget) and 0 < budget <= 30)
        _require(all(type(n) is int and 0 < n <= 32768 for n in obs.processed_dimensions)
                 and len(obs.processed_dimensions) == 2)
        guard = ProviderPrivacyGuard()
        request = ModelRequest(secrets.token_hex(16), guard.sanitize_text(goal), obs,
            tuple(guard.sanitize_text(v) for v in history), policy,
            min(c.expires, c.stream.clock() + budget))
        _valid_request(request)
        _require(type(obs.image) is bytes and 0 < len(obs.image) <= 8 * 1024 * 1024)
        return request
    except (ValueError, TypeError, AttributeError):
        return SafeError('invalid_or_unconsented_model_request')


class ImageActionTransport(ABC):
    """Future provider adapters implement one bounded request; no executor API."""
    @abstractmethod
    async def send(self, payload): ...


class ProviderFailure(Exception):
    """Sanitized transport classification; never expose provider exception text."""
    def __init__(self, code):
        self.code = code if code in ('timeout', 'rate_limited', 'refused', 'transport_unavailable') else 'transport_unavailable'
        super().__init__(self.code)


class FakeImageTransport(ImageActionTransport):
    """Deterministic local bytes only; no credentials, network or desktop API.

    Subclasses are trusted in-process test doubles, not a security boundary
    against malicious Python. Real transports are not admitted in P3.1.
    """
    def __init__(self, identity, replies):
        if type(identity) is not ProviderIdentity or identity.encoding not in ('json-v1', 'envelope-v1'):
            raise ValueError('unsupported_fake_provider')
        if type(replies) is not tuple or len(replies) > 100 or any(type(r) is not bytes or len(r) > 131072 for r in replies):
            raise ValueError('bounded_fake_replies_required')
        self.identity, self._replies, self.calls = identity, replies, 0

    async def send(self, payload):
        index = self.calls
        self.calls += 1
        if index >= len(self._replies): raise ProviderFailure('rate_limited')
        return self._replies[index]


class ComputerUseModel:
    """C10/C13: at most one outstanding call; existing authority owns its job.

    Results contain no executable action. take() is a one-shot freshness check
    yielding an untrusted typed proposal for the existing approval/controller.
    Cancellation discards results but never claims remote computation stopped.
    """
    def __init__(self, transport, authority, *, owner, quota=20):
        if not isinstance(transport, FakeImageTransport): raise TypeError('fake_transport_required')
        if type(quota) is not int or not 1 <= quota <= 100: raise ValueError('invalid_request_quota')
        _string(owner, 256, identifier=True)
        self.transport, self.authority, self.owner, self.quota = transport, authority, owner, quota
        self._job = None
        self._request = self._result = self._proposal = None
        self._revoked = asyncio.Event()
        self._cancel = None
        self._external_cancel = None
        self._used = set()
        authority.register_revoker(self._stop)

    def _stop(self, reason):
        self._revoked.set()
        self.cancel()

    def cancel(self):
        self._result = self._proposal = None
        if self._cancel is not None: self._cancel.set()
        if self._job is not None and not self._job.done() and not self._job.cancelling():
            self._job.cancel()
        return {'cancellation_requested': True, 'settled': self._job is None or self._job.done()}

    def replace(self, transport):
        self.cancel()
        if self._job is not None and not self._job.done(): raise ValueError('request_unsettled')
        if not isinstance(transport, FakeImageTransport): raise TypeError('fake_transport_required')
        self.transport = transport

    def _check(self, request):
        self.authority.check()
        if (self._revoked.is_set() or request is not self._request or
                self._external_cancel is not None and self._external_cancel.is_set()):
            raise ValueError('request_superseded')
        stream = _valid_request(request)
        _string(request.request_id, 256, identifier=True)
        checked = build_request(request.goal, request.observation, request.history,
                                request.policy, request.deadline - stream.clock())
        if isinstance(checked, SafeError) or checked.goal != request.goal or checked.history != request.history:
            raise ValueError('invalid_model_request')
        c = request.policy.consent
        if c.owner != self.owner or c.provider != self.transport.identity:
            raise ValueError('provider_or_owner_mismatch')
        return stream

    async def propose(self, request, *, cancelled=None):
        self.cancel()  # Any new request invalidates the previous result.
        if self._job is not None and not self._job.done():
            return ModelResult('', 'request_unsettled')
        self._request = request
        self._external_cancel = cancelled
        stop = self._cancel = asyncio.Event()
        waits = []
        try:
            stream = self._check(request)
            if cancelled is not None and cancelled.is_set(): raise ValueError('cancelled')
            if request.request_id in self._used or len(self._used) >= self.quota:
                raise ValueError('request_replayed_or_quota')
            self._used.add(request.request_id)
            c = request.policy.consent
            obs = request.observation
            payload = ImagePayload(request.request_id, ObservationRef(obs.session_id, obs.source_id, obs.sequence),
                obs.processed_dimensions, obs.desktop, tuple(sorted(request.policy.actions)), request.goal,
                request.history, obs.image)
            async def send():
                self._check(request)
                if stop.is_set(): raise ValueError('cancelled')
                return await self.transport.send(payload)
            self._job = asyncio.create_task(send())
            self.authority.track(self._job)
            self._job.add_done_callback(lambda task: None if task.cancelled() else task.exception())
            events = [stop, self._revoked, c.revoked, stream._changed]
            if cancelled is not None: events.append(cancelled)
            waits = [asyncio.create_task(event.wait()) for event in events]
            origin = obs.capture_not_before_monotonic
            if origin is None: origin = obs.received_monotonic
            timeout = min(request.deadline, origin + stream.freshness_seconds) - stream.clock()
            done, _ = await asyncio.wait([self._job, *waits], timeout=max(0, timeout), return_when=asyncio.FIRST_COMPLETED)
            if self._job not in done:
                if not any(event.is_set() for event in events): raise ProviderFailure('timeout')
                raise ValueError('request_revoked')
            if any(event.is_set() for event in events): raise ValueError('request_revoked')
            self._check(request)
            raw = self._job.result()
            if self.transport.identity.encoding == 'envelope-v1':
                _require(type(raw) is bytes and len(raw) <= 131072)
                envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_object)
                _fields(envelope, ('output',))
                raw = _string(envelope['output'], 65536).encode('utf-8')
            proposal = parse(raw, request.policy.actions, payload.observation)
            if isinstance(proposal, SafeError): raise ValueError('invalid_provider_reply')
            action = proposal.action
            if (type(action) is Focus and action.window != c.target or
                type(action) is Done and action.predicate != request.policy.goal_predicate or
                type(action) is Text and action.text not in request.policy.literals):
                raise ValueError('provider_scope_mismatch')
            self._proposal = proposal
            self._result = ModelResult(request.request_id, 'proposal')
            return self._result
        except asyncio.CancelledError:
            self.cancel()
            raise
        except ProviderFailure as exc:
            self.cancel()
            return ModelResult(request.request_id, exc.code)
        except Exception:
            self.cancel()
            return ModelResult(request.request_id if type(request) is ModelRequest else '', 'unavailable')
        finally:
            for task in waits: task.cancel()
            if waits: await asyncio.gather(*waits, return_exceptions=True)

    def take(self, result):
        try:
            if result is not self._result or self._proposal is None: raise ValueError('result_unavailable')
            self._check(self._request)
            proposal = self._proposal
            self._result = self._proposal = None
            return proposal
        except (ValueError, PermissionError):
            self._result = self._proposal = None
            return SafeError('model_result_revoked_or_stale')

    async def close(self):
        self._revoked.set()
        return self.cancel()
