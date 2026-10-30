"""Explicit, one-way continuity transfer. No source migrations or cloud sync.

Manifest format::

    {"records": [{"table": "facts", "id": "exact-id",
                  "cloud_storage": True, "provider_access": False,
                  "allow_local_only": True}]}

Every dependency must also be explicitly selected and consented. There are no
wildcards or inherited permissions. ``allow_local_only`` defaults to false.
Bundle rows contain every SQLite column, including JSON columns as *strings*,
so timestamps, versions, and provenance survive byte-for-byte. Approve the
SHA-256 returned by ``bundle_digest`` after reviewing the complete bundle.
The caller owns authentication, review UI, transport, and durable file output.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sqlite3

from lumina.continuity.models import contains_secret
from lumina.continuity.policy import SECRET, SECRET_KEYS, now, text
from lumina.continuity.repository import Repository
from lumina.continuity.retrieval import bounded_pack

BUNDLE_VERSION = 1
SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 1000
MAX_RESULTS = 30
KINDS = {
    'entity': 'entities', 'event': 'events', 'fact': 'facts',
    'evidence': 'evidence', 'episode': 'episodes', 'decision': 'decisions',
    'goal': 'goals', 'commitment': 'commitments', 'open_loop': 'open_loops',
    'relationship': 'relationships', 'memory_candidate': 'memory_candidates',
    'prediction': 'predictions', 'behavior_pattern': 'behavior_patterns',
    'episode_event': 'episode_events',
}
TABLES = frozenset(KINDS.values())
BLOCKED = frozenset({'device_local', 'cloud_blocked', 'sensitive'})
SEARCH_FIELDS = {
    'facts': ('predicate', 'object_value'),
    'decisions': ('subject', 'chosen_option', 'reasoning', 'alternatives_json'),
    'goals': ('description',), 'commitments': ('description',),
    'open_loops': ('description', 'next_action'),
    'episodes': ('title', 'summary', 'outcome'),
    'predictions': ('prediction',), 'behavior_patterns': ('pattern',),
}


def _canonical(value):
    """Strict, bounded UTF-8 JSON; reject non-JSON and excessive nesting early."""
    nodes = 0

    def check(obj, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 20 or nodes > 200000:
            raise ValueError('Memory JSON exceeds its structural limit.')
        if type(obj) is dict:
            for key, item in obj.items():
                if type(key) is not str:
                    raise ValueError('Memory JSON keys must be strings.')
                check(key, depth + 1)
                check(item, depth + 1)
        elif type(obj) is list:
            for item in obj:
                check(item, depth + 1)
        elif type(obj) is str:
            if len(obj) > MAX_BUNDLE_BYTES or '\x00' in obj:
                raise ValueError('Memory text exceeds its limit or contains NUL.')
        elif obj is None or type(obj) is bool:
            pass
        elif type(obj) is int:
            if not -(2**63) <= obj < 2**63:
                raise ValueError('Memory integer is outside SQLite bounds.')
        elif type(obj) is float and math.isfinite(obj):
            pass
        else:
            raise ValueError('Memory data must be finite, plain JSON.')

    check(value)
    encoded = bytearray()
    try:
        for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False,
                                     sort_keys=True, separators=(',', ':')).iterencode(value):
            encoded.extend(part.encode('utf-8'))
            if len(encoded) > MAX_BUNDLE_BYTES:
                raise ValueError('Memory bundle exceeds its size limit.')
    except (UnicodeError, RecursionError):
        raise ValueError('Invalid memory JSON.') from None
    return bytes(encoded)


def bundle_digest(bundle: dict) -> str:
    """SHA-256 of canonical JSON, including the manifest and every raw column."""
    if type(bundle) is not dict:
        raise ValueError('A memory bundle must be an object.')
    return hashlib.sha256(_canonical(bundle)).hexdigest()


def _json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('Duplicate JSON field.')
            result[key] = item
        return result

    try:
        result = json.loads(value, object_pairs_hook=pairs)
        _canonical(result)
        return result
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Invalid JSON column in memory record.') from None


def _screen(value, depth=0):
    if depth > 20:
        raise ValueError('Memory data is too deeply nested.')
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEYS.fullmatch(key):
                raise ValueError('Credential-like memory cannot be transferred.')
            _screen(key, depth + 1)
            _screen(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _screen(item, depth + 1)
    elif isinstance(value, str):
        if contains_secret(value) or SECRET.search(value):
            raise ValueError('Credential-like memory cannot be transferred.')
        # Also inspect JSON embedded in ordinary text (including escaped keys).
        if value.lstrip().startswith(('{', '[')):
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                return
            _canonical(parsed)
            _screen(parsed, depth + 1)


def _manifest(manifest):
    _canonical(manifest)
    if type(manifest) is not dict or set(manifest) != {'records'}:
        raise ValueError('Manifest must contain only an explicit records list.')
    entries = manifest['records']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_RECORDS:
        raise ValueError('Manifest record count is outside its limit.')
    selected = {}
    required = {'table', 'id', 'cloud_storage', 'provider_access'}
    for entry in entries:
        if (type(entry) is not dict or not required <= entry.keys()
                or entry.keys() - (required | {'allow_local_only'})):
            raise ValueError('Invalid manifest record or consent fields.')
        if type(entry['table']) is not str or entry['table'] not in TABLES:
            raise ValueError('Table is not exportable.')
        text(entry['id'], 'record ID', 256)
        if (entry['cloud_storage'] is not True
                or type(entry['provider_access']) is not bool
                or type(entry.get('allow_local_only', False)) is not bool):
            raise ValueError('Explicit boolean storage and provider consent required.')
        key = (entry['table'], entry['id'])
        if key in selected:
            raise ValueError('Duplicate manifest record.')
        selected[key] = entry
    return selected


def _policy(row, consent):
    if 'privacy_class' not in row:  # episode_events inherits its dependencies.
        return
    if (row['privacy_class'] not in {'public', 'private', 'cloud_allowed'}
            or row['sync_policy'] not in {'local_only', 'cloud_allowed'}):
        raise ValueError('Memory privacy or sync policy forbids cloud storage.')
    if row['sync_policy'] == 'local_only' and not consent.get('allow_local_only', False):
        raise ValueError('Local-only memory requires explicit per-record consent.')


def _schema(db):
    return {table: list(db.execute(f'PRAGMA table_info({table})')) for table in TABLES}


def _reference_db():
    # Validate against the installed, trusted DDL in a disposable in-memory DB.
    # Never construct a Repository (even temporarily) for the source.
    db = sqlite3.connect(':memory:', isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        ddl = Path(__file__).parents[1] / 'continuity/migrations/001_initial.sql'
        db.executescript(ddl.read_text(encoding='utf-8'))
        db.execute('PRAGMA foreign_keys=ON')
        return db
    except BaseException:
        db.close()
        raise


def _dependencies(table, row, records, schema_db):
    deps = set()

    def require(target, identity):
        if identity is None:
            return
        if type(identity) is not str or not identity:
            raise ValueError('Invalid memory dependency.')
        if target is None:
            matches = [key for key in records if key[1] == identity
                       and key[0] not in {'evidence', 'episode_events', 'memory_candidates'}]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous explicitly selected dependency.')
            key = matches[0]
        else:
            key = (target, identity)
        if key not in records:
            raise ValueError('Missing explicitly selected memory dependency.')
        deps.add(key)

    for fk in schema_db.execute(f'PRAGMA foreign_key_list({table})'):
        require(fk['table'], row[fk['from']])
    if row.get('project_id') is not None:
        require('entities', row['project_id'])
        if records['entities', row['project_id']]['kind'] != 'project':
            raise ValueError('Memory project dependency is not a project.')
    if table == 'evidence':
        target = KINDS.get(row['record_type'])
        if target is None:
            raise ValueError('Unknown evidence record type.')
        require(target, row['record_id'])
    elif table == 'relationships':
        require(None, row['source_entity'])
        require(None, row['target_entity'])
    elif table == 'memory_candidates':
        proposal = _json(row['proposal_json'])
        if type(proposal) is not dict:
            raise ValueError('Candidate proposal must be an object.')
        require(KINDS.get(proposal.get('kind')), row['record_id'])
        require('facts', proposal.get('supersedes'))
        require('events', proposal.get('source_event_id'))
    elif table in {'predictions', 'behavior_patterns', 'open_loops'}:
        column, target = {
            'predictions': ('evidence_ids_json', 'evidence'),
            'behavior_patterns': ('supporting_events_json', 'events'),
            'open_loops': ('blocked_by_json', None),
        }[table]
        values = _json(row[column])
        if type(values) is not list:
            raise ValueError('Memory dependencies must be a list.')
        for identity in values:
            require(target, identity)
    elif table == 'decisions':
        assumptions = _json(row['assumptions_json'])
        if type(assumptions) is not list:
            raise ValueError('Decision assumptions must be a list.')
        for assumption in assumptions:
            if isinstance(assumption, dict):
                require('facts', assumption.get('fact_id'))
    elif table == 'events':
        payload = _json(row['payload_json'])
        if isinstance(payload, dict):
            if row['event_type'] == 'memory.corrected':
                for key in ('old_id', 'new_id'):
                    if not payload.get(key):
                        raise ValueError('Correction event requires both fact identities.')
                    require('facts', payload[key])
            elif row['event_type'].startswith('memory.'):
                require(KINDS.get(payload.get('kind')), payload.get('record_id'))
                require('memory_candidates', payload.get('candidate_id'))
            elif row['event_type'] == 'entity.registered':
                require('entities', payload.get('entity_id'))
    return deps


def _insert(db, table, row):
    columns = ','.join('"' + key + '"' for key in row)
    db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)})',
               tuple(row.values()))


def _validate(bundle, db):
    _canonical(bundle)
    expected = {'bundle_version', 'schema_version', 'manifest', 'manifest_sha256',
                'record_counts', 'records'}
    if type(bundle) is not dict or set(bundle) != expected:
        raise ValueError('Invalid memory bundle fields.')
    for key, version in (('bundle_version', BUNDLE_VERSION), ('schema_version', SCHEMA_VERSION)):
        if type(bundle[key]) is not int or bundle[key] != version:
            raise ValueError('Unsupported memory schema or bundle version.')
    selected = _manifest(bundle['manifest'])
    if bundle['manifest_sha256'] != bundle_digest(bundle['manifest']):
        raise ValueError('Manifest checksum mismatch.')
    grouped = bundle['records']
    if type(grouped) is not dict or grouped.keys() - TABLES:
        raise ValueError('Invalid bundle record tables.')
    schema = _schema(db)
    records = {}
    for table, rows in grouped.items():
        if type(rows) is not list or not rows or len(rows) > MAX_RECORDS:
            raise ValueError('Invalid bundle record count.')
        columns = {col['name']: col for col in schema[table]}
        for row in rows:
            if type(row) is not dict or row.keys() != columns.keys():
                raise ValueError('Record columns do not match the continuity schema.')
            text(row['id'], 'record ID', 256)
            key = (table, row['id'])
            if key not in selected or key in records:
                raise ValueError('Bundle records must exactly match the manifest.')
            for name, value in row.items():
                column = columns[name]
                if value is None:
                    if column['notnull']:
                        raise ValueError('Required memory column is null.')
                elif (column['type'] == 'TEXT' and type(value) is not str
                      or column['type'] == 'INTEGER' and type(value) is not int
                      or column['type'] == 'REAL' and type(value) not in (int, float)):
                    raise ValueError('Memory column has an invalid SQLite type.')
                if name.endswith('_json'):
                    _screen(_json(value))
            _screen(row)
            _policy(row, selected[key])
            records[key] = row
    counts = dict(Counter(table for table, _ in records))
    if (records.keys() != selected.keys() or type(bundle['record_counts']) is not dict
            or any(type(n) is not int for n in bundle['record_counts'].values())
            or bundle['record_counts'] != counts):
        raise ValueError('Bundle records or counts do not match the manifest.')
    for (table, _), row in records.items():
        _dependencies(table, row, records, db)
    # DDL enforces CHECKs and unique constraints as well as every real FK.
    db.execute('BEGIN')
    db.execute('PRAGMA defer_foreign_keys=ON')
    try:
        for (table, _), row in records.items():
            _insert(db, table, row)
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Missing memory foreign-key dependency.')
    except sqlite3.Error:
        raise ValueError('Memory records violate the continuity schema.') from None
    finally:
        db.execute('ROLLBACK')
    return selected, records


def _check_source_links(db, records):
    # A current belief without its correction chain would misrepresent history.
    for (table, identity), row in records.items():
        if table == 'facts':
            links = db.execute("SELECT id FROM relationships WHERE relationship_type='SUPERSEDES' "
                               'AND (source_entity=? OR target_entity=?) LIMIT ?',
                               (identity, identity, MAX_RECORDS + 1))
            if any(('relationships', link['id']) not in records for link in links):
                raise ValueError('Correction chain requires explicit selection of all its records.')
        if table != 'events':
            continue
        # Match the service's source-taint policy without loading dependent text.
        for target in TABLES - {'episode_events'}:
            kind = next(k for k, t in KINDS.items() if t == target)
            restricted = db.execute(
                f'SELECT 1 FROM evidence e JOIN {target} r ON r.id=e.record_id '
                "WHERE e.event_id=? AND e.record_type=? AND (r.privacy_class IN "
                "('device_local','cloud_blocked','sensitive') OR r.sync_policy IN "
                "('device_local','cloud_blocked','sensitive')) LIMIT 1", (identity, kind)).fetchone()
            if restricted:
                raise ValueError('Source event is linked to cloud-blocked memory.')
        restricted = db.execute(
            'SELECT 1 FROM memory_candidates WHERE source_event_id=? AND '
            "(privacy_class IN ('device_local','cloud_blocked','sensitive') OR "
            "sync_policy IN ('device_local','cloud_blocked','sensitive')) LIMIT 1", (identity,)).fetchone()
        if restricted:
            raise ValueError('Source event is linked to cloud-blocked memory.')


def export_bundle(source: Path, manifest: dict) -> dict:
    """Read a consistent SQLite snapshot without source migrations or writes."""
    manifest = json.loads(_canonical(manifest))
    selected = _manifest(manifest)
    source = Path(source).resolve()
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                raise ValueError('Unsupported source continuity schema version.')
            records = {}
            size = 0
            paths = {str(source).casefold(), source.as_posix().casefold(), source.as_uri().casefold()}
            for table, identity in sorted(selected):
                row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
                if row is None:
                    raise ValueError('An explicitly selected memory record is missing.')
                row = dict(row)
                raw = _canonical(row)
                size += len(raw)
                if size > MAX_BUNDLE_BYTES:
                    raise ValueError('Memory bundle exceeds its size limit.')
                # Never redact approved data silently: reject source-path content.
                values = [str(v).casefold().replace('\\\\', '\\') for v in row.values()]
                if any(path in value for path in paths for value in values):
                    raise ValueError('A selected record discloses the source database path.')
                records.setdefault(table, []).append(row)
            manifest['records'] = [selected[key] for key in sorted(selected)]
            bundle = dict(bundle_version=BUNDLE_VERSION, schema_version=SCHEMA_VERSION,
                          manifest=manifest, manifest_sha256=bundle_digest(manifest),
                          record_counts={table: len(rows) for table, rows in records.items()}, records=records)
            with closing(_reference_db()) as reference:
                _, flat = _validate(bundle, reference)
            _check_source_links(db, flat)
            return bundle
    except sqlite3.Error:
        raise ValueError('Cannot read a compatible continuity source database.') from None


def init_memory_tables(repo: Repository) -> None:
    """Create only cloud memory audit/grant tables in the supplied repository."""
    with repo.transaction():
        repo.db.execute('''CREATE TABLE IF NOT EXISTS cloud_memory_imports (
            bundle_sha256 TEXT PRIMARY KEY NOT NULL,
            schema_version INTEGER NOT NULL, manifest_sha256 TEXT NOT NULL,
            manifest_json TEXT NOT NULL, record_counts_json TEXT NOT NULL,
            imported_at TEXT NOT NULL)''')
        repo.db.execute('''CREATE TABLE IF NOT EXISTS cloud_memory_grants (
            table_name TEXT NOT NULL, record_id TEXT NOT NULL,
            record_sha256 TEXT NOT NULL, bundle_sha256 TEXT NOT NULL
                REFERENCES cloud_memory_imports(bundle_sha256),
            cloud_storage INTEGER NOT NULL CHECK(cloud_storage IN (0,1)),
            provider_access INTEGER NOT NULL CHECK(provider_access IN (0,1)),
            allow_local_only INTEGER NOT NULL CHECK(allow_local_only IN (0,1)),
            PRIMARY KEY(table_name, record_id))''')


def _import_order(records, db):
    # Only physical FKs constrain INSERT order. Semantic evidence edges cycle.
    pending = dict(records)
    emitted = set()
    while pending:
        ready = []
        for key, row in pending.items():
            dependencies = {(fk['table'], row[fk['from']])
                            for fk in db.execute(f'PRAGMA foreign_key_list({key[0]})')
                            if row[fk['from']] is not None}
            if dependencies - {key} <= emitted:
                ready.append(key)
        if not ready:
            raise ValueError('Cyclic SQL foreign keys cannot be imported.')
        for key in ready:
            yield key, pending.pop(key)
            emitted.add(key)


def import_bundle(repo: Repository, bundle: dict, approved_sha256: str) -> dict:
    """Atomically import the exact approved content; never update existing rows."""
    encoded = _canonical(bundle)
    digest = hashlib.sha256(encoded).hexdigest()
    if (type(approved_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', approved_sha256)
            or not hmac.compare_digest(digest, approved_sha256)):
        raise ValueError('Exact bundle SHA-256 approval is required.')
    bundle = json.loads(encoded)  # Detach caller mutations from approved bytes.
    with closing(_reference_db()) as reference:
        selected, records = _validate(bundle, reference)
        reference_schema = _schema(reference)
    try:
        with repo.transaction():
            if (repo.schema_version != bundle['schema_version']
                    or repo.db.execute('PRAGMA user_version').fetchone()[0] != bundle['schema_version']):
                raise ValueError('Bundle schema version does not match the repository.')
            for table in bundle['records']:
                actual = [tuple(c) for c in repo.db.execute(f'PRAGMA table_info({table})')]
                if actual != [tuple(c) for c in reference_schema[table]]:
                    raise ValueError('Destination columns do not match the continuity schema.')
            init_memory_tables(repo)
            previous = repo.db.execute('SELECT 1 FROM cloud_memory_imports WHERE bundle_sha256=?',
                                       (digest,)).fetchone()
            missing = set()
            for (table, identity), row in records.items():
                old = repo.db.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
                if old is None:
                    missing.add((table, identity))
                elif _canonical(dict(old)) != _canonical(row):
                    raise ValueError('Memory identity conflicts with existing data; import rejected.')
            if previous and missing:
                raise ValueError('Previously imported memory is missing; reimport cannot resurrect it.')
            if not previous:
                for (table, identity), row in _import_order(records, repo.db):
                    if (table, identity) in missing:
                        _insert(repo.db, table, row)
                    if table in SEARCH_FIELDS:
                        content = ' '.join(str(row.get(k) or '') for k in SEARCH_FIELDS[table]).replace('_', ' ')
                        if table == 'facts':
                            content = records['entities', row['subject_entity_id']]['name'] + ' ' + content
                        kind = next(k for k, t in KINDS.items() if t == table)
                        repo.refresh_index(kind, identity, content)
                repo.db.execute('INSERT INTO cloud_memory_imports VALUES(?,?,?,?,?,?)',
                                (digest, SCHEMA_VERSION, bundle['manifest_sha256'],
                                 _canonical(bundle['manifest']).decode(),
                                 _canonical(bundle['record_counts']).decode(), now()))
                for key, row in records.items():
                    consent = selected[key]
                    repo.db.execute('''INSERT INTO cloud_memory_grants VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(table_name,record_id) DO UPDATE SET
                        record_sha256=excluded.record_sha256, bundle_sha256=excluded.bundle_sha256,
                        cloud_storage=excluded.cloud_storage, provider_access=excluded.provider_access,
                        allow_local_only=excluded.allow_local_only''',
                        (*key, bundle_digest(row), digest, 1, int(consent['provider_access']),
                         int(consent.get('allow_local_only', False))))
            return {'ok': True, 'sha256': digest, 'already_imported': bool(previous),
                    'imported': len(missing), 'record_counts': bundle['record_counts']}
    except sqlite3.Error:
        raise ValueError('Memory import conflicts with repository constraints; import rolled back.') from None


def approved_memory(repo: Repository, query: str, limit: int = 10, *, for_provider: bool = False) -> list:
    """Bounded lexical recall of unchanged, explicitly approved imported records.

    Evidence is independently consent-filtered. No unapproved adjacent records
    are expanded. The regular RetrievalService requires a MemoryService and
    expands private neighbors, so reuse its packing policy and FTS escaping here.
    """
    query = text(query, 'query', 2048, empty=True)
    if type(limit) is not int or type(for_provider) is not bool:
        raise ValueError('Recall limit and provider flag have invalid types.')
    limit = max(0, min(limit, MAX_RESULTS))
    if not limit:
        return []
    terms = re.findall(r'[^\W_]+', query.casefold())[:24]
    match = ' OR '.join('"' + term.replace('"', '""') + '"' for term in terms)
    with repo.lock:
        if not repo.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cloud_memory_grants'").fetchone():
            return []
        cache = {}

        def approved(table, identity):
            key = (table, identity)
            if key in cache:
                return cache[key]
            cache[key] = None
            grant = repo.db.execute('SELECT * FROM cloud_memory_grants WHERE table_name=? AND record_id=?', key).fetchone()
            if not grant or not grant['cloud_storage'] or for_provider and not grant['provider_access']:
                return None
            raw = repo.db.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
            if raw is None or bundle_digest(dict(raw)) != grant['record_sha256']:
                return None  # A grant approves content, not future edits under the same ID.
            row = dict(raw)
            try:
                _policy(row, dict(grant))
                _screen(row)
            except ValueError:
                return None
            cache[key] = Repository._decode(raw)
            return cache[key]

        candidates = []
        instant = now()
        for table, fields in SEARCH_FIELDS.items():
            clauses = ['g.table_name=?', 'g.cloud_storage=1']
            params = [table]
            if for_provider:
                clauses.append('g.provider_access=1')
            clauses.append("r.privacy_class IN ('public','private','cloud_allowed')")
            clauses.append("(r.sync_policy='cloud_allowed' OR (r.sync_policy='local_only' AND g.allow_local_only=1))")
            if table == 'facts':
                clauses.extend(["r.status IN ('active','disputed')", 'r.valid_from<=?',
                                '(r.valid_until IS NULL OR r.valid_until>?)'])
                params.extend([instant, instant])
            elif table in {'decisions', 'goals', 'commitments', 'open_loops'}:
                clauses.append("r.status IN ('active','open','blocked','pending','needs_review')")
            base = f'SELECT r.id FROM {table} r JOIN cloud_memory_grants g ON g.record_id=r.id WHERE '
            filters = ' AND '.join(clauses)
            order = ' ORDER BY r.updated_at DESC,r.id LIMIT 120'
            try:
                search = (' AND r.id IN (SELECT record_id FROM memory_fts WHERE memory_fts MATCH ? AND kind=?)'
                          if match else '')
                kind = next(k for k, t in KINDS.items() if t == table)
                rows = repo.db.execute(base + filters + search + order,
                                       (*params, match, kind) if match else params).fetchall()
            except sqlite3.OperationalError:
                # FTS-less deployments still have bounded, literal SQL recall.
                expression = " || ' ' || ".join(f"coalesce(r.{field},'')" for field in fields)
                search = ' AND (' + ' OR '.join(f'instr(lower({expression}),?)>0' for _ in terms) + ')' if terms else ''
                rows = repo.db.execute(base + filters + search + order, (*params, *terms)).fetchall()
            for hit in rows:
                row = approved(table, hit['id'])
                if not row:
                    continue
                entity_ids = [row.get(k) for k in ('subject_entity_id', 'object_entity_id', 'project_id', 'owner_entity_id')]
                if any(identity and not approved('entities', identity) for identity in entity_ids):
                    continue
                evidence = []
                links = repo.db.execute('''SELECT e.id FROM evidence e
                    JOIN cloud_memory_grants g ON g.table_name='evidence' AND g.record_id=e.id
                    WHERE e.record_type=? AND e.record_id=? AND g.cloud_storage=1
                    AND (?=0 OR g.provider_access=1) ORDER BY e.observed_at DESC LIMIT 12''',
                    (kind, row['id'], int(for_provider))).fetchall()
                for link in links:
                    item = approved('evidence', link['id'])
                    if item and (not item['event_id'] or approved('events', item['event_id'])):
                        evidence.append(item)
                if not evidence:
                    continue
                content = ' '.join(str(row.get(f) or '') for f in fields).casefold().replace('_', ' ')
                rank = sum(term in content for term in terms)
                candidates.append({'id': row['id'], 'kind': kind, 'record': row,
                                   'evidence': evidence[:6], 'rank': rank})
        candidates.sort(key=lambda item: (-item['rank'], item['id']))
        return bounded_pack({'items': candidates[:limit]}, 24000, ['items']).get('items', [])
