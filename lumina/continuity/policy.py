"""Bounded, model-independent validation. Memory is not a credential vault."""
import json
import math
import re
from datetime import datetime, timezone

PRIVACY = {'public', 'private', 'sensitive', 'device_local', 'cloud_blocked', 'cloud_allowed'}
SECRET = re.compile(
    r'-----BEGIN (?:\w+ )?PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{20,})'
    r'|\bBearer\s+[A-Za-z0-9._~-]{8,}'
    r'|\b(?:password|passphrase|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|recovery[_ -]?code|authorization|cookie)\s*(?:[=:]|is\b)\s*\S+', re.I)
SECRET_KEYS = re.compile(r'^(?:password|passphrase|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|authorization|cookie|credentials|recovery[_-]?codes?)$', re.I)


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def timestamp(value=None):
    if value is None:
        return now()
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Use a timezone-aware ISO timestamp.')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Use a timezone-aware ISO timestamp.')
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


def text(value, name='text', maximum=12000, *, empty=False):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value or (not empty and not value.strip()):
        raise ValueError(f'{name} must be bounded, non-empty text.')
    from .models import contains_secret
    if SECRET.search(value) or contains_secret(value):
        raise ValueError('Credentials cannot be stored as ordinary memory.')
    return value.strip()


def score(value, name='confidence'):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'{name} must be between zero and one.')
    return float(value)


def document(value, *, maximum=24000):
    def check(obj, depth=0):
        if depth > 7:
            raise ValueError('Memory data is too deeply nested.')
        if isinstance(obj, dict):
            if len(obj) > 60:
                raise ValueError('Memory data contains too many fields.')
            for key, item in obj.items():
                if not isinstance(key, str) or len(key) > 100 or SECRET_KEYS.fullmatch(key):
                    raise ValueError('Invalid or credential-bearing memory field.')
                check(item, depth + 1)
        elif isinstance(obj, list):
            if len(obj) > 200:
                raise ValueError('Memory collection exceeds its bound.')
            for item in obj:
                check(item, depth + 1)
        elif isinstance(obj, str):
            text(obj, empty=True)
        elif obj is not None and type(obj) not in (bool, int, float):
            raise ValueError('Memory data must be plain JSON.')
    check(value)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode('utf-8')) > maximum:
        raise ValueError('Memory data exceeds its size limit.')
    return json.loads(encoded)


def public_record(record, *, online=False, include_sensitive=False):
    privacy = record.get('privacy_class', 'private')
    if not include_sensitive and privacy == 'sensitive':
        return False
    if online and (privacy in {'sensitive', 'device_local', 'cloud_blocked'} or record.get('sync_policy') == 'cloud_blocked'):
        return False
    return True
