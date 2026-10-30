"""Durable persistence, cryptographic verification, and atomic backup/restore for LUMINA Continuity.

Supports hot SQLite backups, evidence integrity verification, and FTS5 index reconstruction.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Dict, Optional


def compute_sha256(path: Path | str) -> str:
    """Compute SHA-256 digest of a file in bounded chunks."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Inspect counts of core memory and continuity tables."""
    tables = [
        'entities', 'events', 'facts', 'evidence', 'episodes',
        'decisions', 'goals', 'commitments', 'open_loops',
        'relationships', 'memory_candidates', 'memory_fts',
        'memory_suppressions'
    ]
    counts = {}
    for t in tables:
        try:
            row = conn.execute(f"SELECT count(*) FROM {t}").fetchone()
            counts[t] = row[0] if row else 0
        except sqlite3.OperationalError:
            counts[t] = 0
    return counts


def create_backup(
    source_db_path: Path | str,
    backup_dir: Optional[Path | str] = None,
    *,
    verify: bool = True
) -> Dict[str, Any]:
    """Create an atomic, verified backup of a live continuity database.

    Uses SQLite online backup API to ensure a clean transaction snapshot
    even if the database is in WAL mode and has active read connections.
    """
    src = Path(source_db_path).resolve()
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"Source continuity database not found at {src}")

    if backup_dir is None:
        target_dir = src.parent / 'backups'
    else:
        target_dir = Path(backup_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{src.stem}_backup_{timestamp_str}.sqlite3"
    backup_path = target_dir / backup_name
    manifest_path = target_dir / f"{backup_name}.manifest.json"

    # Online backup ensures WAL pages are committed and clean in destination
    src_conn = sqlite3.connect(str(src), timeout=10.0)
    dst_conn = sqlite3.connect(str(backup_path), timeout=10.0)
    try:
        # Checkpoint WAL if possible before copy
        try:
            src_conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.OperationalError:
            pass

        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()

    checksum = compute_sha256(backup_path)
    file_size = backup_path.stat().st_size

    counts = {}
    integrity_status = "unverified"
    if verify:
        verify_conn = sqlite3.connect(str(backup_path))
        try:
            row = verify_conn.execute("PRAGMA integrity_check").fetchone()
            integrity_status = row[0] if row else "failed"
            if integrity_status.lower() != "ok":
                raise ValueError(f"Backup failed SQLite integrity check: {integrity_status}")
            counts = get_table_counts(verify_conn)
        finally:
            verify_conn.close()

    manifest = {
        'version': 1,
        'backup_file': backup_name,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_path': str(src),
        'sha256': checksum,
        'file_size_bytes': file_size,
        'integrity_status': integrity_status,
        'table_counts': counts
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    return {
        'ok': True,
        'backup_path': str(backup_path),
        'manifest_path': str(manifest_path),
        'sha256': checksum,
        'file_size': file_size,
        'integrity': integrity_status,
        'counts': counts
    }


def verify_backup(
    backup_path: Path | str,
    manifest_path: Optional[Path | str] = None
) -> Dict[str, Any]:
    """Verify cryptographic integrity, schema, evidence linkages, and FTS tables."""
    bak = Path(backup_path).resolve()
    if not bak.exists():
        return {'ok': False, 'error': f"Backup file not found at {bak}"}

    current_sha256 = compute_sha256(bak)

    # Check manifest if present
    expected_sha256 = None
    if manifest_path:
        mf = Path(manifest_path).resolve()
        if mf.exists():
            data = json.loads(mf.read_text(encoding='utf-8'))
            expected_sha256 = data.get('sha256')
    else:
        auto_mf = bak.with_name(f"{bak.name}.manifest.json")
        if auto_mf.exists():
            data = json.loads(auto_mf.read_text(encoding='utf-8'))
            expected_sha256 = data.get('sha256')

    if expected_sha256 and expected_sha256.lower() != current_sha256.lower():
        return {
            'ok': False,
            'error': f"SHA256 mismatch! Expected {expected_sha256}, got {current_sha256}",
            'sha256_match': False
        }

    conn = sqlite3.connect(str(bak))
    try:
        check = conn.execute("PRAGMA integrity_check").fetchone()
        status = check[0] if check else "unknown"
        if status.lower() != 'ok':
            return {'ok': False, 'error': f"PRAGMA integrity_check returned: {status}"}

        counts = get_table_counts(conn)

        # Check evidence consistency: every evidence record must point to a real event
        orphaned_evidence = conn.execute(
            "SELECT count(*) FROM evidence WHERE event_id NOT IN (SELECT id FROM events)"
        ).fetchone()[0]

        # Check FTS index viability
        fts_count = 0
        try:
            fts_count = conn.execute("SELECT count(*) FROM memory_fts").fetchone()[0]
        except sqlite3.OperationalError:
            pass

        return {
            'ok': True,
            'sha256': current_sha256,
            'sha256_verified': bool(expected_sha256),
            'integrity': status,
            'counts': counts,
            'orphaned_evidence': orphaned_evidence,
            'fts_records': fts_count,
            'evidence_healthy': (orphaned_evidence == 0)
        }
    finally:
        conn.close()


def restore_backup(
    backup_path: Path | str,
    target_path: Path | str,
    *,
    overwrite: bool = False,
    rebuild_indexes: bool = True,
    safety_backup: bool = True
) -> Dict[str, Any]:
    """Restore a continuity database from a verified backup.

    Creates an automatic rollback snapshot if target exists, restores atomically,
    and rebuilds the FTS5 search index to ensure complete search consistency.
    """
    bak = Path(backup_path).resolve()
    target = Path(target_path).resolve()

    # Pre-verification
    ver = verify_backup(bak)
    if not ver.get('ok'):
        return {'ok': False, 'error': f"Cannot restore invalid backup: {ver.get('error')}"}

    safety_path = None
    if target.exists():
        if not overwrite:
            return {'ok': False, 'error': f"Target file already exists: {target}. Set overwrite=True to replace."}
        if safety_backup:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safety_path = target.parent / f"{target.stem}_pre_restore_{ts}.bak"
            try:
                # Use online backup for safe copy if it's a valid SQLite file
                with closing(sqlite3.connect(str(target))) as s_conn, closing(sqlite3.connect(str(safety_path))) as d_conn:
                    s_conn.backup(d_conn)
            except Exception:
                shutil.copy2(target, safety_path)

    target.parent.mkdir(parents=True, exist_ok=True)

    # Perform restoration using SQLite backup API to write clean database file
    with closing(sqlite3.connect(str(bak))) as b_conn, closing(sqlite3.connect(str(target))) as t_conn:
        b_conn.backup(t_conn)
        t_conn.commit()

    rebuilt = False
    if rebuild_indexes:
        with closing(sqlite3.connect(str(target))) as conn:
            try:
                conn.execute("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
                conn.commit()
                rebuilt = True
            except sqlite3.OperationalError:
                pass

    post_ver = verify_backup(target)
    return {
        'ok': post_ver.get('ok', False),
        'target_path': str(target),
        'source_backup': str(bak),
        'safety_backup_path': str(safety_path) if safety_path else None,
        'rebuilt_indexes': rebuilt,
        'counts': post_ver.get('counts', {}),
        'integrity': post_ver.get('integrity')
    }
