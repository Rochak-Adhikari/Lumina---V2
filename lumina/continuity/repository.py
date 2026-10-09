"""Serialized SQLite persistence, reversible expansion and stable legacy mapping."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4, uuid5, NAMESPACE_URL
from .models import contains_secret
from .policy import now

CANONICAL = {'entities','events','facts','evidence','episodes','decisions','goals','commitments',
             'open_loops','relationships','memory_candidates','predictions','behavior_patterns'}
WRITABLE = CANONICAL | {'current_state','episode_events','legacy_memory_map','meta'}


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.backup_path = None
        self._depth = 0
        if str(path) != ':memory:':
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=2, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute('PRAGMA busy_timeout=2000')
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA secure_delete=ON')
            self._migrate()
            self.columns = {t:{r['name'] for r in self.db.execute(f'PRAGMA table_info({t})')} for t in WRITABLE}
            self.import_legacy()
        except BaseException:
            self.db.close()
            raise

    def _migrate(self):
        migrations = sorted((Path(__file__).parent/'migrations').glob('[0-9]*.sql'))
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        target = max(int(p.name.split('_')[0]) for p in migrations)
        if version > target:
            raise ValueError('Memory was created by a newer application version.')
        if version < target and str(self.path) != ':memory:' and self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
            self.backup_path = self.path.with_name(self.path.name+'.before-continuity-'+uuid4().hex+'.backup')
            with closing(sqlite3.connect(str(self.backup_path))) as backup:
                self.db.backup(backup)
        with self.transaction():
            # Another process may have upgraded while this connection backed up.
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            self.db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
            for migration in migrations:
                number = int(migration.name.split('_')[0])
                if number <= version:
                    continue
                statement = ''
                for line in migration.read_text('utf-8').splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        self.db.execute(statement)
                        statement = ''
                if statement.strip() and not statement.strip().startswith('--'):
                    raise ValueError('Incomplete memory migration.')
                self.db.execute('INSERT INTO schema_migrations VALUES(?,?)', (number,now()))
                self.db.execute(f'PRAGMA user_version={number}')
            self.schema_version = self.db.execute('PRAGMA user_version').fetchone()[0]

    @contextmanager
    def transaction(self):
        with self.lock:
            outer = self._depth == 0
            save = 'memory_'+str(self._depth)
            self.db.execute('BEGIN IMMEDIATE' if outer else 'SAVEPOINT '+save)
            self._depth += 1
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK' if outer else 'ROLLBACK TO '+save)
                if not outer:
                    self.db.execute('RELEASE '+save)
                raise
            else:
                self.db.execute('COMMIT' if outer else 'RELEASE '+save)
            finally:
                self._depth -= 1

    @staticmethod
    def _decode(row):
        result = dict(row)
        for key, value in list(result.items()):
            if key.endswith('_json') and isinstance(value, str):
                result[key] = json.loads(value)
        return result

    def rows(self, sql, params=()):
        with self.lock:
            return [self._decode(row) for row in self.db.execute(sql, params).fetchall()]

    def _check(self, table, values):
        if table not in WRITABLE or set(values)-self.columns[table]:
            raise ValueError('Invalid repository fields.')

    def insert(self, table, values):
        values = dict(values)
        self._check(table, values)
        if 'id' in self.columns[table]:
            values.setdefault('id', str(uuid4()))
        for key in ('created_at','updated_at'):
            if key in self.columns[table]:
                values.setdefault(key, now())
        encoded = {k:json.dumps(v,ensure_ascii=False,allow_nan=False) if k.endswith('_json') and v is not None else v for k,v in values.items()}
        with self.transaction():
            keys = ','.join(encoded)
            self.db.execute(f"INSERT INTO {table}({keys}) VALUES({','.join('?' for _ in encoded)})", tuple(encoded.values()))
        return values.get('id')

    def update(self, table, identity, values):
        if table == 'events':
            raise ValueError('Events are immutable; append a correction event instead.')
        values = dict(values)
        self._check(table, values)
        if set(values)&{'id','created_at','version'}:
            raise ValueError('Immutable identity fields cannot change.')
        with self.transaction():
            old = self.get(table, identity)
            if old is None:
                raise ValueError('Record unavailable.')
            if 'updated_at' in self.columns[table]:
                values['updated_at'] = now()
            if 'version' in self.columns[table]:
                values['version'] = old['version']+1
            encoded = {k:json.dumps(v,ensure_ascii=False,allow_nan=False) if k.endswith('_json') and v is not None else v for k,v in values.items()}
            self.db.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in encoded)} WHERE id=?", (*encoded.values(),identity))
            return self.get(table, identity)

    def get(self, table, identity):
        if table not in WRITABLE or 'id' not in self.columns[table]:
            raise ValueError('Invalid record table.')
        rows = self.rows(f'SELECT * FROM {table} WHERE id=?', (identity,))
        return rows[0] if rows else None

    def refresh_index(self, kind, identity, content):
        with self.transaction():
            self.db.execute('DELETE FROM memory_fts WHERE record_id=?', (identity,))
            self.db.execute('INSERT INTO memory_fts(record_id,kind,content) VALUES(?,?,?)', (identity,kind,content))

    def remove_index(self, identity):
        with self.transaction():
            self.db.execute('DELETE FROM memory_fts WHERE record_id=?', (identity,))

    def import_legacy(self):
        """Idempotent mapping; original rows remain byte-for-byte unchanged."""
        with self.transaction():
            user = self.rows('SELECT id FROM entities WHERE canonical_key=?', ('local-user',))
            user_id = user[0]['id'] if user else self.insert('entities',dict(kind='user',name='User',canonical_key='local-user'))
            if not user:
                ev=self.insert('events',dict(event_type='entity.registered',source_type='runtime',source_id=user_id,payload_json={'entity_id':user_id,'kind':'user'}))
                self.insert('evidence',dict(record_type='entity',record_id=user_id,event_id=ev,source_type='runtime',source_id=user_id,
                    extraction_method='registry',confidence=1,source_fingerprint=hashlib.sha256(user_id.encode()).hexdigest()))
            excluded = 0
            for row in self.rows('SELECT m.* FROM memories m LEFT JOIN legacy_memory_map l ON l.legacy_id=m.id WHERE l.legacy_id IS NULL'):
                identity = str(uuid5(NAMESPACE_URL, 'lumina-legacy-note:'+str(row['id'])))
                if contains_secret(row['text']):
                    excluded += 1
                    self.db.execute('INSERT INTO legacy_memory_map VALUES(?,?)', (row['id'],identity))
                    continue
                observed = datetime.fromtimestamp(row['created'],timezone.utc).isoformat(timespec='microseconds')
                ended = datetime.fromtimestamp(row['deleted'],timezone.utc).isoformat(timespec='microseconds') if row['deleted'] else None
                privacy = 'sensitive' if row['category']=='journal' else 'private'
                event = self.insert('events',dict(event_type='legacy.imported',timestamp=observed,source_type='legacy',source_id=str(row['id']),payload_json={'legacy_id':row['id'],'category':row['category']},privacy_class=privacy))
                self.insert('facts',dict(id=identity,subject_entity_id=user_id,predicate='legacy_note:'+str(row['id']),object_value=row['text'],confidence=.55,stability=.5,valid_from=observed,valid_until=ended,status='invalidated' if ended else 'active',source_type='legacy',privacy_class=privacy))
                self.insert('evidence',dict(record_type='fact',record_id=identity,event_id=event,source_type='legacy',source_id=str(row['id']),observed_at=observed,extraction_method='legacy_import',confidence=.55,source_fingerprint=hashlib.sha256(('legacy\0'+str(row['id'])).encode()).hexdigest(),privacy_class=privacy))
                self.db.execute('INSERT INTO legacy_memory_map VALUES(?,?)', (row['id'],identity))
                self.refresh_index('fact',identity,row['text'])
            if excluded:
                previous=self.rows("SELECT value FROM meta WHERE key='legacy_excluded'")
                self.db.execute("INSERT OR REPLACE INTO meta VALUES('legacy_excluded',?)",(str(excluded+int(previous[0]['value'] if previous else 0)),))

    def close(self):
        with self.lock:
            self.db.close()
