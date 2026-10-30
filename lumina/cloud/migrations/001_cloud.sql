CREATE TABLE cloud_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE cloud_conversations(id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE cloud_turns(
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES cloud_conversations(id),
 client_message_id TEXT NOT NULL, input TEXT NOT NULL, status TEXT NOT NULL,
 created_at REAL NOT NULL, completed_at REAL, answer TEXT, error TEXT,
 lease_until REAL, fence INTEGER NOT NULL DEFAULT 0,
 UNIQUE(conversation_id, client_message_id)
);
CREATE TABLE cloud_messages(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 conversation_id TEXT NOT NULL REFERENCES cloud_conversations(id),
 turn_id TEXT NOT NULL REFERENCES cloud_turns(id), role TEXT NOT NULL,
 content TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(turn_id,role)
);
CREATE TABLE cloud_requests(
 scope TEXT NOT NULL, key TEXT NOT NULL, digest TEXT NOT NULL,
 resource_id TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(scope,key)
);
CREATE TABLE cloud_events(
 cursor INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 type TEXT NOT NULL, resource_id TEXT NOT NULL, resource_version INTEGER NOT NULL,
 created_at REAL NOT NULL, correlation_id TEXT, payload_json TEXT NOT NULL
);
CREATE TABLE cloud_tasks(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind='reminder'),
 status TEXT NOT NULL, message TEXT NOT NULL, due_at REAL NOT NULL,
 timezone TEXT NOT NULL, created_at REAL NOT NULL, completed_at REAL,
 attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL, fence INTEGER NOT NULL DEFAULT 0,
 version INTEGER NOT NULL DEFAULT 1, error TEXT
);
CREATE TABLE cloud_notifications(
 id TEXT PRIMARY KEY, task_id TEXT UNIQUE NOT NULL REFERENCES cloud_tasks(id),
 message TEXT NOT NULL, created_at REAL NOT NULL, read_at REAL
);
CREATE INDEX cloud_tasks_due ON cloud_tasks(status,due_at);
CREATE INDEX cloud_turns_queue ON cloud_turns(status,created_at);
CREATE INDEX cloud_messages_conversation ON cloud_messages(conversation_id,seq);
CREATE INDEX cloud_events_resource ON cloud_events(resource_id,resource_version);
