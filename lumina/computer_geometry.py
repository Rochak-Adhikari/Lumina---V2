"""Pure P1.2 evidence/geometry checks; no capture, UIA, input or OS imports.

Snapshots must come from the trusted capture/inspection owner. These types do
not turn model/window text into evidence or establish native acquisition truth.
"""
from dataclasses import asdict, dataclass, field, replace
import hashlib
import math

from .computer_action import (ObservationRef, TargetEvidence, SafeError, Move,
                              Click, Scroll, Drag)
from .observations import DesktopTransform, Observation


@dataclass(frozen=True)
class WindowIdentity:
    hwnd: int
    pid: int
    creation_id: str
    class_name: str
    window_generation: str
    desktop_id: str


@dataclass(frozen=True)
class TargetSnapshot:
    evidence: TargetEvidence
    identity: WindowIdentity
    observation: ObservationRef
    bounds: tuple[int, int, int, int]  # left, top, width, height; exclusive edges
    virtual_bounds: tuple[int, int, int, int]
    geometry_revision: str
    display_revision: str
    monitor_id: str
    dpi: tuple[float, float]
    rotation: int = 0
    alive: bool = True
    visible: bool = True


@dataclass(frozen=True)
class ValidatedObservation:
    reference: ObservationRef
    source_type: str
    origin: float
    received: float
    expires: float
    original_dimensions: tuple[int, int]
    frame_size: tuple[int, int]
    desktop: DesktopTransform
    frame_digest: str = field(repr=False)


@dataclass(frozen=True)
class GroundingProof:
    inference: ObservationRef
    dispatch: ObservationRef
    method: str


@dataclass(frozen=True)
class TargetBinding:
    inference: ValidatedObservation
    target: TargetSnapshot
    owner: str
    authority_epoch: str
    generation: int
    deadline: float
    revoked: object = field(repr=False, compare=False)
    current: ValidatedObservation
    proof: GroundingProof
    signature: str = field(default='', repr=False)


def binding_scope(binding):
    """Original immutable scope; current proof never changes approved arguments."""
    return dict(inference=asdict(binding.inference), target=asdict(binding.target),
                owner=binding.owner, authority_epoch=binding.authority_epoch,
                generation=binding.generation, deadline=binding.deadline)


def _require(condition, code):
    if not condition:
        raise ValueError(code)


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _id(value):
    return type(value) is str and 0 < len(value) <= 256 and '\x00' not in value


def _size(value):
    return (type(value) is tuple and len(value) == 2 and
            all(type(v) is int and 0 < v <= 32768 for v in value))


def _rect(value):
    return (type(value) is tuple and len(value) == 4 and
        all(type(v) is int and -(2**31) <= v < 2**31 for v in value) and
        0 < value[2] <= 32768 and 0 < value[3] <= 32768 and
        all(-(2**31) <= value[i] + value[i+2] < 2**31 for i in (0, 1)))


def _contains(rect, point):
    return all(rect[i] <= point[i] < rect[i] + rect[i+2] for i in (0, 1))


def _transform(geometry, frame_size):
    _require(type(geometry) is DesktopTransform and _size(frame_size), 'invalid_geometry')
    _require(geometry.coordinate_space == 'physical_virtual_desktop' and
        _rect((geometry.left, geometry.top, geometry.width, geometry.height)), 'invalid_geometry')
    for scale, extent, pixels in zip((geometry.scale_x, geometry.scale_y),
                                    (geometry.width, geometry.height), frame_size):
        _require(_finite(scale) and scale > 0 and
                 math.isclose(scale * pixels, extent, rel_tol=1e-12, abs_tol=1e-9), 'invalid_geometry')


def to_physical(point, geometry, frame_size):
    """Pure C05: normalized frame edges → physical integer pixel, no clamping."""
    try:
        _transform(geometry, frame_size)
        _require(type(point) is tuple and len(point) == 2 and
                 all(_finite(v) and 0 <= v < 1 for v in point), 'invalid_coordinate')
        result = (geometry.left + math.floor(point[0] * geometry.width),
                  geometry.top + math.floor(point[1] * geometry.height))
        _require(_contains((geometry.left, geometry.top, geometry.width, geometry.height), result), 'invalid_coordinate')
        return result
    except (ValueError, TypeError, OverflowError):
        return SafeError('invalid_geometry_or_coordinate')


def to_absolute(point, virtual_bounds):
    """Pure C06 arithmetic only. No SendInput structure, adapter or call.

    First/last addressable pixels map to 0/65535, half-up integer rounding;
    a one-pixel axis maps to zero. Right/bottom rectangle edges are excluded.
    """
    if (not _rect(virtual_bounds) or type(point) is not tuple or len(point) != 2 or
            any(type(v) is not int for v in point) or not _contains(virtual_bounds, point)):
        return SafeError('invalid_virtual_coordinate')
    return tuple(0 if virtual_bounds[i+2] == 1 else
        ((point[i] - virtual_bounds[i]) * 65535 + (virtual_bounds[i+2]-1)//2) //
        (virtual_bounds[i+2]-1) for i in (0, 1))


def validate_observation(obs, snapshot, now):
    """C03: validate a currently owned frame; no copied handle revives pixels."""
    try:
        _require(type(obs) is Observation, 'observation_unavailable')
        stream = obs._stream()
        _require(stream is not None and stream.latest() is obs and obs.image is not None,
                 'stale_observation')
        _require(type(snapshot) is TargetSnapshot, 'invalid_binding')
        ref = ObservationRef(obs.session_id, obs.source_id, obs.sequence)
        _require(ref == snapshot.observation, 'observation_mismatch')
        _require(type(obs.sequence) is int and obs.sequence > 0 and
                 _id(obs.session_id) and _id(obs.source_id), 'invalid_binding')
        _require(obs.source_type in ('window', 'monitor') and obs.timing_basis == 'native_request',
                 'unsupported_coordinate_source')
        _require(_size(obs.original_dimensions) and _size(obs.processed_dimensions), 'invalid_geometry')
        _transform(obs.desktop, obs.processed_dimensions)
        _require(obs.original_dimensions == (obs.desktop.width, obs.desktop.height), 'invalid_geometry')
        origin, received = obs.capture_not_before_monotonic, obs.received_monotonic
        _require(all(_finite(v) for v in (origin, received, now, stream.freshness_seconds)) and
            origin <= received <= now and stream.freshness_seconds > 0, 'invalid_observation_clock')
        _require(origin <= now < origin + stream.freshness_seconds, 'stale_observation')
        _require(type(obs.image) is bytes and 0 < len(obs.image) <= 8 * 1024 * 1024, 'invalid_frame')
        return ValidatedObservation(ref, obs.source_type, origin, received,
            origin + stream.freshness_seconds, obs.original_dimensions,
            obs.processed_dimensions, obs.desktop, hashlib.sha256(obs.image).hexdigest())
    except ValueError as exc:
        return SafeError(str(exc))
    except (TypeError, AttributeError, OverflowError):
        return SafeError('invalid_binding')


def validate_target(expected, current, *, allow_unfocused=False):
    """C08: complete identity + eligibility + geometry; no title-based match."""
    try:
        _require(type(expected) is TargetSnapshot and type(current) is TargetSnapshot, 'invalid_binding')
        _require(type(current.observation) is ObservationRef and type(current.observation.sequence) is int and
            current.observation.sequence > 0 and _id(current.observation.session_id) and
            _id(current.observation.source_id), 'invalid_binding')
        identity = current.identity
        _require(type(identity) is WindowIdentity and type(identity.hwnd) is int and identity.hwnd > 0 and
            type(identity.pid) is int and identity.pid > 0 and all(_id(v) for v in
            (identity.creation_id, identity.class_name, identity.window_generation, identity.desktop_id)), 'invalid_target_identity')
        e = current.evidence
        _require(type(e) is TargetEvidence and all(_id(v) for v in (e.window_id, e.control_id, e.revision)) and
            type(e.input_epoch) is int and e.input_epoch >= 0 and type(e.patterns) is tuple and
            all(_id(v) for v in e.patterns), 'invalid_target_identity')
        _require(current.alive is True and current.visible is True and
            (e.foreground is True or allow_unfocused) and e.enabled is True and e.password is False, 'target_ineligible')
        _require(_rect(current.bounds) and _rect(current.virtual_bounds) and
            all(_id(v) for v in (current.geometry_revision, current.display_revision, current.monitor_id)) and
            type(current.rotation) is int and current.rotation in (0, 90, 180, 270) and
            type(current.dpi) is tuple and len(current.dpi) == 2 and
            all(_finite(v) and 0 < v <= 960 for v in current.dpi), 'invalid_geometry')
        _require(expected.identity == current.identity and expected.evidence == current.evidence, 'target_mismatch')
        _require(all(getattr(expected, f) == getattr(current, f) for f in
            ('bounds', 'virtual_bounds', 'geometry_revision', 'display_revision', 'monitor_id', 'dpi', 'rotation')), 'geometry_mismatch')
        return current
    except ValueError as exc:
        return SafeError(str(exc))
    except (TypeError, AttributeError, OverflowError):
        return SafeError('invalid_binding')


def reground(proposal, binding, observation, current_target, now, *, allow_new=False, allow_unfocused=False):
    """C04 conservative proof: byte-identical *whole* frame, unchanged identity.

    Never change the proposal/ref, renew its scope deadline, retain screenshots,
    interpret perceptual similarity as equality, or recover revoked image access.
    """
    try:
        _require(type(binding) is TargetBinding and proposal.observation == binding.inference.reference,
                 'invalid_binding')
        _require(not binding.revoked.is_set(), 'session_invalidated')
        _require(_finite(now) and binding.inference.origin <= now < binding.deadline, 'proposal_expired')
        target = validate_target(binding.target, current_target, allow_unfocused=allow_unfocused)
        if isinstance(target, SafeError): return target
        current = validate_observation(observation, target, now)
        if isinstance(current, SafeError): return current
        old = binding.inference
        _require((current.reference.session_id, current.reference.source_id, current.source_type) ==
                 (old.reference.session_id, old.reference.source_id, old.source_type), 'source_mismatch')
        _require(current.reference.sequence >= old.reference.sequence and current.origin >= old.origin and
                 current.received >= old.received, 'observation_mismatch')
        _require(current.frame_size == old.frame_size and current.original_dimensions == old.original_dimensions and
                 current.desktop == old.desktop, 'geometry_mismatch')
        _require(current.frame_digest == old.frame_digest, 'visual_context_changed')
        if current.reference == old.reference:
            _require(current == old, 'observation_identity_rewritten')
        if not allow_new:
            _require(current == binding.current, 'observation_changed')
        for point in ((proposal.action.start, proposal.action.end) if isinstance(proposal.action, Drag) else
                      (proposal.action.point,) if isinstance(proposal.action, (Move, Click, Scroll)) else ()):
            physical = to_physical(point, current.desktop, current.frame_size)
            _require(not isinstance(physical, SafeError) and _contains(target.bounds, physical) and
                     _contains(target.virtual_bounds, physical), 'coordinate_outside_target')
        method = 'original_frame' if current.reference == old.reference else 'identical_frame_and_target'
        return replace(binding, current=current, proof=GroundingProof(old.reference, current.reference, method))
    except ValueError as exc:
        return SafeError(str(exc))
    except (TypeError, AttributeError, OverflowError):
        return SafeError('invalid_binding')
