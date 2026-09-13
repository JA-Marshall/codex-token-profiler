CREATE TABLE usage_facts (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT, timestamp TEXT,
 interval_start TEXT, interval_end TEXT, model TEXT, project TEXT,
 method TEXT NOT NULL, accounting_version INTEGER NOT NULL,
 input_tokens INTEGER, cached_input_tokens INTEGER, cache_write_input_tokens INTEGER,
 output_tokens INTEGER, reasoning_output_tokens INTEGER, total_tokens INTEGER,
 coverage TEXT NOT NULL
);
CREATE INDEX usage_session_time ON usage_facts(session_id,timestamp,id);
CREATE INDEX usage_filters ON usage_facts(project,model,timestamp);
CREATE TABLE fact_sources (
 fact_id TEXT NOT NULL REFERENCES usage_facts(id) ON DELETE CASCADE,
 record_id INTEGER NOT NULL REFERENCES source_records(id), PRIMARY KEY(fact_id,record_id)
);
CREATE TABLE accounting_gaps (
 id TEXT PRIMARY KEY, session_id TEXT, record_id INTEGER REFERENCES source_records(id),
 code TEXT NOT NULL, detail_json TEXT NOT NULL, accounting_version INTEGER NOT NULL
);
CREATE VIEW usage_observations AS
 SELECT e.id,e.record_id,e.kind,e.session_id,e.turn_id,e.timestamp,e.model,e.project,e.native_id,
 e.data_json,r.generation_id,r.ordinal,r.superseded AS row_superseded,g.superseded AS generation_superseded
 FROM normalized_events e JOIN source_records r ON r.id=e.record_id
 JOIN source_generations g ON g.id=r.generation_id
 WHERE e.kind IN ('cumulative_usage','response_usage');
