from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from ..db import now
from ..normalize import PARSER_VERSION
from .history import item_metrics
from .sqlite import readonly, schema


def utc(value, millis=False):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / (1000 if millis else 1), timezone.utc).isoformat()
    return value if isinstance(value, str) else None


def enrich(connection, source, source_id, salt):
    """Full mutable-key reconciliation; payloads decoded only for new/changed rows.

    Source snapshots are read-only and short per table; row changes retain previous
    provenance but supersede the old projection. Rollout usage is never added here.
    """
    stat = Path(source["path"]).stat()
    identity = f"{stat.st_dev}:{stat.st_ino}"
    generation = connection.execute("SELECT id,generation,file_id FROM source_generations WHERE source_id=? ORDER BY generation DESC LIMIT 1", (source_id,)).fetchone()
    if generation and generation["file_id"] == identity:
        gen_id = generation[0]
    else:
        if generation:
            connection.execute("UPDATE source_generations SET superseded=1 WHERE id=?", (generation["id"],))
        gen_id = connection.execute("INSERT INTO source_generations(source_id,generation,file_id,created_at,change_reason) VALUES (?,?,?,?,?)", (source_id, generation["generation"] + 1 if generation else 1, identity, now(), "database_replacement" if generation else "database_initial")).lastrowid
    ordinal = connection.execute("SELECT coalesce(max(ordinal),0) FROM source_records WHERE generation_id=?", (gen_id,)).fetchone()[0]
    count = 0
    event_count = 0
    error_count = 0
    unsupported = []

    def persist(table, key, values, revision=None):
        nonlocal ordinal, count
        digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        key = json.dumps(key, separators=(",", ":"))
        old = connection.execute("SELECT d.digest,d.record_id,r.generation_id,r.parser_version FROM database_rows d JOIN source_records r ON r.id=d.record_id WHERE d.source_id=? AND d.table_name=? AND d.row_key=?", (source_id, table, key)).fetchone()
        if old and old["digest"] == digest and old["generation_id"] == gen_id and old["parser_version"] == PARSER_VERSION:
            return None
        ordinal += 1
        if old:
            connection.execute("UPDATE source_records SET superseded=1 WHERE id=?", (old["record_id"],))
        record_id = connection.execute("""INSERT INTO source_records(generation_id,byte_start,byte_end,ordinal,digest,kind,parser_version,table_name,row_key)
            VALUES (?,?,?,?,?,?,?,?,?)""", (gen_id, ordinal, ordinal, ordinal, digest, table, PARSER_VERSION, table, key)).lastrowid
        connection.execute("""INSERT INTO database_rows VALUES (?,?,?,?,?,?) ON CONFLICT(source_id,table_name,row_key)
            DO UPDATE SET digest=excluded.digest,record_id=excluded.record_id,revision=excluded.revision""", (source_id, table, key, digest, record_id, str(revision) if revision is not None else None))
        count += 1
        return record_id

    def session(thread_id, record_id, **values):
        if not isinstance(thread_id, str):
            return
        connection.execute("INSERT OR IGNORE INTO sessions(id,source_record_id) VALUES (?,?)", (thread_id, record_id))
        for key, value in values.items():
            if value is not None:
                connection.execute(f"UPDATE sessions SET {key}=? WHERE id=?", (value, thread_id))

    with readonly(Path(source["path"])) as reader:
        tables = schema(reader)
        expected_tables = {"state": {"threads"}, "history": {"thread_turns", "thread_items", "thread_realtime_items"}, "catalog": {"local_thread_catalog", "thread_timeline_ledger"}}[source["kind"]]
        if not expected_tables.intersection(tables):
            unsupported.append("missing_supported_tables")
        def rows(table, wanted, required):
            available = {c["name"] for c in tables.get(table, [])}
            if not set(required) <= available:
                if table in tables:
                    unsupported.append(table)
                return []
            columns = [name for name in wanted if name in available]
            return reader.execute('SELECT ' + ','.join('"' + c + '"' for c in columns) + f' FROM "{table}"')

        if source["kind"] == "state":
            for raw in rows("threads", ("id", "cwd", "project_id", "created_at", "updated_at", "archived", "tokens_used", "rollout_path"), ("id",)):
                row = dict(raw)
                record_id = persist("threads", [row["id"]], row)
                if record_id:
                    # Today's model is deliberately not backfilled onto old usage.
                    session(row["id"], record_id, cwd=row.get("cwd"), project_id=row.get("project_id"), created_at=utc(row.get("created_at")), updated_at=utc(row.get("updated_at")), archived=row.get("archived"), reported_state_tokens=row.get("tokens_used"))
            for raw in rows("thread_spawn_edges", ("parent_thread_id", "child_thread_id", "status"), ("parent_thread_id", "child_thread_id")):
                row = dict(raw)
                record_id = persist("thread_spawn_edges", [row["parent_thread_id"], row["child_thread_id"]], row)
                if record_id:
                    connection.execute("INSERT OR IGNORE INTO session_edges VALUES (?,?,?,?)", (row["parent_thread_id"], row["child_thread_id"], "spawn", record_id))
            for raw in rows("project_roots", ("project_id", "path", "position"), ("project_id", "path")):
                row = dict(raw)
                record_id = persist("project_roots", [row["project_id"], row["path"]], row)
                if record_id:
                    connection.execute("INSERT OR REPLACE INTO projects VALUES (?,?,?)", (row["project_id"], row["path"], record_id))
        elif source["kind"] == "catalog":
            hosts = {r["host_id"]: r["host_kind"] for r in rows("local_thread_catalog_hosts", ("host_id", "host_kind"), ("host_id", "host_kind"))}
            for raw in rows("local_thread_catalog", ("host_id", "thread_id", "cwd", "project_id", "source_created_at", "source_updated_at", "observation_sequence"), ("thread_id",)):
                row = dict(raw)
                row["host_kind"] = hosts.get(row.get("host_id"), "unknown")
                record_id = persist("local_thread_catalog", [row.get("host_id"), row["thread_id"]], row, row.get("observation_sequence"))
                if record_id:
                    session(row["thread_id"], record_id, cwd=row.get("cwd"), project_id=row.get("project_id"), host_id=row.get("host_id"), host_kind=row["host_kind"], coverage="remote_metadata_only" if row["host_kind"] != "local" else "unknown")
            # An unexpected nonempty timeline is an explicit unsupported gap.
            if "thread_timeline_ledger" in tables and reader.execute("SELECT 1 FROM thread_timeline_ledger LIMIT 1").fetchone():
                unsupported.append("nonempty_thread_timeline_ledger")
        elif source["kind"] == "history":
            for raw in rows("thread_turns", ("thread_id", "turn_id", "status", "started_at", "completed_at", "duration_ms", "rollout_ordinal", "rollout_byte_offset", "rollout_end_ordinal"), ("thread_id", "turn_id")):
                row = dict(raw)
                record_id = persist("thread_turns", [row["thread_id"], row["turn_id"]], row, row.get("rollout_end_ordinal"))
                if record_id:
                    session(row["thread_id"], record_id)
                    connection.execute("INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?,?,?)", (row["thread_id"], row["turn_id"], row.get("status"), utc(row.get("started_at")), utc(row.get("completed_at")), row.get("duration_ms"), record_id))
            for table in ("thread_items", "thread_realtime_items"):
                for raw in rows(table, ("thread_id", "turn_id", "item_id", "rollout_ordinal", "created_at_ms", "item_json", "item_type", "updated_at_ordinal"), ("thread_id", "item_id", "item_json")):
                    row = dict(raw)
                    record_id = persist(table, [row["thread_id"], row["item_id"]], row, row.get("updated_at_ordinal", row.get("rollout_ordinal")))
                    if record_id:
                        session(row["thread_id"], record_id)
                        try:
                            item = json.loads(row["item_json"])
                            metrics = item_metrics(item, salt)
                            metrics["rollout_ordinal"] = row.get("rollout_ordinal")
                            connection.execute("INSERT INTO normalized_events(record_id,kind,session_id,turn_id,timestamp,native_id,data_json) VALUES (?,?,?,?,?,?,?)", (record_id, "item_completed", row["thread_id"], row.get("turn_id"), utc(row.get("created_at_ms"), millis=True), row["item_id"], json.dumps(metrics)))
                            event_count += 1
                        except (ValueError, TypeError, AttributeError):
                            error_count += 1
                            connection.execute("INSERT INTO diagnostics(source_id,record_id,code,created_at) VALUES (?,?,'malformed_projection',?)", (source_id, record_id, now()))
        if not tables:
            unsupported.append("empty_schema")
    for name in unsupported:
        connection.execute("INSERT INTO diagnostics(source_id,code,location,created_at) VALUES (?,'unsupported_schema',?,?)", (source_id, name, now()))
    connection.execute("UPDATE sources SET disposition=?,last_success=?,error=? WHERE id=?", ("failed" if unsupported else "imported", now(), "unsupported_schema" if unsupported else None, source_id))
    connection.commit()
    return dict(records=count, events=event_count, errors=len(unsupported) + error_count, pending_bytes=0, skipped=count == 0, unsupported=unsupported)
