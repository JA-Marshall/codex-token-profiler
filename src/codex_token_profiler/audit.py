"""Independent read-only arithmetic over source bytes at committed watermarks.

This intentionally does not import the production accounting or normalization
functions. Complex histories are explicitly outside this simple arithmetic oracle.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def audit_sources(connection):
    results = []
    native_responses = {}
    response_conflicts = []
    sources = connection.execute("""SELECT s.id,s.original_path,g.id AS generation_id,c.byte_offset,c.content_hash
        FROM sources s JOIN source_generations g ON g.source_id=s.id JOIN checkpoints c ON c.generation_id=g.id
        WHERE s.kind='rollout' AND g.superseded=0""").fetchall()
    for source in sources:
        reason, header, first, previous, last, first_task = None, None, None, None, None, None
        metadata_count = 0
        digest = hashlib.sha256()
        responses = {}
        tags = ["archive"] if "archived_sessions" in source["original_path"] else ["active"]
        last_counter_timestamp = None
        try:
            with Path(source["original_path"]).open("rb") as stream:
                while stream.tell() < source["byte_offset"]:
                    raw = stream.readline(source["byte_offset"] - stream.tell())
                    if not raw:
                        break
                    digest.update(raw)
                    value = json.loads(raw)
                    payload = value.get("payload", {})
                    if value.get("type") == "session_meta":
                        metadata_count += 1
                        header = header or payload
                        if payload.get("parent_thread_id") or payload.get("forked_from_id"):
                            tags.append("branch")
                    if value.get("type") == "compacted":
                        tags.append("compaction")
                    if value.get("type") == "event_msg" and payload.get("type") == "task_started":
                        first_task = first_task or value.get("timestamp")
                    if value.get("type") == "token_usage_record":
                        if payload.get("response_id"):
                            responses[payload["response_id"]] = (value.get("timestamp"), payload.get("usage"))
                            native = payload["response_id"]
                            observation = dict(owner=payload.get("thread_id"), usage=payload.get("usage"))
                            if native in native_responses and native_responses[native] != observation:
                                response_conflicts.append(native)
                            native_responses[native] = observation
                    if value.get("type") != "event_msg" or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info") or {}
                    total = info.get("total_token_usage")
                    if not isinstance(total, dict) or any(type(total.get(k)) is not int for k in FIELDS):
                        reason = reason or "missing_categories"
                        continue
                    if first is None:
                        first = total
                        if total != info.get("last_token_usage") or not first_task or first_task > value.get("timestamp", ""):
                            reason = reason or "unproven_first_boundary"
                    if previous and any(total[k] < previous[k] for k in FIELDS):
                        reason = "counter_decrease"
                    previous, last = total, total
                    last_counter_timestamp = value.get("timestamp")
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            reason = type(exc).__name__
        if digest.hexdigest() != source["content_hash"]:
            reason = "source_changed_before_watermark"
        if metadata_count != 1:
            reason = "multiple_identity_epochs"
        if last is None:
            reason = reason or "no_cumulative_usage"
        row = dict(source_id=source["id"], generation_id=source["generation_id"], watermark=source["byte_offset"], disposition="outside_simple_oracle", reason=reason, tags=sorted(set(tags)))
        if reason is None:
            expected = dict(last)
            for timestamp, usage in responses.values():
                if timestamp and timestamp > last_counter_timestamp:
                    for key in FIELDS:
                        expected[key] += usage[key]
            if responses and next(iter(responses.values()))[1] == first:
                response_sum = {key: sum(usage[key] for _, usage in responses.values()) for key in FIELDS}
                if all(response_sum[key] >= last[key] for key in FIELDS):
                    expected = response_sum
            session_id = header["id"]
            actual = dict(connection.execute("SELECT " + ",".join(f"sum({key}) AS {key}" for key in FIELDS) + " FROM usage_facts WHERE session_id=?", (session_id,)).fetchone())
            row.update(session_id=session_id, disposition="exact" if expected == actual else "mismatch", expected=expected, actual=actual)
        results.append(row)
    actual_responses = {}
    for fact in connection.execute("""SELECT DISTINCT f.*,e.native_id FROM usage_facts f
            CROSS JOIN fact_sources fs ON fs.fact_id=f.id CROSS JOIN normalized_events e ON e.record_id=fs.record_id
            WHERE f.method='reported_response' AND e.kind='response_usage'"""):
        actual_responses[fact["native_id"]] = dict(owner=fact["session_id"], usage={k: fact[k] for k in FIELDS})
    response_mismatches = [key for key in native_responses.keys() | actual_responses.keys() if native_responses.get(key) != actual_responses.get(key)]
    return dict(method="independent_source_oracles_v2", counts=dict(Counter(r["disposition"] for r in results)),
        exact_tags=dict(Counter(tag for r in results if r["disposition"] == "exact" for tag in r["tags"])),
        exclusions=dict(Counter(r["reason"] for r in results if r["reason"])), sources=results,
        response_oracle=dict(source_responses=len(native_responses), ledger_responses=len(actual_responses), conflicts=response_conflicts, mismatches=response_mismatches))
