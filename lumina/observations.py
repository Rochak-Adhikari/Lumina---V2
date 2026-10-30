"""Connection-local perception. No capture, provider, persistence or action APIs.

Only trusted in-process consumers given this stream by its connection owner may
subscribe. Handles retain metadata, not pixels: replacement/stop revokes image
access even through an old handle. Copied bytes cannot be revoked by Python.
All methods run on the owning asyncio loop; this is not a cross-thread API.
"""
import asyncio
from dataclasses import dataclass, field
import math
import time
import threading
from typing import Literal
import weakref


@dataclass(frozen=True)
class DesktopTransform:
    """Processed pixel edges map to physical desktop: origin + pixel * scale."""
    left: int
    top: int
    width: int
    height: int
    scale_x: float
    scale_y: float
    coordinate_space: str = 'physical_virtual_desktop'


@dataclass(frozen=True)
class Observation:
    session_id: str
    source_id: str
    source_type: str
    sequence: int
    captured_at: str | None
    received_at: str
    received_monotonic: float
    capture_not_before_monotonic: float | None
    timing_basis: Literal['browser_ticket', 'native_request', 'unknown']
    original_dimensions: tuple[int, int]
    processed_dimensions: tuple[int, int]
    desktop: DesktopTransform | None
    _stream: weakref.ReferenceType = field(repr=False, compare=False)
    _revoked: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)
    capture_method: str = 'unknown'

    @property
    def availability(self):
        stream = self._stream()
        return stream.availability(self) if stream else 'invalidated'

    @property
    def image(self):
        """Memory-only JPEG; None once superseded, stopped or invalidated."""
        stream = self._stream()
        return stream._image if stream and stream.current is self else None


@dataclass(frozen=True)
class ObservationEvidence:
    """Metadata only, never pixels or action permission. Thread-safe revocation.

    Normal replacement revokes image access, not a recent observed fact. Its
    original deadline is never extended; target state still needs revalidation.
    """
    session_id: str
    source_id: str
    source_type: str
    sequence: int
    origin: float
    expires: float
    revoked: threading.Event = field(repr=False, compare=False)

    def valid(self, now):
        return not self.revoked.is_set() and self.origin <= now < self.expires


class ObservationStream:
    def __init__(self, *, clock=time.monotonic, freshness_seconds=3.0):
        if not math.isfinite(freshness_seconds) or freshness_seconds <= 0:
            raise ValueError('freshness_seconds must be positive and finite')
        self.clock = clock
        self.freshness_seconds = freshness_seconds
        self.session_id = None
        self._session_token = object()
        self._evidence_revoked = threading.Event()
        self.current = None
        self._image = None
        self._changed = asyncio.Event()
        self.capture_state = 'stopped'
        self.analysis_state = 'disabled'
        self.error = None

    def _notify(self):
        self._changed.set()
        self._changed = asyncio.Event()

    def start(self, session_id, *, analysis=False):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('A nonempty sharing session identity is required')
        self.stop()
        self.session_id = session_id
        self.capture_state = 'waiting'
        self.analysis_state = 'connecting' if analysis else 'disabled'
        self.error = None

    def stop(self):
        self._invalidate_evidence()
        if self.current is not None:
            self.current._revoked.set()
        self._session_token = object()
        self.session_id = None
        self.current = self._image = None
        self.capture_state = 'stopped'
        self.analysis_state = 'disabled'
        self.error = None
        self._notify()

    def fail(self, stage):
        self._invalidate_evidence()
        # Callers provide fixed stage codes, never raw exception text.
        self.capture_state = 'failed'
        self.error = 'capture_failed' if stage == 'capture' else 'processing_failed'
        self._notify()

    def _invalidate_evidence(self):
        self._evidence_revoked.set()
        self._evidence_revoked = threading.Event()

    def pause(self):
        self._invalidate_evidence()
        self.capture_state = 'paused'
        self._notify()

    def evidence(self, *, session_id, minimum_sequence):
        current = self.latest()
        if (current is None or current.session_id != session_id or
                current.sequence < minimum_sequence):
            raise ValueError('fresh_shared_observation_required')
        origin = current.capture_not_before_monotonic
        return ObservationEvidence(current.session_id, current.source_id, current.source_type,
            current.sequence, origin, origin + self.freshness_seconds, self._evidence_revoked)

    def publish(self, image, **metadata):
        if self.session_id is None or metadata['session_id'] != self.session_id:
            raise ValueError('inactive observation session')
        sequence = metadata['sequence']
        if (type(sequence) is not int or sequence <= 0 or
                (self.current is not None and sequence <= self.current.sequence)):
            raise ValueError('invalid or expired observation sequence')
        observation = Observation(**metadata, _stream=weakref.ref(self))
        if self.current is not None:
            if (observation.source_id, observation.source_type) != (self.current.source_id, self.current.source_type):
                self._invalidate_evidence()
            self.current._revoked.set()
        self.current, self._image = observation, image
        self.capture_state, self.error = 'active', None
        self._notify()
        return observation

    def availability(self, observation=None):
        observation = observation or self.current
        if not self.session_id:
            return 'stopped' if observation is None else 'invalidated'
        if observation is None:
            return self.capture_state
        if observation is not self.current or observation.session_id != self.session_id:
            return 'invalidated'
        if self.capture_state in {'failed', 'paused'}:
            return self.capture_state
        origin = observation.capture_not_before_monotonic
        if origin is None:
            return 'unverified'
        age = self.clock() - origin
        return 'fresh' if 0 <= age < self.freshness_seconds else 'stale'

    def latest(self, *, require_fresh=True):
        if require_fresh and self.availability() != 'fresh':
            return None
        return self.current

    def status(self):
        current = self.current
        origin = current.capture_not_before_monotonic if current else None
        return {'capture': self.capture_state, 'observation': self.availability(),
                'analysis': self.analysis_state, 'error': self.error,
                'sequence': self.current.sequence if self.current else 0,
                'capture_method': self.current.capture_method if self.current else 'unknown',
                'freshness_seconds': self.freshness_seconds,
                'session_id': self.session_id,
                'captured_at': current.captured_at if current else None,
                'received_at': current.received_at if current else None,
                'capture_not_before_monotonic': origin,
                'received_monotonic': current.received_monotonic if current else None,
                'age_seconds': max(0, self.clock() - origin) if origin is not None else None,
                'dimensions': current.processed_dimensions if current else None}

    def subscribe(self):
        """No consent acquisition or capture side effects; active session only."""
        if self.session_id is None:
            raise ValueError('No authorized sharing session')
        return ObservationConsumer(self, self.session_id)


class ObservationConsumer:
    """Latest-only delivery; slow readers skip frames, never accumulate a queue."""
    def __init__(self, stream, session_id):
        self._stream, self.session_id = stream, session_id
        self._session_token = stream._session_token
        self._sequence = 0
        self._closed = self._waiting = False

    def close(self):
        self._closed = True
        self._stream._notify()

    async def next(self):
        if self._waiting:
            raise RuntimeError('Only one pending read per consumer')
        self._waiting = True
        try:
            while (not self._closed and self._stream.session_id == self.session_id and
                   self._stream._session_token is self._session_token):
                changed = self._stream._changed
                observation = self._stream.latest(require_fresh=False)
                if observation and observation.sequence > self._sequence:
                    self._sequence = observation.sequence
                    return observation
                await changed.wait()
            raise StopAsyncIteration
        finally:
            self._waiting = False
