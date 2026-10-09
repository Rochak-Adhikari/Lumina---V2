-- Applied statement-by-statement under the repository's BEGIN IMMEDIATE.
-- Keep the legacy table, integer identifiers, and soft-deleted rows intact.
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY, category TEXT NOT NULL, text TEXT NOT NULL,
    created REAL NOT NULL, updated REAL NOT NULL, deleted REAL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories(category);
CREATE TABLE meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);

CREATE TABLE entities (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_key TEXT NOT NULL UNIQUE,
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(metadata_json))
);

CREATE TABLE events (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    session_id TEXT,
    device_id TEXT,
    project_id TEXT,
    source_type TEXT NOT NULL DEFAULT 'unknown',
    source_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1)
);

CREATE TABLE facts (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    subject_entity_id TEXT NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    object_entity_id TEXT REFERENCES entities(id),
    confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1),
    stability REAL NOT NULL DEFAULT 0.5 CHECK(stability BETWEEN 0 AND 1),
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1),
    valid_from TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    valid_until TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','disputed','superseded','invalidated','expired')),
    confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK(confirmed_by_user IN (0,1)),
    source_type TEXT NOT NULL DEFAULT 'unknown',
    last_confirmed_at TEXT,
    project_id TEXT
);

CREATE TABLE evidence (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    event_id TEXT REFERENCES events(id),
    source_type TEXT NOT NULL DEFAULT 'unknown',
    source_id TEXT,
    observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    extraction_method TEXT NOT NULL DEFAULT 'unknown',
    confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1),
    confirmed_by_user INTEGER NOT NULL DEFAULT 0 CHECK(confirmed_by_user IN (0,1)),
    model_metadata_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(model_metadata_json)),
    source_fingerprint TEXT NOT NULL,
    UNIQUE(record_type, record_id, source_fingerprint)
);

CREATE TABLE episodes (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ended_at TEXT,
    project_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1)
);

CREATE TABLE decisions (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    subject TEXT NOT NULL,
    chosen_option TEXT NOT NULL,
    alternatives_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(alternatives_json)),
    reasoning TEXT NOT NULL DEFAULT '',
    constraints_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(constraints_json)),
    assumptions_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(assumptions_json)),
    expected_outcome TEXT,
    actual_outcome TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    made_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    superseded_at TEXT,
    project_id TEXT,
    importance REAL NOT NULL DEFAULT 0.5 CHECK(importance BETWEEN 0 AND 1)
);

CREATE TABLE goals (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    priority REAL NOT NULL DEFAULT 0.5,
    deadline TEXT,
    completed_at TEXT,
    project_id TEXT,
    parent_goal_id TEXT REFERENCES goals(id)
);

CREATE TABLE commitments (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    description TEXT NOT NULL,
    owner_entity_id TEXT REFERENCES entities(id),
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1),
    project_id TEXT
);

CREATE TABLE open_loops (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    blocked_by_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(blocked_by_json)),
    next_action TEXT,
    resolved_at TEXT,
    project_id TEXT,
    task_id TEXT
);

CREATE TABLE relationships (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    source_entity TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.7 CHECK(confidence BETWEEN 0 AND 1),
    valid_from TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    valid_until TEXT,
    source_event TEXT REFERENCES events(id),
    project_id TEXT
);

CREATE TABLE memory_candidates (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    proposal_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(proposal_json)),
    status TEXT NOT NULL DEFAULT 'pending',
    decision TEXT,
    reason TEXT,
    source_event_id TEXT REFERENCES events(id),
    record_id TEXT
);

CREATE TABLE predictions (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    prediction TEXT NOT NULL,
    horizon TEXT,
    confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'pending',
    outcome TEXT,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(evidence_ids_json)),
    project_id TEXT
);

CREATE TABLE behavior_patterns (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT,
    pattern TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT 'hypothesis',
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK(evidence_count >= 0),
    supporting_events_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(supporting_events_json)),
    last_observed TEXT,
    project_id TEXT
);

-- The mapping deliberately survives canonical hard deletion: a forgotten
-- legacy record must not be imported again when the database is reopened.
CREATE TABLE legacy_memory_map (
    legacy_id INTEGER PRIMARY KEY REFERENCES memories(id),
    record_id TEXT NOT NULL
);
CREATE TABLE episode_events (
    id TEXT PRIMARY KEY NOT NULL,
    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES events(id),
    UNIQUE(episode_id, event_id)
);
CREATE TABLE current_state (
    id TEXT PRIMARY KEY NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(data_json)),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1)
);
CREATE VIRTUAL TABLE memory_fts USING fts5(record_id UNINDEXED, kind UNINDEXED, content);

CREATE TABLE sync_outbox (
    id TEXT PRIMARY KEY NOT NULL DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)), 2) || '-' || substr('89ab', (random() & 3) + 1, 1) || substr(hex(randomblob(2)), 2) || '-' || hex(randomblob(6)))),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('insert','update','delete')),
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    synced_at TEXT,
    privacy_class TEXT NOT NULL DEFAULT 'private',
    sync_policy TEXT NOT NULL DEFAULT 'local_only',
    device_scope TEXT
);

CREATE INDEX events_timestamp ON events(timestamp);
CREATE INDEX events_project_timestamp ON events(project_id, timestamp);
CREATE INDEX facts_subject_predicate ON facts(subject_entity_id, predicate, status);
CREATE INDEX facts_project_status ON facts(project_id, status, valid_until);
CREATE INDEX evidence_event ON evidence(event_id);
CREATE INDEX episodes_project_started ON episodes(project_id, started_at);
CREATE INDEX decisions_project_status ON decisions(project_id, status);
CREATE INDEX goals_project_status ON goals(project_id, status);
CREATE INDEX goals_parent ON goals(parent_goal_id);
CREATE INDEX commitments_project_status ON commitments(project_id, status);
CREATE INDEX open_loops_project_status ON open_loops(project_id, status);
CREATE INDEX open_loops_task ON open_loops(task_id);
CREATE INDEX relationships_source ON relationships(source_entity, relationship_type);
CREATE INDEX relationships_target ON relationships(target_entity, relationship_type);
CREATE INDEX candidates_source_event ON memory_candidates(source_event_id);
CREATE INDEX predictions_project_status ON predictions(project_id, status);
CREATE INDEX patterns_project_status ON behavior_patterns(project_id, status);
CREATE INDEX sync_outbox_pending ON sync_outbox(synced_at, created_at);

CREATE TRIGGER events_immutable BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'Events are immutable.');
END;

-- Outbox triggers also cover trusted service SQL through Repository.db.
-- Evidence links, joins, caches, legacy data, and metadata are not canonical
-- mutations and do not recursively create outbox entries.
CREATE TRIGGER entities_outbox_insert AFTER INSERT ON entities
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('entities', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER entities_outbox_update AFTER UPDATE ON entities
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('entities', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER entities_outbox_delete AFTER DELETE ON entities
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('entities', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER events_outbox_insert AFTER INSERT ON events
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('events', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER events_outbox_update AFTER UPDATE ON events
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('events', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER events_outbox_delete AFTER DELETE ON events
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('events', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER facts_outbox_insert AFTER INSERT ON facts
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('facts', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER facts_outbox_update AFTER UPDATE ON facts
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('facts', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER facts_outbox_delete AFTER DELETE ON facts
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('facts', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER episodes_outbox_insert AFTER INSERT ON episodes
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('episodes', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER episodes_outbox_update AFTER UPDATE ON episodes
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('episodes', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER episodes_outbox_delete AFTER DELETE ON episodes
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('episodes', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER decisions_outbox_insert AFTER INSERT ON decisions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('decisions', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER decisions_outbox_update AFTER UPDATE ON decisions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('decisions', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER decisions_outbox_delete AFTER DELETE ON decisions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('decisions', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER goals_outbox_insert AFTER INSERT ON goals
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('goals', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER goals_outbox_update AFTER UPDATE ON goals
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('goals', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER goals_outbox_delete AFTER DELETE ON goals
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('goals', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER commitments_outbox_insert AFTER INSERT ON commitments
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('commitments', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER commitments_outbox_update AFTER UPDATE ON commitments
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('commitments', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER commitments_outbox_delete AFTER DELETE ON commitments
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('commitments', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER open_loops_outbox_insert AFTER INSERT ON open_loops
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('open_loops', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER open_loops_outbox_update AFTER UPDATE ON open_loops
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('open_loops', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER open_loops_outbox_delete AFTER DELETE ON open_loops
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('open_loops', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER relationships_outbox_insert AFTER INSERT ON relationships
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('relationships', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER relationships_outbox_update AFTER UPDATE ON relationships
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('relationships', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER relationships_outbox_delete AFTER DELETE ON relationships
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('relationships', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER memory_candidates_outbox_insert AFTER INSERT ON memory_candidates
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('memory_candidates', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER memory_candidates_outbox_update AFTER UPDATE ON memory_candidates
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('memory_candidates', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER memory_candidates_outbox_delete AFTER DELETE ON memory_candidates
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('memory_candidates', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER predictions_outbox_insert AFTER INSERT ON predictions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('predictions', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER predictions_outbox_update AFTER UPDATE ON predictions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('predictions', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER predictions_outbox_delete AFTER DELETE ON predictions
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('predictions', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;

CREATE TRIGGER behavior_patterns_outbox_insert AFTER INSERT ON behavior_patterns
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('behavior_patterns', NEW.id, 'insert', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER behavior_patterns_outbox_update AFTER UPDATE ON behavior_patterns
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('behavior_patterns', NEW.id, 'update', NEW.version, NEW.privacy_class, NEW.sync_policy, NEW.device_scope);
END;

CREATE TRIGGER behavior_patterns_outbox_delete AFTER DELETE ON behavior_patterns
BEGIN
    INSERT INTO sync_outbox(entity_type, entity_id, operation, version, privacy_class, sync_policy, device_scope)
    VALUES('behavior_patterns', OLD.id, 'delete', OLD.version + 1, OLD.privacy_class, OLD.sync_policy, OLD.device_scope);
    DELETE FROM memory_fts WHERE record_id = OLD.id;
END;
