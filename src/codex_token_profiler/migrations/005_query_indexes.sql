CREATE INDEX normalized_record ON normalized_events(record_id);
CREATE INDEX gaps_record ON accounting_gaps(record_id);
CREATE INDEX gaps_code_session ON accounting_gaps(code,session_id);
DROP VIEW usage_observations;
CREATE VIEW usage_observations AS
 SELECT e.id,e.record_id,e.kind,e.session_id,e.turn_id,e.timestamp,e.model,e.project,e.native_id,
 e.data_json,r.generation_id,r.ordinal,r.digest,r.byte_start,g.source_id,
 r.superseded AS row_superseded,g.superseded AS generation_superseded
 FROM normalized_events e JOIN source_records r ON r.id=e.record_id
 JOIN source_generations g ON g.id=r.generation_id
 WHERE e.kind IN ('cumulative_usage','response_usage');
