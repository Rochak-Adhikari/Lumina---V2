"""Lumina Earth persistent search history storage (P1.6).

Dedicated SQLite storage in ``<runtime_root>/earth.sqlite3``, sharing the database
with P1.4 waypoints while isolating schema and lifecycle.
"""
from __future__ import annotations

import math
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_FILENAME = 'earth.sqlite3'
NAME_MAX = 120
DISPLAY_NAME_MAX = 300
COUNTRY_MAX = 120
COUNTRY_CODE_MAX = 10
ADMIN1_MAX = 120
TIMEZONE_MAX = 64
ID_RE = re.compile(r'^[0-9a-f]{32}$')
LIST_DEFAULT = 50
LIST_MAX = 200
MAX_HISTORY = 100
DEDUP_WINDOW_SECONDS = 120.0

FIELDS = (
    'name',
    'latitude',
    'longitude',
    'display_name',
    'country',
    'country_code',
    'admin1',
    'timezone',
)
REQUIRED = ('name', 'latitude', 'longitude')

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS search_history (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE CHECK (length(id) = 32),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND {NAME_MAX}),
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    display_name TEXT CHECK (display_name IS NULL OR length(display_name) <= {DISPLAY_NAME_MAX}),
    country TEXT CHECK (country IS NULL OR length(country) <= {COUNTRY_MAX}),
    country_code TEXT CHECK (country_code IS NULL OR length(country_code) <= {COUNTRY_CODE_MAX}),
    admin1 TEXT CHECK (admin1 IS NULL OR length(admin1) <= {ADMIN1_MAX}),
    timezone TEXT CHECK (timezone IS NULL OR length(timezone) <= {TIMEZONE_MAX}),
    searched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_history_searched_at ON search_history(searched_at DESC);
"""


class HistoryError(Exception):
    code = 'internal_error'


class HistoryValidationError(HistoryError):
    code = 'invalid_argument'


class HistoryNotFound(HistoryError):
    code = 'not_found'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def parse_utc_timestamp(ts: str) -> datetime:
    try:
        clean = ts.replace('Z', '+00:00')
        return datetime.fromisoformat(clean)
    except Exception:
        return datetime.now(timezone.utc)


def validate_id(value: Any) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise HistoryValidationError('History id is invalid.')
    return value


def _coordinate(field: str, value: Any, bound: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoryValidationError(f'{field} must be a number.')
    val = float(value)
    if not math.isfinite(val):
        raise HistoryValidationError(f'{field} must be a finite number.')
    if not -bound <= val <= bound:
        raise HistoryValidationError(f'{field} must be between -{bound} and {bound}.')
    return val


def _validate_str(field: str, value: Any, max_len: int, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise HistoryValidationError(f'{field} is required.')
        return None
    if not isinstance(value, str):
        raise HistoryValidationError(f'{field} must be a string.')
    clean = value.strip()
    if not clean:
        if required:
            raise HistoryValidationError(f'{field} must not be empty.')
        return None
    if len(clean) > max_len:
        raise HistoryValidationError(f'{field} must be at most {max_len} characters.')
    return clean


def _validate_field(field: str, value: Any) -> Any:
    if field == 'name':
        return _validate_str('name', value, NAME_MAX, required=True)
    if field == 'latitude':
        return _coordinate('latitude', value, 90.0)
    if field == 'longitude':
        return _coordinate('longitude', value, 180.0)
    if field == 'display_name':
        return _validate_str('display_name', value, DISPLAY_NAME_MAX)
    if field == 'country':
        return _validate_str('country', value, COUNTRY_MAX)
    if field == 'country_code':
        return _validate_str('country_code', value, COUNTRY_CODE_MAX)
    if field == 'admin1':
        return _validate_str('admin1', value, ADMIN1_MAX)
    if field == 'timezone':
        return _validate_str('timezone', value, TIMEZONE_MAX)
    raise HistoryValidationError(f'Unsupported field: {field}')


def validate_create(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HistoryValidationError('Request body must be a JSON object.')
    unknown = sorted(set(body) - set(FIELDS))
    if unknown:
        raise HistoryValidationError('Unsupported field(s): ' + ', '.join(map(str, unknown)))
    missing = [f for f in REQUIRED if f not in body]
    if missing:
        raise HistoryValidationError('Missing required field(s): ' + ', '.join(missing))
    return {f: _validate_field(f, body.get(f)) for f in FIELDS}


def validate_paging(limit: Any, offset: Any) -> tuple[int, int]:
    def parse(raw: Any, default: int, lo: int, hi: int, name: str) -> int:
        if raw is None:
            return default
        if not isinstance(raw, str) or not re.fullmatch(r'\d{1,6}', raw):
            raise HistoryValidationError(f'{name} must be an integer between {lo} and {hi}.')
        val = int(raw)
        if not lo <= val <= hi:
            raise HistoryValidationError(f'{name} must be an integer between {lo} and {hi}.')
        return val

    return (
        parse(limit, LIST_DEFAULT, 1, LIST_MAX, 'limit'),
        parse(offset, 0, 0, 999999, 'offset'),
    )


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {
        'id': r['id'],
        'name': r['name'],
        'latitude': r['latitude'],
        'longitude': r['longitude'],
        'display_name': r['display_name'],
        'country': r['country'],
        'country_code': r['country_code'],
        'admin1': r['admin1'],
        'timezone': r['timezone'],
        'searched_at': r['searched_at'],
    }


class SearchHistoryStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.initialize()

    @classmethod
    def for_config(cls, config: Any) -> SearchHistoryStore:
        return cls(Path(config.runtime_root) / DB_FILENAME)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def list(self, limit: int = LIST_DEFAULT, offset: int = 0) -> dict[str, Any]:
        with closing(self._connect()) as conn:
            total = conn.execute('SELECT COUNT(*) FROM search_history').fetchone()[0]
            rows = conn.execute(
                'SELECT * FROM search_history ORDER BY searched_at DESC, seq DESC LIMIT ? OFFSET ?',
                (limit, offset),
            ).fetchall()
        return {
            'history': [_row(r) for r in rows],
            'total': total,
            'limit': limit,
            'offset': offset,
        }

    def get(self, history_id: str) -> dict[str, Any]:
        validate_id(history_id)
        with closing(self._connect()) as conn:
            r = conn.execute('SELECT * FROM search_history WHERE id = ?', (history_id,)).fetchone()
        if r is None:
            raise HistoryNotFound('Search history entry not found.')
        return _row(r)

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        now_str = utc_now()
        now_dt = parse_utc_timestamp(now_str)

        with closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                # 1. Check for rapid duplicate (same name and within 0.001 deg of lat/lon)
                # within DEDUP_WINDOW_SECONDS
                candidates = conn.execute(
                    'SELECT * FROM search_history WHERE name = ? ORDER BY searched_at DESC LIMIT 5',
                    (values['name'],),
                ).fetchall()

                match = None
                for c in candidates:
                    d_lat = abs(c['latitude'] - values['latitude'])
                    d_lon = abs(c['longitude'] - values['longitude'])
                    if d_lat < 0.001 and d_lon < 0.001:
                        c_dt = parse_utc_timestamp(c['searched_at'])
                        if (now_dt - c_dt).total_seconds() <= DEDUP_WINDOW_SECONDS:
                            match = c
                            break

                if match is not None:
                    # Update timestamp and optional metadata if newly provided
                    conn.execute(
                        """
                        UPDATE search_history
                        SET searched_at = ?,
                            display_name = COALESCE(?, display_name),
                            country = COALESCE(?, country),
                            country_code = COALESCE(?, country_code),
                            admin1 = COALESCE(?, admin1),
                            timezone = COALESCE(?, timezone)
                        WHERE id = ?
                        """,
                        (
                            now_str,
                            values.get('display_name'),
                            values.get('country'),
                            values.get('country_code'),
                            values.get('admin1'),
                            values.get('timezone'),
                            match['id'],
                        ),
                    )
                    conn.execute('COMMIT')
                    updated = conn.execute(
                        'SELECT * FROM search_history WHERE id = ?', (match['id'],)
                    ).fetchone()
                    return _row(updated)

                # 2. Insert new record
                hid = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO search_history
                        (id, name, latitude, longitude, display_name, country, country_code, admin1, timezone, searched_at)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hid,
                        values['name'],
                        values['latitude'],
                        values['longitude'],
                        values.get('display_name'),
                        values.get('country'),
                        values.get('country_code'),
                        values.get('admin1'),
                        values.get('timezone'),
                        now_str,
                    ),
                )

                # 3. Enforce bounded history size (retain newest MAX_HISTORY)
                total = conn.execute('SELECT COUNT(*) FROM search_history').fetchone()[0]
                if total > MAX_HISTORY:
                    conn.execute(
                        """
                        DELETE FROM search_history
                        WHERE id NOT IN (
                            SELECT id FROM search_history
                            ORDER BY searched_at DESC, seq DESC
                            LIMIT ?
                        )
                        """,
                        (MAX_HISTORY,),
                    )

                conn.execute('COMMIT')
                created = conn.execute(
                    'SELECT * FROM search_history WHERE id = ?', (hid,)
                ).fetchone()
                return _row(created)
            except Exception:
                conn.execute('ROLLBACK')
                raise

    def delete(self, history_id: str) -> bool:
        validate_id(history_id)
        with closing(self._connect()) as conn:
            cur = conn.execute('DELETE FROM search_history WHERE id = ?', (history_id,))
        if cur.rowcount == 0:
            raise HistoryNotFound('Search history entry not found.')
        return True

    def clear(self) -> int:
        with closing(self._connect()) as conn:
            cur = conn.execute('DELETE FROM search_history')
        return cur.rowcount
