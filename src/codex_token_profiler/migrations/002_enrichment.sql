ALTER TABLE source_records ADD COLUMN table_name TEXT;
ALTER TABLE source_records ADD COLUMN row_key TEXT;
ALTER TABLE source_records ADD COLUMN superseded INTEGER NOT NULL DEFAULT 0;
CREATE TABLE database_rows (
 source_id INTEGER NOT NULL REFERENCES sources(id), table_name TEXT NOT NULL,
 row_key TEXT NOT NULL, digest TEXT NOT NULL, record_id INTEGER NOT NULL REFERENCES source_records(id),
 revision TEXT, PRIMARY KEY(source_id,table_name,row_key)
);
CREATE TABLE sessions (
 id TEXT PRIMARY KEY, cwd TEXT, project_id TEXT, model TEXT,
 created_at TEXT, updated_at TEXT, archived INTEGER, reported_state_tokens INTEGER,
 coverage TEXT NOT NULL DEFAULT 'unknown', source_record_id INTEGER REFERENCES source_records(id)
);
CREATE TABLE session_edges (
 parent_id TEXT NOT NULL, child_id TEXT NOT NULL, kind TEXT NOT NULL,
 record_id INTEGER NOT NULL REFERENCES source_records(id), PRIMARY KEY(parent_id,child_id,kind,record_id)
);
CREATE TABLE projects (
 id TEXT NOT NULL, root TEXT NOT NULL, record_id INTEGER NOT NULL REFERENCES source_records(id),
 PRIMARY KEY(id,root)
);
CREATE TABLE turns (
 session_id TEXT NOT NULL, id TEXT NOT NULL, status TEXT, started_at TEXT, completed_at TEXT,
 duration_ms REAL, record_id INTEGER NOT NULL REFERENCES source_records(id), PRIMARY KEY(session_id,id)
);
