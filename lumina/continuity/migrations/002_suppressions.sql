-- Migration 002: Durable Memory Suppressions & Anti-Resurrection Ledger
-- Applied under BEGIN IMMEDIATE by repository migration runner.

CREATE TABLE IF NOT EXISTS memory_suppressions (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    subject_canonical_key TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_fingerprint TEXT NOT NULL,
    original_fact_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL CHECK(mode IN ('invalidated','forgotten','hard_deleted')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','overridden')),
    overridden_at TEXT,
    override_event_id TEXT REFERENCES events(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suppressions_active 
ON memory_suppressions(subject_canonical_key, predicate, object_fingerprint) 
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_suppressions_subject 
ON memory_suppressions(subject_canonical_key, status);
