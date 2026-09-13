from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from .db import now
from .discovery import discover
from .normalize import normalize, PARSER_VERSION

MAX_RECORD = 32 * 1024 * 1024
BATCH_RECORDS = 500


def hash_range(stream, start, length):
    stream.seek(start)
    digest = hashlib.sha256()
    while length:
        block = stream.read(min(length, 1024 * 1024))
        if not block:
            break
        digest.update(block)
        length -= len(block)
    return digest.hexdigest()


def register(connection, source):
    connection.execute("""INSERT INTO sources(canonical_path,original_path,kind,disposition,reason,error,schema_signature,last_seen)
      VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(canonical_path) DO UPDATE SET original_path=excluded.original_path,
      disposition=excluded.disposition,reason=excluded.reason,error=excluded.error,schema_signature=excluded.schema_signature,last_seen=excluded.last_seen""",
      (source["canonical_path"], source["path"], source["kind"], source["disposition"], source.get("reason"), source.get("error"), source.get("schema_signature"), now()))
    return connection.execute("SELECT id FROM sources WHERE canonical_path=?", (source["canonical_path"],)).fetchone()[0]


def ingest_file(connection, source, source_id, salt, full=False, fault=None, finalized=False):
    path = Path(source["path"])
    with path.open("rb") as stream:
        import os
        stat = os.fstat(stream.fileno())
        identity = f"{stat.st_dev}:{stat.st_ino}"
        previous = connection.execute("""SELECT g.id,g.generation,g.file_id,c.* FROM source_generations g
            JOIN checkpoints c ON c.generation_id=g.id WHERE g.source_id=? ORDER BY g.generation DESC LIMIT 1""", (source_id,)).fetchone()
        reason = None
        if previous:
            offset = previous["byte_offset"]
            if previous["file_id"] != identity:
                reason = "replacement"
            elif stat.st_size < offset:
                reason = "truncation"
            elif hash_range(stream, 0, previous["prefix_length"]) != previous["prefix_hash"]:
                reason = "prefix_rewrite"
            elif hash_range(stream, max(0, offset - 4096), min(offset, 4096)) != previous["tail_hash"]:
                reason = "checkpoint_rewrite"
            elif full and previous["content_hash"] and hash_range(stream, 0, offset) != previous["content_hash"]:
                reason = "content_rewrite"
            elif connection.execute("SELECT 1 FROM source_records WHERE generation_id=? AND parser_version<? LIMIT 1", (previous["id"], PARSER_VERSION)).fetchone():
                reason = "parser_upgrade"
        if not previous or reason:
            if previous:
                connection.execute("UPDATE source_generations SET superseded=1 WHERE id=?", (previous["id"],))
            generation = previous["generation"] + 1 if previous else 1
            cursor = connection.execute("INSERT INTO source_generations(source_id,generation,file_id,created_at,change_reason) VALUES (?,?,?,?,?)", (source_id, generation, identity, now(), reason))
            gen_id, offset, ordinal, context = cursor.lastrowid, 0, 0, {}
            connection.execute("INSERT INTO checkpoints(generation_id) VALUES (?)", (gen_id,))
        else:
            gen_id, offset, ordinal, context = previous["id"], previous["byte_offset"], previous["ordinal"], json.loads(previous["context_json"])
            if stat.st_size == offset and not reason:
                connection.execute("UPDATE sources SET disposition='imported',last_success=?,error=NULL WHERE id=?", (now(), source_id))
                connection.commit()
                return dict(records=0, events=0, errors=0, pending_bytes=0, skipped=True)
        counts = Counter(records=0, events=0, errors=0)
        pending = 0
        committed_hash = hashlib.sha256()
        stream.seek(0)
        remaining_prefix = offset
        while remaining_prefix:
            block = stream.read(min(remaining_prefix, 1024 * 1024))
            if not block:
                break
            committed_hash.update(block)
            remaining_prefix -= len(block)
        if previous and not reason and previous["content_hash"] and committed_hash.hexdigest() != previous["content_hash"]:
            return ingest_file(connection, source, source_id, salt, full=True, fault=fault, finalized=finalized)
        stream.seek(offset)

        def commit_checkpoint(final=False):
            pos = stream.tell()
            prefix_length = min(offset, 4096)
            prefix = hash_range(stream, 0, prefix_length)
            tail = hash_range(stream, max(0, offset - 4096), min(offset, 4096))
            # Rolling state covers exactly the committed prefix even at a batch
            # crash boundary; no quadratic rereading or unhashed checkpoint.
            content = committed_hash.hexdigest()
            connection.execute("""UPDATE checkpoints SET byte_offset=?,ordinal=?,context_json=?,prefix_hash=?,prefix_length=?,tail_hash=?,content_hash=?,size=?,mtime_ns=?,pending_bytes=? WHERE generation_id=?""",
                (offset, ordinal, json.dumps(context), prefix, prefix_length, tail, content, stat.st_size, stat.st_mtime_ns, pending, gen_id))
            if fault:
                fault("before_commit")
            connection.commit()
            if fault:
                fault("after_commit")
            stream.seek(pos)

        # Freeze the import watermark at this file handle's initial size.
        while stream.tell() < stat.st_size:
            start = stream.tell()
            raw = stream.readline(min(MAX_RECORD + 1, stat.st_size - start))
            digest = hashlib.sha256(raw)
            candidate_hash = committed_hash.copy()
            candidate_hash.update(raw)
            oversized = len(raw) > MAX_RECORD
            if oversized:
                while not raw.endswith(b"\n") and stream.tell() < stat.st_size:
                    raw = stream.readline(min(MAX_RECORD + 1, stat.st_size - stream.tell()))
                    digest.update(raw)
                    candidate_hash.update(raw)
            end = stream.tell()
            if not raw.endswith(b"\n"):
                # Explicit finalization requires an unchanged prior observation and
                # unchanged handle metadata; a growing file never qualifies.
                current_stat = os.fstat(stream.fileno())
                stable = previous and previous["size"] == stat.st_size and previous["mtime_ns"] == stat.st_mtime_ns and current_stat.st_size == stat.st_size and current_stat.st_mtime_ns == stat.st_mtime_ns
                valid_final = False
                if finalized and stable and not oversized:
                    try:
                        valid_final = isinstance(json.loads(raw), dict)
                    except (ValueError, UnicodeError):
                        pass
                if not valid_final:
                    pending = end - start
                    break
            ordinal += 1
            error, events, kind, timestamp = None, [], None, None
            if oversized:
                error = "oversized_record"
            else:
                try:
                    record = json.loads(raw)
                    if not isinstance(record, dict):
                        raise ValueError()
                    kind = record.get("type") if isinstance(record.get("type"), str) else None
                    timestamp = record.get("timestamp") if isinstance(record.get("timestamp"), str) else None
                    if source["kind"] == "session_index":
                        kind = "session_index"
                        native = record.get("id")
                        events = [dict(kind=kind, session_id=native, turn_id=None, timestamp=record.get("updated_at"), model=None, project=None, native_id=native, data_json="{}")] if isinstance(native, str) else []
                        error = None if events else "unsupported_index_record"
                    else:
                        context["_ordinal"] = ordinal - 1
                        events, error = normalize(record, context, salt)
                except (ValueError, UnicodeError, TypeError, AttributeError, RecursionError):
                    error = "malformed_record"
            cursor = connection.execute("INSERT INTO source_records(generation_id,byte_start,byte_end,ordinal,digest,kind,timestamp,parser_version) VALUES (?,?,?,?,?,?,?,?)", (gen_id, start, end, ordinal, digest.hexdigest(), kind, timestamp, PARSER_VERSION))
            record_id = cursor.lastrowid
            connection.execute("""INSERT INTO record_interpretations VALUES (?,?,?,?)
                ON CONFLICT(source_id,byte_start,digest) DO UPDATE SET record_id=excluded.record_id""", (source_id, start, digest.hexdigest(), record_id))
            for event in events:
                connection.execute("INSERT INTO normalized_events(record_id,kind,session_id,turn_id,timestamp,model,project,native_id,data_json) VALUES (?,?,?,?,?,?,?,?,?)", (record_id, *[event[k] for k in ("kind", "session_id", "turn_id", "timestamp", "model", "project", "native_id", "data_json")]))
            if error:
                connection.execute("INSERT INTO diagnostics(source_id,record_id,code,location,digest,created_at) VALUES (?,?,?,?,?,?)", (source_id, record_id, error, str(start), digest.hexdigest(), now()))
                counts["errors"] += 1
            counts["records"] += 1
            counts["events"] += len(events)
            offset = end
            committed_hash = candidate_hash
            if counts["records"] % BATCH_RECORDS == 0:
                commit_checkpoint()
        connection.execute("UPDATE sources SET disposition=?,last_success=?,error=NULL WHERE id=?", ("pending" if pending else "imported", now(), source_id))
        commit_checkpoint(final=True)
        return dict(counts, pending_bytes=pending, skipped=False, change_reason=reason)


def source_signature(source):
    """Main-file and WAL metadata; periodic full scans verify contents as well."""
    paths=[Path(source['path'])]
    if source['kind'] in ('state','history','catalog'):
        paths.append(Path(source['path']+'-wal'))
    values=[]
    for path in paths:
        try:
            stat=path.stat()
            values.append((stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns))
        except FileNotFoundError:
            values.append(None)
    return tuple(values)


def import_sources(connection, config, full=False, fault=None, finalized_sources=(), signature_cache=None):
    from .estimates import configure
    configure(config.data_dir)
    started = time.perf_counter()
    inventory = discover(config, versions=False)
    cursor = connection.execute("INSERT INTO ingestion_runs(started_at,mode) VALUES (?,?)", (now(), "reconcile_sources" if full else "import"))
    run_id = cursor.lastrowid
    salt = connection.execute("SELECT value FROM settings WHERE key='pattern_salt'").fetchone()[0]
    totals = Counter(discovered=len(inventory["sources"]), imported=0, skipped=0, failed=0, pending=0, records=0, events=0, errors=0)
    dispositions = []
    seen = []
    for source in inventory["sources"]:
        source_id = register(connection, source)
        seen.append(source_id)
        connection.commit()
        if source["kind"] not in ("rollout", "session_index", "state", "history", "catalog") or source["disposition"] != "eligible":
            # M2 owns enrichment. Explicitly retain pending coverage, not a false success.
            disposition = "pending_adapter" if source["disposition"] == "eligible" else source["disposition"]
            connection.execute("UPDATE sources SET disposition=? WHERE id=?", (disposition, source_id))
            connection.commit()
            dispositions.append(dict(source_id=source_id, disposition=disposition))
            continue
        try:
            signature=source_signature(source) if signature_cache is not None else None
            cached=signature_cache.get(source_id) if signature_cache is not None else None
            if not full and cached and cached[0]==signature and cached[1]=='imported':
                connection.execute("UPDATE sources SET disposition='imported',error=NULL WHERE id=?",(source_id,))
                connection.commit()
                totals['skipped']+=1
                dispositions.append(dict(source_id=source_id,skipped=True,records=0,events=0,errors=0,pending_bytes=0))
                continue
            if source["kind"] in ("state", "history", "catalog"):
                from .sources.enrichment import enrich
                result = enrich(connection, source, source_id, salt)
                totals["failed"] += int(bool(result.get("unsupported")))
            else:
                from .config import canonical
                result = ingest_file(connection, source, source_id, salt, full, fault, source["canonical_path"] in {canonical(p) for p in finalized_sources})
            totals["skipped" if result["skipped"] else "imported"] += 1
            for key in ("records", "events", "errors"):
                totals[key] += result[key]
            totals["pending"] += int(bool(result["pending_bytes"]))
            dispositions.append(dict(source_id=source_id, **result))
            if signature_cache is not None and not result.get('unsupported') and not result.get('pending_bytes'):
                signature_cache[source_id]=(signature,'imported')
        except Exception as exc:
            connection.rollback()
            connection.execute("UPDATE sources SET disposition='failed',error=? WHERE id=?", (type(exc).__name__, source_id))
            connection.commit()
            totals["failed"] += 1
            dispositions.append(dict(source_id=source_id, disposition="failed", error=type(exc).__name__))
    if seen:
        connection.execute("UPDATE sources SET disposition='unavailable',error='not_discovered' WHERE id NOT IN (" + ",".join("?" for _ in seen) + ")", seen)
    connection.execute("""INSERT OR IGNORE INTO sessions(id,source_record_id)
        SELECT session_id,min(record_id) FROM normalized_events WHERE session_id IS NOT NULL GROUP BY session_id""")
    connection.execute("""INSERT OR IGNORE INTO session_edges(parent_id,child_id,kind,record_id)
        SELECT json_extract(e.data_json,'$.parent'),e.session_id,'metadata_parent',e.record_id
        FROM normalized_events e JOIN record_interpretations i ON i.record_id=e.record_id
        WHERE e.kind='session_meta' AND json_extract(e.data_json,'$.parent') IS NOT NULL
        AND json_extract(e.data_json,'$.parent')<>e.session_id""")
    summary = dict(totals, seconds=time.perf_counter() - started, sources=dispositions, discovery_diagnostics=inventory["diagnostics"])
    connection.execute("UPDATE ingestion_runs SET completed_at=?,summary_json=? WHERE id=?", (now(), json.dumps(summary), run_id))
    connection.commit()
    return summary
