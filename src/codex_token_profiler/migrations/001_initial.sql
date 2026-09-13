CREATE TABLE sources (
 id INTEGER PRIMARY KEY, canonical_path TEXT UNIQUE NOT NULL, original_path TEXT NOT NULL,
 kind TEXT NOT NULL, disposition TEXT NOT NULL, reason TEXT, error TEXT,
 schema_signature TEXT, last_seen TEXT, last_success TEXT
);
CREATE TABLE source_generations (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
 generation INTEGER NOT NULL, file_id TEXT, created_at TEXT NOT NULL,
 superseded INTEGER NOT NULL DEFAULT 0, change_reason TEXT,
 UNIQUE(source_id,generation)
);
CREATE TABLE checkpoints (
 generation_id INTEGER PRIMARY KEY REFERENCES source_generations(id),
 byte_offset INTEGER NOT NULL DEFAULT 0, ordinal INTEGER NOT NULL DEFAULT 0,
 context_json TEXT NOT NULL DEFAULT '{}', prefix_hash TEXT, prefix_length INTEGER NOT NULL DEFAULT 0,
 tail_hash TEXT, content_hash TEXT, size INTEGER NOT NULL DEFAULT 0, mtime_ns INTEGER,
 pending_bytes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE source_records (
 id INTEGER PRIMARY KEY, generation_id INTEGER NOT NULL REFERENCES source_generations(id),
 byte_start INTEGER NOT NULL, byte_end INTEGER NOT NULL, ordinal INTEGER NOT NULL,
 digest TEXT NOT NULL, kind TEXT, timestamp TEXT, parser_version INTEGER NOT NULL,
 UNIQUE(generation_id,byte_start)
);
CREATE INDEX record_generation_order ON source_records(generation_id,ordinal);
CREATE TABLE normalized_events (
 id INTEGER PRIMARY KEY, record_id INTEGER NOT NULL REFERENCES source_records(id),
 kind TEXT NOT NULL, session_id TEXT, turn_id TEXT, timestamp TEXT,
 model TEXT, project TEXT, native_id TEXT, data_json TEXT NOT NULL
);
CREATE INDEX event_session_time ON normalized_events(session_id,timestamp,id);
CREATE INDEX event_native ON normalized_events(kind,native_id);
CREATE TABLE diagnostics (
 id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
 record_id INTEGER REFERENCES source_records(id), code TEXT NOT NULL,
 location TEXT, digest TEXT, created_at TEXT NOT NULL
);
CREATE TABLE ingestion_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
 mode TEXT NOT NULL, summary_json TEXT
);
CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
