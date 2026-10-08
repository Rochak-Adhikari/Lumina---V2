"""Small private SQLite memory store with explicit write and deletion authority."""
from pathlib import Path
import os
import secrets
import sqlite3
import time

CATEGORIES = {'working', 'episodic', 'semantic', 'procedural', 'preference', 'project', 'journal'}


class MemoryStore:
    def __init__(self, path=None):
        if path in (None, ''):
            base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'LUMINA'
            path = base / 'memory.sqlite3'
        self.path = Path(path)
        if str(self.path) != ':memory:':
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY, category TEXT NOT NULL, text TEXT NOT NULL,
            created REAL NOT NULL, updated REAL NOT NULL, deleted REAL)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS memories_category ON memories(category)')
        self.db.commit()
        self.pending = {}

    @staticmethod
    def _text(text):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError('Memory text must contain 1–12000 characters.')
        return text.strip()

    @staticmethod
    def _category(category):
        if category not in CATEGORIES:
            raise ValueError('That memory category is unavailable.')
        return category

    def remember(self, text, category='working', *, authorized=False):
        if authorized is not True:
            raise PermissionError('Saving memory requires your instruction.')
        text, category = self._text(text), self._category(category)
        now = time.time()
        cur = self.db.execute('INSERT INTO memories(category,text,created,updated) VALUES(?,?,?,?)', (category,text,now,now))
        self.db.commit()
        return {'ok': True, 'id': cur.lastrowid, 'category': category}

    def search(self, query, *, include_journal=False, limit=20):
        query = self._text(query)
        limit = max(1, min(int(limit), 50))
        clauses = ['deleted IS NULL', 'text LIKE ?']
        params = [f'%{query}%']
        if not include_journal:
            clauses.append("category <> 'journal'")
        rows = self.db.execute(f"SELECT id,category,text,created,updated FROM memories WHERE {' AND '.join(clauses)} ORDER BY updated DESC LIMIT ?", (*params, limit + 1)).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        return {'ok': True, 'count': len(rows), 'total': len(rows), 'truncated': truncated,
                'matches': [dict(row) for row in rows]}

    def request_delete(self, memory_id):
        try: memory_id = int(memory_id)
        except (TypeError, ValueError): raise ValueError('That memory identifier is invalid.') from None
        row = self.db.execute('SELECT id,category,text FROM memories WHERE id=? AND deleted IS NULL', (memory_id,)).fetchone()
        if row is None: return {'ok': False, 'error': 'That memory is unavailable.'}
        token = secrets.token_urlsafe(24)
        self.pending[token] = {'id': memory_id, 'expires': time.monotonic() + 60}
        return {'ok': False, 'confirmation_required': True, 'confirmation_id': token,
                'id': memory_id, 'category': row['category'], 'message': 'This will remove the selected memory. Confirm before proceeding.'}

    def confirm_delete(self, token, *, authorized=False):
        if authorized is not True: raise PermissionError('Deleting memory requires your instruction.')
        pending = self.pending.pop(token, None)
        if pending is None or time.monotonic() > pending['expires']:
            return {'ok': False, 'error': 'That confirmation is no longer valid.'}
        now = time.time();self.db.execute('UPDATE memories SET deleted=?,updated=? WHERE id=? AND deleted IS NULL',(now,now,pending['id']));self.db.commit()
        return {'ok': True, 'id': pending['id'], 'message': 'The memory was removed.'}

    def restore(self, memory_id, *, authorized=False):
        if authorized is not True: raise PermissionError('Restoring memory requires your instruction.')
        self.db.execute('UPDATE memories SET deleted=NULL,updated=? WHERE id=?',(time.time(),int(memory_id)));self.db.commit()
        return {'ok': True, 'id': int(memory_id)}

    def close(self): self.db.close()
