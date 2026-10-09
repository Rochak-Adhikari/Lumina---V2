"""Verify a read-only copy of a real legacy database, without printing its data."""
import argparse
from contextlib import closing
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lumina.memory import MemoryStore


def digest(db):
    rows=[list(row) for row in db.execute('SELECT * FROM memories ORDER BY id')]
    return len(rows),hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def verify(source):
    # The real database is opened read-only; all migrations run on this disposable copy.
    with tempfile.TemporaryDirectory(prefix='lumina-memory-migration-') as folder:
        copy=Path(folder)/'memory.sqlite3'
        with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as original:
            with closing(sqlite3.connect(copy)) as target:
                original.backup(target)
        with closing(sqlite3.connect(copy)) as original:
            before=digest(original)
            original_version=original.execute('PRAGMA user_version').fetchone()[0]
        memory=MemoryStore(copy)
        after=digest(memory.db)
        assert before==after,'Legacy rows changed during migration'
        assert memory.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not memory.db.execute('PRAGMA foreign_key_check').fetchall()
        backup=memory.repo.backup_path
        if original_version==0:
            assert backup and backup.is_file()
            with closing(sqlite3.connect(backup)) as restored:
                assert digest(restored)==before
                assert restored.execute('PRAGMA user_version').fetchone()[0]==original_version
        counts=memory.status()['counts']
        schema=memory.repo.schema_version
        memory.close()
        memory=MemoryStore(copy)
        assert digest(memory.db)==before
        assert memory.status()['counts']==counts,'Restart duplicated imported records'
        memory.close()
        return {'ok':True,'legacy_records':before[0],'legacy_rows_unchanged':True,
                'schema_version':schema,'backup_restore_verified':bool(backup),
                'restart_idempotent':True,'integrity':'ok','foreign_keys':'ok',
                'original_database_modified':False,'private_contents_exported':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    report=verify(args.source)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
