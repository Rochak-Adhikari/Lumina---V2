"""Outbound Provider Privacy Guard for Lumina.

Enforces a fail-closed privacy boundary between Lumina's local memory system
and external AI providers (Gemini, fallback providers, and external reasoning APIs).

Classification Rules:
- 'public': Eligible for external model context when relevant and otherwise permitted.
- 'private': Remains local by default (must not be sent to external providers).
- 'sensitive': Prohibited from external transmission.
- 'device_local': Remains local (must not be sent externally).
- 'cloud_blocked': Prohibited from external transmission.
- Missing, None, malformed, or unknown: Prohibited from external transmission (fail-closed).
"""
import copy
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger('lumina.privacy')

# Secret patterns that must never appear in outbound model context
_SECRET_PATTERN = re.compile(
    r'(?i)(?:\b(?:password|passwd|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|client[ _-]?secret|recovery[ _-]?code|auth(?:orization)?)\s*[:=]\s*\S+'
    r'|\bBearer\s+[A-Za-z0-9._~-]{8,}'
    r'|-----BEGIN (?:[A-Z0-9_]+ )?PRIVATE KEY-----'
    r'|\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{20,}))'
)

# Allowed classification for outbound transmission
PERMITTED_OUTBOUND_CLASSES: Set[str] = {'public'}

# Explicitly prohibited classifications
EXPLICITLY_PROHIBITED_CLASSES: Set[str] = {
    'private', 'sensitive', 'device_local', 'cloud_blocked', 'journal', 'internal'
}


class ProviderPrivacyGuard:
    """Outbound privacy guard that screens and sanitizes model context, tool results,
    and history before external transmission."""

    def __init__(self):
        self._blocked_count = 0
        self._reasons: Dict[str, int] = {
            'private': 0,
            'sensitive': 0,
            'device_local': 0,
            'cloud_blocked': 0,
            'unknown_classification': 0,
            'missing_classification': 0,
            'secret_detected': 0,
            'sync_policy_blocked': 0,
        }

    @property
    def blocked_count(self) -> int:
        return self._blocked_count

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return safe statistical diagnostics. Never includes raw content or keys."""
        return {
            'blocked_count': self._blocked_count,
            'reasons': dict(self._reasons),
        }

    def _record_blocked(self, reason: str) -> None:
        self._blocked_count += 1
        key = reason.lower() if reason.lower() in self._reasons else 'unknown_classification'
        self._reasons[key] = self._reasons.get(key, 0) + 1

    def is_record_outbound_permitted(self, record: Any) -> Tuple[bool, str]:
        """Determine if a memory record or entity dictionary is permitted for outbound transmission.
        
        Returns:
            (is_permitted: bool, reason_category: str)
        """
        if not isinstance(record, dict):
            return False, 'malformed_record'

        # Check sync_policy
        if record.get('sync_policy') == 'cloud_blocked':
            return False, 'sync_policy_blocked'

        # Check boolean cloud flags
        if record.get('cloud_allowed') is False or record.get('cloud_blocked') is True or record.get('device_local') is True:
            return False, 'cloud_blocked'

        # Extract privacy classification
        privacy = None
        for key in ('privacy_class', 'privacy', 'category', 'sensitivity'):
            val = record.get(key)
            if val is not None:
                privacy = str(val).strip().lower()
                break

        if privacy is None:
            # Memory record without classification: fail-closed
            return False, 'missing_classification'

        if privacy in EXPLICITLY_PROHIBITED_CLASSES:
            return False, privacy

        if privacy in PERMITTED_OUTBOUND_CLASSES:
            return True, 'permitted'

        # Unknown / malformed classification: fail-closed
        return False, 'unknown_classification'

    def is_memory_like(self, obj: Dict[str, Any]) -> bool:
        """Check if a dictionary appears to be a memory record, candidate, or entity."""
        if any(k in obj for k in ('privacy_class', 'privacy', 'sync_policy')):
            return True
        if any(k in obj for k in ('subject_entity_id', 'predicate', 'object_value')):
            return True
        if 'record' in obj and isinstance(obj.get('record'), dict):
            return True
        if obj.get('kind') in {'fact', 'decision', 'goal', 'commitment', 'open_loop', 'episode'}:
            return True
        return False

    def sanitize_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Sanitize a single memory record. Returns None if disallowed."""
        permitted, reason = self.is_record_outbound_permitted(record)
        if not permitted:
            self._record_blocked(reason)
            return None

        # Record is public; strip internal local-only keys if present
        clean = {}
        for k, v in record.items():
            if k in {'path', 'db', 'device_id', 'session_id', 'workspace', 'workspace_path', 'canonical_key'}:
                continue
            clean[k] = self.sanitize_payload(v)
        return clean

    def sanitize_payload(self, value: Any) -> Any:
        """Recursively sanitize any payload (tool argument, result, context dict, list)."""
        if isinstance(value, dict):
            # Check if this dictionary itself is a memory record
            if self.is_memory_like(value):
                # If it's a candidate wrapper: {'id': ..., 'kind': ..., 'record': {...}, 'evidence': [...]}
                if 'record' in value and isinstance(value.get('record'), dict):
                    rec = value['record']
                    permitted, reason = self.is_record_outbound_permitted(rec)
                    if not permitted:
                        self._record_blocked(reason)
                        return None
                    # Also screen evidence
                    clean_evidence = []
                    for ev in value.get('evidence', []):
                        ev_safe = self.sanitize_payload(ev)
                        if ev_safe is not None:
                            clean_evidence.append(ev_safe)
                    clean_wrapper = {k: self.sanitize_payload(v) for k, v in value.items() if k != 'evidence'}
                    clean_wrapper['evidence'] = clean_evidence
                    return clean_wrapper

                # Direct record
                permitted, reason = self.is_record_outbound_permitted(value)
                if not permitted:
                    self._record_blocked(reason)
                    return None

            # General dictionary: sanitize children
            result = {}
            for k, v in value.items():
                if k in {'path', 'db', 'device_id', 'session_id', 'workspace', 'workspace_path', 'canonical_key'}:
                    continue
                safe_v = self.sanitize_payload(v)
                if safe_v is not None:
                    result[k] = safe_v
            return result

        elif isinstance(value, list):
            cleaned = []
            for item in value:
                safe_item = self.sanitize_payload(item)
                if safe_item is not None:
                    cleaned.append(safe_item)
            return cleaned

        elif isinstance(value, str):
            if _SECRET_PATTERN.search(value):
                self._record_blocked('secret_detected')
                return None
            return value

        return value

    def sanitize_tool_result(self, tool_name: str, result: Any) -> Any:
        """Sanitize a tool execution result before outbound transmission."""
        if not isinstance(result, dict):
            return self.sanitize_payload(result)

        # Handle top-level tool response dict
        sanitized = copy.deepcopy(result)

        # If tool returned items list (e.g. memory_recall, memory_continuation)
        if 'items' in sanitized and isinstance(sanitized['items'], list):
            filtered_items = []
            for item in sanitized['items']:
                safe = self.sanitize_payload(item)
                if safe is not None:
                    filtered_items.append(safe)
            sanitized['items'] = filtered_items
            sanitized['count'] = len(filtered_items)
            if 'returned_count' in sanitized:
                sanitized['returned_count'] = len(filtered_items)

        # Handle specific continuation lists: open_loops, goals, commitments, etc.
        for list_key in ('open_loops', 'goals', 'commitments', 'decisions', 'events', 'relationships'):
            if list_key in sanitized and isinstance(sanitized[list_key], list):
                sanitized[list_key] = [
                    safe for item in sanitized[list_key]
                    if (safe := self.sanitize_payload(item)) is not None
                ]

        # Handle single record in explain/detail response
        if 'record' in sanitized and isinstance(sanitized['record'], dict):
            safe_rec = self.sanitize_payload(sanitized['record'])
            if safe_rec is None:
                # The single requested record is restricted
                return {
                    'ok': False,
                    'error': 'This memory record is restricted to local use and cannot be transmitted to external providers.',
                    'untrusted_evidence': True
                }
            sanitized['record'] = safe_rec

        # Sanitize any nested context
        for k, v in list(sanitized.items()):
            if k not in ('items', 'open_loops', 'goals', 'commitments', 'decisions', 'events', 'relationships', 'record'):
                sanitized[k] = self.sanitize_payload(v)

        return sanitized

    def sanitize_text(self, text: str) -> str:
        """Sanitize plain text prompts or terminal tails before external transmission.
        
        Redacts credentials/secret patterns safely.
        """
        if not isinstance(text, str):
            return ""

        def _redact_secret(match):
            self._record_blocked('secret_detected')
            return "[REDACTED_CREDENTIAL]"

        return _SECRET_PATTERN.sub(_redact_secret, text)

    def sanitize_history(self, history: List[Any]) -> List[Any]:
        """Sanitize provider history objects before injecting into next prompt."""
        if not isinstance(history, list):
            return []
        sanitized = []
        for item in history:
            safe = self.sanitize_payload(item)
            if safe is not None:
                sanitized.append(safe)
        return sanitized


class GuardedProvider:
    """Wraps any provider (e.g. fallback provider) with ProviderPrivacyGuard."""

    def __init__(self, provider, privacy_guard: Optional[ProviderPrivacyGuard] = None):
        self._provider = provider
        self.privacy_guard = privacy_guard or ProviderPrivacyGuard()

    def register_tools(self, specs):
        return self._provider.register_tools(specs)

    async def generate(self, text, handle_tool_call):
        safe_text = self.privacy_guard.sanitize_text(text)

        async def guarded_handler(name, args):
            raw = await handle_tool_call(name, args)
            return self.privacy_guard.sanitize_tool_result(name, raw)

        return await self._provider.generate(safe_text, guarded_handler)

    async def stream(self, text, handle_tool_call):
        safe_text = self.privacy_guard.sanitize_text(text)

        async def guarded_handler(name, args):
            raw = await handle_tool_call(name, args)
            return self.privacy_guard.sanitize_tool_result(name, raw)

        async for chunk in self._provider.stream(safe_text, guarded_handler):
            yield chunk
