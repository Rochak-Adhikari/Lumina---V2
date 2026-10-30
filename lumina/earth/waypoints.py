"""Lumina Earth persistent waypoint storage (P1.4).

Dedicated SQLite database (``<runtime_root>/earth.sqlite3``), standard library
only. Each operation opens a short-lived connection that is always closed, so
the store is safe to call from worker threads (``asyncio.to_thread``).
"""
from __future__ import annotations

import math
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

DB_FILENAME = 'earth.sqlite3'
NAME_MAX = 120
DESCRIPTION_MAX = 2000
CATEGORY_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,31}$')
ID_RE = re.compile(r'^[0-9a-f]{32}$')
LIST_DEFAULT = 100
LIST_MAX = 500
MAX_WAYPOINTS = 10000
FIELDS = ('name', 'latitude', 'longitude', 'description', 'category')
REQUIRED = ('name', 'latitude', 'longitude')

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS waypoints (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE CHECK (length(id) = 32),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND {NAME_MAX}),
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    description TEXT CHECK (description IS NULL OR length(description) <= {DESCRIPTION_MAX}),
    category TEXT CHECK (category IS NULL OR length(category) BETWEEN 1 AND 32),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class WaypointError(Exception):
    code = 'internal_error'


class WaypointValidationError(WaypointError):
    code = 'invalid_argument'


class WaypointNotFound(WaypointError):
    code = 'not_found'


class WaypointLimitError(WaypointError):
    code = 'limit_exceeded'


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def validate_id(value) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise WaypointValidationError('Waypoint id is invalid.')
    return value


def _coordinate(field, value, bound):
    # bool is a subclass of int; reject it explicitly. Never coerce strings.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WaypointValidationError(f'{field} must be a number.')
    value = float(value)
    if not math.isfinite(value):
        raise WaypointValidationError(f'{field} must be a finite number.')
    if not -bound <= value <= bound:
        raise WaypointValidationError(f'{field} must be between -{bound} and {bound}.')
    return value


def _validate_field(field, value):
    if field == 'name':
        if not isinstance(value, str):
            raise WaypointValidationError('name must be a string.')
        value = value.strip()
        if not value:
            raise WaypointValidationError('name must not be empty.')
        if len(value) > NAME_MAX:
            raise WaypointValidationError(f'name must be at most {NAME_MAX} characters.')
        return value
    if field == 'latitude':
        return _coordinate('latitude', value, 90)
    if field == 'longitude':
        return _coordinate('longitude', value, 180)
    if field == 'description':
        if value is None:
            return None
        if not isinstance(value, str):
            raise WaypointValidationError('description must be a string or null.')
        value = value.strip()
        if len(value) > DESCRIPTION_MAX:
            raise WaypointValidationError(f'description must be at most {DESCRIPTION_MAX} characters.')
        return value or None
    if field == 'category':
        if value is None:
            return None
        if not isinstance(value, str) or not CATEGORY_RE.fullmatch(value):
            raise WaypointValidationError(
                'category must be null or 1-32 chars of lowercase letters, digits, "-" or "_".')
        return value
    raise WaypointValidationError(f'Unsupported field: {field}')


def _check_object(body):
    if not isinstance(body, dict):
        raise WaypointValidationError('Request body must be a JSON object.')
    unknown = sorted(set(body) - set(FIELDS))
    if unknown:
        raise WaypointValidationError('Unsupported field(s): ' + ', '.join(map(str, unknown)))


def validate_create(body) -> dict:
    _check_object(body)
    missing = [f for f in REQUIRED if f not in body]
    if missing:
        raise WaypointValidationError('Missing required field(s): ' + ', '.join(missing))
    return {f: _validate_field(f, body.get(f)) for f in FIELDS}


def validate_update(body) -> dict:
    _check_object(body)
    if not body:
        raise WaypointValidationError('At least one field must be supplied.')
    for f in REQUIRED:
        if f in body and body[f] is None:
            raise WaypointValidationError(f'{f} cannot be null.')
    return {f: _validate_field(f, v) for f, v in body.items()}


def validate_paging(limit, offset):
    def parse(raw, default, lo, hi, name):
        if raw is None:
            return default
        if not isinstance(raw, str) or not re.fullmatch(r'\d{1,6}', raw):
            raise WaypointValidationError(f'{name} must be an integer between {lo} and {hi}.')
        val = int(raw)
        if not lo <= val <= hi:
            raise WaypointValidationError(f'{name} must be an integer between {lo} and {hi}.')
        return val
    return parse(limit, LIST_DEFAULT, 1, LIST_MAX, 'limit'), parse(offset, 0, 0, 999999, 'offset')


def _row(r) -> dict:
    return {'id': r['id'], 'name': r['name'], 'latitude': r['latitude'], 'longitude': r['longitude'],
            'description': r['description'], 'category': r['category'],
            'created_at': r['created_at'], 'updated_at': r['updated_at']}


class WaypointStore:
    def __init__(self, path):
        self.path = Path(path)
        self.initialize()

    @classmethod
    def for_config(cls, config):
        return cls(Path(config.runtime_root) / DB_FILENAME)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 5000')
        return conn

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def list(self, limit=LIST_DEFAULT, offset=0):
        with closing(self._connect()) as conn:
            total = conn.execute('SELECT COUNT(*) FROM waypoints').fetchone()[0]
            rows = conn.execute('SELECT * FROM waypoints ORDER BY seq ASC LIMIT ? OFFSET ?',
                                (limit, offset)).fetchall()
        return {'waypoints': [_row(r) for r in rows], 'total': total, 'limit': limit, 'offset': offset}

    def get(self, waypoint_id):
        validate_id(waypoint_id)
        with closing(self._connect()) as conn:
            r = conn.execute('SELECT * FROM waypoints WHERE id = ?', (waypoint_id,)).fetchone()
        if r is None:
            raise WaypointNotFound('Waypoint not found.')
        return _row(r)

    def create(self, values):
        now = utc_now()
        wid = uuid.uuid4().hex
        with closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                if conn.execute('SELECT COUNT(*) FROM waypoints').fetchone()[0] >= MAX_WAYPOINTS:
                    raise WaypointLimitError(f'At most {MAX_WAYPOINTS} waypoints can be stored.')
                conn.execute(
                    'INSERT INTO waypoints (id, name, latitude, longitude, description, category, created_at, updated_at)'
                    ' VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (wid, values['name'], values['latitude'], values['longitude'],
                     values.get('description'), values.get('category'), now, now))
                r = conn.execute('SELECT * FROM waypoints WHERE id = ?', (wid,)).fetchone()
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
        return _row(r)

    def update(self, waypoint_id, changes):
        validate_id(waypoint_id)
        with closing(self._connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                r = conn.execute('SELECT * FROM waypoints WHERE id = ?', (waypoint_id,)).fetchone()
                if r is None:
                    raise WaypointNotFound('Waypoint not found.')
                diff = {k: v for k, v in changes.items() if r[k] != v}
                if diff:
                    cols = ', '.join(f'{k} = ?' for k in diff)  # keys are whitelisted FIELDS
                    conn.execute(f'UPDATE waypoints SET {cols}, updated_at = ? WHERE id = ?',
                                 (*diff.values(), utc_now(), waypoint_id))
                    r = conn.execute('SELECT * FROM waypoints WHERE id = ?', (waypoint_id,)).fetchone()
                conn.execute('COMMIT')
            except BaseException:
                conn.execute('ROLLBACK')
                raise
        return _row(r), bool(diff)

    def delete(self, waypoint_id):
        validate_id(waypoint_id)
        with closing(self._connect()) as conn:
            cur = conn.execute('DELETE FROM waypoints WHERE id = ?', (waypoint_id,))
        if cur.rowcount == 0:
            raise WaypointNotFound('Waypoint not found.')
