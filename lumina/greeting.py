"""Bounded return-session greeting state.

A single small local file records when the previous application run ended
normally. It is transient session metadata, not memory and not a database.
Only a confirmed clean shutdown writes it; a missing, unreadable or malformed
record never produces a return greeting.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

RETURN_WINDOW_SECONDS = 30 * 60


def default_state_path():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    return base / 'LUMINA' / 'last-session.json'


def time_band(now):
    """Local wall-clock greeting band; the caller supplies local time."""
    hour = now.hour
    if 5 <= hour < 12:
        return 'Good morning, sir.'
    if 12 <= hour < 17:
        return 'Good afternoon, sir.'
    if 17 <= hour < 21:
        return 'Good evening, sir.'
    return 'Burning the midnight oil, sir?'


def read_last_end(path):
    """Return the last confirmed shutdown instant, or None when unusable."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(data, dict) or data.get('version') != 1:
        return None
    value = data.get('ended_at')
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        ended = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ended.tzinfo is None:
        return None
    return ended


def greeting_for(path, now, window=RETURN_WINDOW_SECONDS):
    """Choose one greeting line; no state or unreadable state uses the band."""
    ended = read_last_end(path)
    if ended is not None:
        elapsed = (now.astimezone(timezone.utc) - ended.astimezone(timezone.utc)).total_seconds()
        if 0 <= elapsed <= window:
            return 'Welcome back, sir.'
    return time_band(now)


def write_ended(path, now):
    """Persist a confirmed normal end. Failure never breaks shutdown."""
    target = Path(path)
    temporary = target.with_name(target.name + '.tmp')
    payload = json.dumps({'version': 1, 'ended_at': now.astimezone(timezone.utc).isoformat()},
                         separators=(',', ':')).encode('utf-8')
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open('wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        return True
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        return False


def clear_ended(path):
    """Remove the record so an abnormal end cannot claim a clean shutdown."""
    try:
        Path(path).unlink()
        return True
    except OSError:
        return False
