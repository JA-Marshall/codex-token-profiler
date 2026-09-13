CREATE TABLE record_interpretations (
 source_id INTEGER NOT NULL REFERENCES sources(id), byte_start INTEGER NOT NULL,
 digest TEXT NOT NULL, record_id INTEGER NOT NULL REFERENCES source_records(id),
 PRIMARY KEY(source_id,byte_start,digest)
);
CREATE UNIQUE INDEX interpretation_record ON record_interpretations(record_id);
INSERT INTO record_interpretations
 SELECT g.source_id,r.byte_start,r.digest,max(r.id)
 FROM source_records r JOIN source_generations g ON g.id=r.generation_id
 WHERE r.table_name IS NULL GROUP BY g.source_id,r.byte_start,r.digest;
DROP VIEW usage_observations;
CREATE VIEW usage_observations AS
 SELECT e.id,e.record_id,e.kind,e.session_id,e.turn_id,e.timestamp,e.model,e.project,e.native_id,
 e.data_json,r.generation_id,r.ordinal,r.digest,r.byte_start,g.source_id,r.parser_version,
 r.superseded AS row_superseded,g.superseded AS generation_superseded
 FROM normalized_events e JOIN source_records r ON r.id=e.record_id
 JOIN record_interpretations interpretation ON interpretation.record_id=r.id
 JOIN source_generations g ON g.id=r.generation_id
 WHERE e.kind IN ('cumulative_usage','response_usage');
