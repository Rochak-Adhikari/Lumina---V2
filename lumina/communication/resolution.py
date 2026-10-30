"""Exact destination matching; labels are hints, provider IDs are send targets."""
import re

from .base import CommunicationError


def query_text(query):
    if not isinstance(query, str) or len(query) > 512 or any(ord(c) < 32 for c in query):
        raise CommunicationError('invalid_destination', 'Use a bounded destination name or provider ID.')
    return query.strip()


def choose(query, candidates, *, complete=True):
    """Never rank a partial/name match into a send destination."""
    unique = {item['destination']: item for item in candidates}
    candidates = sorted(unique.values(), key=lambda item: (item['label'].casefold(), item['destination']))
    if not complete:
        raise CommunicationError('resolution_incomplete', 'Destination lookup is incomplete; choose an explicit provider ID.', candidates=candidates)
    if len(candidates) > 1:
        raise CommunicationError('ambiguous_destination', 'Several destinations match; choose an explicit provider ID.', candidates=candidates)
    if not candidates:
        raise CommunicationError('destination_not_found', 'No known destination matches; supply an explicit provider ID.', candidates=[])
    return {'query': query, 'destination': candidates[0]['destination'], 'candidates': candidates}


def matches(query, candidate):
    return query.casefold() in {str(candidate.get(key, '')).casefold()
                               for key in ('destination', 'label', 'username', 'qualified_name')}


def text_content(content, limit):
    if not isinstance(content, str) or not 1 <= len(content) <= limit:
        raise CommunicationError('invalid_content', f'Text must contain 1–{limit} characters.')


def provider_id(value):
    """Validate a response ID before allowing a provider acceptance receipt."""
    if type(value) is int and value > 0:
        return str(value)
    if isinstance(value, str) and value.strip() and len(value) <= 512 and not re.search(r'\s|[\x00-\x1f\x7f]', value):
        return value
    raise CommunicationError('invalid_response', 'Provider returned no usable message ID; delivery is uncertain.')
