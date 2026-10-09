"""Explicit local bootstrap entry point. Back up the existing DB before opening it."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import quote

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lumina.continuity.bootstrap import SeedImporter, load_plan
from lumina.continuity.graph import MemoryGraphProjection
from lumina.memory import MemoryStore


def backup_database(database, directory):
    database=Path(database).resolve();directory=Path(directory).resolve()
    directory.mkdir(parents=True,exist_ok=True)
    if not database.exists():return None
    target=directory/('before-seed-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.sqlite3')
    target.touch(exist_ok=False)
    # file://localhost/share is treated as a local URI authority by SQLite,
    # losing the UNC server component. Keep the UNC path in the URI path.
    uri = ('file://'+quote(database.as_posix(), safe='/') if str(database).startswith('\\\\')
           else database.as_uri()) + '?mode=ro'
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('Memory backup timed out; no seed was imported. Run maintenance in the same Windows user context as LUMINA.')
    with closing(sqlite3.connect(uri,uri=True)) as source, closing(sqlite3.connect(target)) as destination:
        source.backup(destination, pages=256, progress=progress, sleep=.1)
        if destination.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed.')
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',required=True);parser.add_argument('--plan',required=True)
    parser.add_argument('--database',required=True);parser.add_argument('--workspace',required=True)
    parser.add_argument('--workspace-alias',action='append',default=[])
    parser.add_argument('--backup-dir',required=True);parser.add_argument('--report',required=True)
    parser.add_argument('--apply-reviewed',action='store_true',required=True)
    args=parser.parse_args()
    load_plan(args.seed,args.plan)  # Reject a stale/unsafe plan before even opening the DB.
    report_path=Path(args.report)
    if report_path.exists():raise ValueError('Choose a fresh report path; audit files are never silently overwritten.')
    backup=backup_database(args.database,args.backup_dir)
    memory=MemoryStore(args.database)
    try:
        result=SeedImporter(memory).run(args.seed,args.plan,workspace=args.workspace,
            workspace_aliases=args.workspace_alias,authorized=True)
        projection=MemoryGraphProjection(memory);graph=projection.read()
        result={**result,'backup':str(backup) if backup else None,'graph_counts':graph['counts'],
                'graph_consistency':projection.consistency_check(graph),'database':str(Path(args.database).resolve())}
        report_path.parent.mkdir(parents=True,exist_ok=True)
        with report_path.open('x',encoding='utf-8') as output:json.dump(result,output,ensure_ascii=False,indent=2)
        print(json.dumps({k:result.get(k) for k in ('already_imported','proposed','admitted','deduplicated','requires_review','counts','graph_counts','backup')}))
    finally:memory.close()


if __name__=='__main__':main()
