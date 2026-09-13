CREATE TABLE tool_calls (
 id TEXT PRIMARY KEY, session_id TEXT, native_id TEXT, turn_id TEXT, name TEXT NOT NULL,
 timestamp TEXT, completed_at TEXT, status TEXT NOT NULL, duration_ms REAL, wall_ms REAL,
 argument_bytes INTEGER, result_bytes INTEGER, argument_tokens INTEGER, result_tokens INTEGER,
 estimate_method TEXT NOT NULL, completeness TEXT NOT NULL, pattern_hash TEXT, pattern_kind TEXT,
 level TEXT NOT NULL, parent_id TEXT, coverage TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE INDEX tool_session_time ON tool_calls(session_id,timestamp,id);
CREATE INDEX tool_name ON tool_calls(name,status);
CREATE TABLE tool_sources (
 tool_id TEXT NOT NULL REFERENCES tool_calls(id) ON DELETE CASCADE,
 record_id INTEGER NOT NULL REFERENCES source_records(id), PRIMARY KEY(tool_id,record_id)
);
CREATE INDEX tool_source_record ON tool_sources(record_id,tool_id);
CREATE TABLE pattern_occurrences (
 pattern_hash TEXT NOT NULL, tool_id TEXT NOT NULL REFERENCES tool_calls(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, likely_retry INTEGER NOT NULL, previous_tool_id TEXT,
 PRIMARY KEY(pattern_hash,tool_id)
);
CREATE TABLE benchmark_labels (
 session_id TEXT PRIMARY KEY, label TEXT NOT NULL, updated_at TEXT NOT NULL
);
