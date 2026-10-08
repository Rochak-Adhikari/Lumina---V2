"""Bounded, local session audit logs with secret redaction."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import time


_SECRET_KEY = re.compile(r"token|secret|password|api[_-]?key|authorization|cookie|credential|refresh", re.I)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*|token\s*[=:]\s*)[^\s,;]+")
_SESSION_NAME = re.compile(r"^[0-9]{8}[-_][0-9]{6}(?:-[0-9a-f]{8})?\.log$")


def _safe(value, key=""):
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k)) for k, v in list(value.items())[:80]}
    if isinstance(value, (list, tuple)):
        return [_safe(item, key) for item in list(value)[:80]]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value[:4000])
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:4000]


class SessionLog:
    """One JSON-lines file per runtime session, retaining only the latest three."""

    MAX_SESSIONS = 3
    MAX_BYTES = 1_000_000

    def __init__(self, root: Path):
        self.directory = Path(root) / "logs" / "sessions"
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.session_id = f"{stamp}-{secrets.token_hex(4)}"
        self.path = self.directory / f"{self.session_id}.log"
        self._prune()
        self.write("session.started", session_id=self.session_id, retention=self.MAX_SESSIONS)

    def _prune(self):
        files = sorted(self.directory.glob("*.log"), key=lambda p: p.stat().st_mtime)
        for old in files[: max(0, len(files) - self.MAX_SESSIONS + 1)]:
            try:
                old.unlink()
            except OSError:
                pass

    def write(self, event, **details):
        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": str(event)[:120],
            **{str(k): _safe(v, str(k)) for k, v in details.items()},
        }
        try:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            if self.path.stat().st_size > self.MAX_BYTES:
                tail = self.path.read_text(encoding="utf-8", errors="replace")[-800_000:]
                self.path.write_text('{"event":"session.log_truncated"}\n' + tail, encoding="utf-8")
        except OSError:
            # Logging must never break a user operation.
            pass

    def close(self):
        self.write("session.closed")

    def listing(self):
        items = []
        for path in sorted(self.directory.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[: self.MAX_SESSIONS]:
            try:
                items.append({"name": path.name, "bytes": path.stat().st_size,
                              "modified": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
            except OSError:
                continue
        return items

    def read(self, name):
        if not isinstance(name, str) or not _SESSION_NAME.fullmatch(name) or Path(name).name != name:
            raise ValueError("Invalid session log name.")
        path = self.directory / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path.read_text(encoding="utf-8", errors="replace")[-200_000:]
