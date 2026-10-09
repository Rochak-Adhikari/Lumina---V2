"""Provider-independent continuity records and conservative secret screening.

These types describe data, not authority: admission and source trust belong to
the service. JSON fields keep their storage names but contain Python values.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Deliberately conservative: legacy content is never a credential vault. Do not
# include matching text in diagnostics, exceptions, or migration reports.
_SECRET_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    r"\bAIza[A-Za-z0-9_-]{30,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b",
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\b(?:password|passwd|pwd|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|auth(?:entication)?[ _-]?token|client[ _-]?secret|secret[ _-]?key|recovery[ _-]?codes?)\b[\s\"']*(?:[:=]|\bis\b)[\s\"']*\S+",
    r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@",
))


def contains_secret(value: Any) -> bool:
    """Screen text or nested JSON without returning the suspected credential."""
    if isinstance(value, dict):
        return any(contains_secret(f"{key}: {item}") or contains_secret(item)
                   for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item) for item in value)
    return isinstance(value, str) and any(p.search(value) for p in _SECRET_PATTERNS)


def safe_text(value: str, *, max_length: int = 12000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError("Memory text is empty or exceeds the size limit.")
    if contains_secret(value):
        raise ValueError("Secret-like content cannot be stored as ordinary memory.")
    return value.strip()


class DictModel:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Record(DictModel):
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    version: int = 1
    privacy_class: str = "private"
    sync_policy: str = "local_only"
    device_scope: str | None = None


@dataclass
class Event(Record):
    event_type: str = ""
    timestamp: str = field(default_factory=utc_now)
    session_id: str | None = None
    device_id: str | None = None
    project_id: str | None = None
    source_type: str = "unknown"
    source_id: str | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5


@dataclass
class Entity(Record):
    kind: str = "concept"
    name: str = ""
    canonical_key: str = ""
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fact(Record):
    subject_entity_id: str | None = None
    predicate: str = ""
    object_value: str = ""
    object_entity_id: str | None = None
    confidence: float = 0.7
    stability: float = 0.5
    importance: float = 0.5
    valid_from: str = field(default_factory=utc_now)
    valid_until: str | None = None
    status: str = "active"
    confirmed_by_user: int = 0
    source_type: str = "unknown"
    last_confirmed_at: str | None = None
    project_id: str | None = None


@dataclass
class Evidence(Record):
    record_type: str = "fact"
    record_id: str = ""
    event_id: str | None = None
    source_type: str = "unknown"
    source_id: str | None = None
    observed_at: str = field(default_factory=utc_now)
    extraction_method: str = "unknown"
    confidence: float = 0.7
    confirmed_by_user: int = 0
    model_metadata_json: dict[str, Any] = field(default_factory=dict)
    source_fingerprint: str = ""


@dataclass
class Episode(Record):
    title: str = ""
    summary: str = ""
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    project_id: str | None = None
    status: str = "open"
    outcome: str | None = None
    importance: float = 0.5


@dataclass
class Decision(Record):
    subject: str = ""
    chosen_option: str = ""
    alternatives_json: list[Any] = field(default_factory=list)
    reasoning: str = ""
    constraints_json: list[Any] = field(default_factory=list)
    assumptions_json: list[Any] = field(default_factory=list)
    expected_outcome: str | None = None
    actual_outcome: str | None = None
    status: str = "active"
    made_at: str = field(default_factory=utc_now)
    superseded_at: str | None = None
    project_id: str | None = None
    importance: float = 0.5


@dataclass
class Goal(Record):
    description: str = ""
    status: str = "active"
    priority: float = 0.5
    deadline: str | None = None
    completed_at: str | None = None
    project_id: str | None = None
    parent_goal_id: str | None = None


@dataclass
class Commitment(Record):
    description: str = ""
    owner_entity_id: str | None = None
    due_at: str | None = None
    status: str = "open"
    confidence: float = 0.7
    project_id: str | None = None


@dataclass
class OpenLoop(Record):
    description: str = ""
    status: str = "open"
    blocked_by_json: list[Any] = field(default_factory=list)
    next_action: str | None = None
    resolved_at: str | None = None
    project_id: str | None = None
    task_id: str | None = None


@dataclass
class Relationship(Record):
    source_entity: str = ""
    relationship_type: str = ""
    target_entity: str = ""
    confidence: float = 0.7
    valid_from: str = field(default_factory=utc_now)
    valid_until: str | None = None
    source_event: str | None = None
    project_id: str | None = None


@dataclass
class MemoryCandidate(Record):
    proposal_json: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    decision: str | None = None
    reason: str | None = None
    source_event_id: str | None = None
    record_id: str | None = None


@dataclass
class Prediction(Record):
    prediction: str = ""
    horizon: str | None = None
    confidence: float = 0.5
    status: str = "pending"
    outcome: str | None = None
    evidence_ids_json: list[str] = field(default_factory=list)
    project_id: str | None = None


@dataclass
class BehaviorPattern(Record):
    pattern: str = ""
    confidence: float = 0.5
    status: str = "hypothesis"
    evidence_count: int = 0
    supporting_events_json: list[str] = field(default_factory=list)
    last_observed: str | None = None
    project_id: str | None = None


@dataclass
class PersonalState(DictModel):
    active_project: str | None = None
    active_task: str | None = None
    current_device: str | None = None
    current_workspace: str | None = None
    recent_episode: dict[str, Any] | None = None
    open_loops: list[dict[str, Any]] = field(default_factory=list)
    active_goals: list[dict[str, Any]] = field(default_factory=list)
    recent_decisions: list[dict[str, Any]] = field(default_factory=list)
    blocked_items: list[dict[str, Any]] = field(default_factory=list)
    last_known_activity: str | None = None


@dataclass
class ContinuationContext(DictModel):
    project: str | None = None
    task: str | None = None
    workspace: str | None = None
    files: list[str] = field(default_factory=list)
    agent_sessions: list[dict[str, Any]] = field(default_factory=list)
    recent_decisions: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[Any] = field(default_factory=list)
    open_loops: list[dict[str, Any]] = field(default_factory=list)
    next_dependencies: list[Any] = field(default_factory=list)
    state: PersonalState = field(default_factory=PersonalState)


@dataclass
class MemoryProposal(DictModel):
    kind: str = "fact"
    subject: str = "user"
    predicate: str = ""
    object: str = ""
    source_event_id: str | None = None
    confidence: float = 0.7
    stability: float = 0.5
    importance: float = 0.5
    project_id: str | None = None
    privacy_class: str = "private"
    data: dict[str, Any] = field(default_factory=dict)
    reason: str = "proposal"
    supersedes: str | None = None
