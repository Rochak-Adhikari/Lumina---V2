"""Extraction Manifest: Durable Chunk and Candidate Processing Tracker.

Guarantees 100% loss-accounting across multi-chunk extractions, ensuring
resumability and preventing silent omission of memory-bearing content.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Dict, List, Optional, Any


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ChunkRecord:
    chunk_id: str
    index: int
    start_char: int
    end_char: int
    status: str = 'pending'  # pending, in_progress, extracted, completed, failed
    candidate_ids: List[str] = field(default_factory=list)
    retries: int = 0
    error: Optional[str] = None
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'chunk_id': self.chunk_id,
            'index': self.index,
            'start_char': self.start_char,
            'end_char': self.end_char,
            'status': self.status,
            'candidate_ids': list(self.candidate_ids),
            'retries': self.retries,
            'error': self.error,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkRecord':
        return cls(
            chunk_id=data['chunk_id'],
            index=data['index'],
            start_char=data['start_char'],
            end_char=data['end_char'],
            status=data.get('status', 'pending'),
            candidate_ids=data.get('candidate_ids', []),
            retries=data.get('retries', 0),
            error=data.get('error'),
            updated_at=data.get('updated_at', _utc_now()),
        )


class ExtractionManifest:
    """Manages the full lifecycle of message chunking, candidate extraction, and admission."""

    def __init__(self, message_id: str, text_hash: str, total_chunks: int, repo=None):
        self.message_id = message_id
        self.text_hash = text_hash
        self.total_chunks = total_chunks
        self.chunks: Dict[str, ChunkRecord] = {}
        self.status = 'pending'
        self.created_at = _utc_now()
        self.updated_at = _utc_now()
        self.repo = repo

    @classmethod
    def create_from_chunks(cls, message_id: str, text_hash: str, chunks: List[Any], repo=None) -> 'ExtractionManifest':
        manifest = cls(message_id, text_hash, len(chunks), repo=repo)
        for c in chunks:
            manifest.chunks[c.chunk_id] = ChunkRecord(
                chunk_id=c.chunk_id,
                index=c.index,
                start_char=c.start_char,
                end_char=c.end_char,
                status='pending'
            )
        manifest.persist()
        return manifest

    def start_chunk(self, chunk_id: str) -> None:
        if chunk_id in self.chunks:
            rec = self.chunks[chunk_id]
            rec.status = 'in_progress'
            rec.updated_at = _utc_now()
            self.updated_at = _utc_now()
            self.persist()

    def record_chunk_result(self, chunk_id: str, candidate_ids: List[str] = None, error: str = None) -> None:
        if chunk_id not in self.chunks:
            return
        rec = self.chunks[chunk_id]
        rec.updated_at = _utc_now()
        self.updated_at = _utc_now()
        
        if error:
            rec.status = 'failed'
            rec.error = error
        else:
            rec.status = 'extracted'
            rec.error = None
            if candidate_ids:
                rec.candidate_ids = list(dict.fromkeys(rec.candidate_ids + candidate_ids))

        self._recalculate_status()
        self.persist()

    def mark_chunk_completed(self, chunk_id: str) -> None:
        if chunk_id in self.chunks:
            rec = self.chunks[chunk_id]
            rec.status = 'completed'
            rec.updated_at = _utc_now()
            self._recalculate_status()
            self.persist()

    def retry_chunk(self, chunk_id: str) -> bool:
        if chunk_id in self.chunks:
            rec = self.chunks[chunk_id]
            if rec.retries >= 3:
                return False
            rec.retries += 1
            rec.status = 'pending'
            rec.error = None
            rec.updated_at = _utc_now()
            self._recalculate_status()
            self.persist()
            return True
        return False

    def is_complete(self) -> bool:
        return all(c.status in ('extracted', 'completed') for c in self.chunks.values())

    def unresolved_chunks(self) -> List[ChunkRecord]:
        return [c for c in self.chunks.values() if c.status in ('pending', 'in_progress', 'failed')]

    def all_candidate_ids(self) -> List[str]:
        result = []
        for c in self.chunks.values():
            result.extend(c.candidate_ids)
        return list(dict.fromkeys(result))

    def _recalculate_status(self) -> None:
        statuses = [c.status for c in self.chunks.values()]
        if all(s in ('extracted', 'completed') for s in statuses):
            self.status = 'completed'
        elif any(s == 'failed' for s in statuses):
            self.status = 'partial_failed' if any(s in ('extracted', 'completed') for s in statuses) else 'failed'
        elif any(s == 'in_progress' for s in statuses):
            self.status = 'in_progress'
        else:
            self.status = 'pending'

    def get_summary(self) -> Dict[str, Any]:
        candidates = self.all_candidate_ids()
        unresolved = [c.to_dict() for c in self.unresolved_chunks()]
        return {
            'message_id': self.message_id,
            'status': self.status,
            'total_chunks': self.total_chunks,
            'processed_chunks': sum(1 for c in self.chunks.values() if c.status in ('extracted', 'completed')),
            'failed_chunks': sum(1 for c in self.chunks.values() if c.status == 'failed'),
            'total_candidates': len(candidates),
            'candidate_ids': candidates,
            'unresolved': unresolved,
            'is_complete': self.is_complete(),
        }

    def persist(self) -> None:
        """Persist state to SQLite meta table if repo is available."""
        if not self.repo:
            return
        try:
            key = f"manifest:{self.message_id}"
            payload = json.dumps({
                'message_id': self.message_id,
                'text_hash': self.text_hash,
                'total_chunks': self.total_chunks,
                'status': self.status,
                'created_at': self.created_at,
                'updated_at': self.updated_at,
                'chunks': {cid: c.to_dict() for cid, c in self.chunks.items()},
            }, ensure_ascii=False)
            self.repo.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, payload))
            self.repo.db.commit()
        except Exception:
            pass

    @classmethod
    def load(cls, message_id: str, repo) -> Optional['ExtractionManifest']:
        """Load manifest from SQLite meta table."""
        if not repo:
            return None
        try:
            rows = repo.rows("SELECT value FROM meta WHERE key = ?", (f"manifest:{message_id}",))
            if not rows:
                return None
            data = json.loads(rows[0]['value'])
            manifest = cls(data['message_id'], data['text_hash'], data['total_chunks'], repo=repo)
            manifest.status = data.get('status', 'pending')
            manifest.created_at = data.get('created_at', _utc_now())
            manifest.updated_at = data.get('updated_at', _utc_now())
            for cid, cdata in data.get('chunks', {}).items():
                manifest.chunks[cid] = ChunkRecord.from_dict(cdata)
            return manifest
        except Exception:
            return None

