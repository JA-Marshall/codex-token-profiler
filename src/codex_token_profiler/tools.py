"""Canonical observed tool invocations, separate from reported model usage."""
from collections import defaultdict
from datetime import datetime
import hashlib
import json

TOOL_TYPES = {"commandExecution", "mcpToolCall", "dynamicToolCall", "fileChange", "webSearch", "imageView", "collabAgentToolCall", "sleep", "imageGeneration", "functionCallOutput"}


def elapsed(start, end):
    if not start or not end:
        return None
    try:
        result = (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds() * 1000
        return result if result >= 0 else None
    except ValueError:
        return None


def key(owner, native):
    return hashlib.sha256(json.dumps([owner, native]).encode()).hexdigest()


def build_tools(events, edges=()):
    parents = defaultdict(set)
    for parent, child in edges:
        parents[child].add(parent)
    def ancestors(session):
        seen, pending = set(), list(parents[session])
        while pending:
            parent = pending.pop()
            if parent not in seen and parent != session:
                seen.add(parent)
                pending.extend(parents[parent] - seen)
        return seen
    physical = {}
    for item in events:
        row = dict(item)
        data = json.loads(row["data_json"])
        if row["kind"] == "item_completed" and data.get("type") not in TOOL_TYPES:
            continue
        row["data"] = data
        row["refs"] = [row["record_id"]]
        identity = (row.get("source_id"), row.get("byte_start"), row.get("digest")) if row.get("source_id") is not None else (row["record_id"],)
        previous = physical.get(identity)
        if previous:
            refs = previous["refs"] + row["refs"]
            if (row.get("parser_version", 0), row["record_id"]) > (previous.get("parser_version", 0), previous["record_id"]):
                physical[identity] = row
            physical[identity]["refs"] = refs
        else:
            physical[identity] = row
        if data.get("parent"):
            parents[row["session_id"]].add(data["parent"])
    native_groups = defaultdict(list)
    for row in physical.values():
        native_groups[row.get("native_id") or f"unknown-record:{row['record_id']}"] .append(row)
    groups = defaultdict(list)
    ancestor_cache = {}
    def cached_ancestors(session):
        if session not in ancestor_cache:
            ancestor_cache[session] = ancestors(session)
        return ancestor_cache[session]
    for native, rows in native_groups.items():
        owners = {r.get("session_id") for r in rows}
        for row in rows:
            owner = row.get("session_id")
            candidates = cached_ancestors(owner) & owners
            # Merge cross-thread copies only along an observed ancestry chain.
            roots = [candidate for candidate in candidates if not (cached_ancestors(candidate) & candidates)]
            if len(roots) == 1:
                owner = roots[0]
            groups[(owner, native)].append(row)
    facts = []
    for (owner, native), rows in groups.items():
        rows.sort(key=lambda r: (r.get("timestamp") or "", r["record_id"]))
        calls = [r for r in rows if r["kind"] == "tool_call"]
        items = [r for r in rows if r["kind"] == "item_completed"]
        outputs = [r for r in rows if r["kind"] == "tool_output"]
        representative = calls[0] if calls else items[-1] if items else rows[0]
        data = representative["data"]
        name = data.get("name") or data.get("tool") or {"commandExecution": "exec_command", "fileChange": "apply_patch"}.get(data.get("type"), data.get("type")) or "unknown_tool"
        namespace = data.get("namespace") or data.get("server")
        if namespace and not name.startswith(namespace + "."):
            name = namespace + "." + name
        status = "pending" if calls else "unknown"
        duration = None
        for row in outputs + items:
            value = row["data"]
            if value.get("explicit_error") or value.get("success") is False or value.get("status") in ("failed", "error") or type(value.get("exitCode")) is int and value["exitCode"] != 0:
                status = "failed"
            elif value.get("success") is True or value.get("exitCode") == 0 or value.get("status") in ("completed", "succeeded"):
                status = "succeeded"
            if isinstance(value.get("durationMs"), (int, float)) and value["durationMs"] >= 0:
                duration = value["durationMs"]
        if status in ("unknown", "pending") and outputs:
            status = "unknown_outcome"
        argument = next((r["data"]["argument_size"] for r in calls + items if r["data"].get("argument_size", {}).get("bytes") is not None), {})
        projection_results = [r for r in items if r["data"].get("result_size", {}).get("bytes") is not None]
        if projection_results:
            result = projection_results[-1]["data"]["result_size"]
            chunks = 1
        elif outputs:
            # Copies in multiple rollouts do not multiply async chunks. Use the
            # source with the complete observed output sequence, flag alternatives.
            by_source = defaultdict(list)
            for row in outputs:
                by_source[row.get("source_id", "fixture")].append(row)
            chosen = max(by_source.values(), key=lambda group: (len(group), max(r["record_id"] for r in group)))
            sizes = [r["data"].get("result_size", {}) for r in chosen]
            result = {metric: sum(s[metric] for s in sizes) if all(s.get(metric) is not None for s in sizes) else None for metric in ("bytes", "tokens", "characters")}
            result.update(method=sizes[0].get("method", "unknown"), completeness="partial" if any(s.get("completeness") == "partial" for s in sizes) else "retained_content")
            chunks = len(chosen)
        else:
            result, chunks = {}, 0
        pattern = next((r["data"] for r in calls + items if r["data"].get("pattern_hash")), {})
        completed = max((r.get("timestamp") for r in items + outputs if r.get("timestamp")), default=None)
        start = calls[0].get("timestamp") if calls else representative.get("timestamp")
        parent_native = data.get("parent_call_id") or data.get("parentCallId")
        opaque = name in ("functions.exec", "exec")
        reads = {p["pattern_hash"]: p for r in items for p in r["data"].get("read_patterns", []) if p.get("pattern_hash")}
        facts.append(dict(id=key(owner, native), session_id=owner, native_id=native, turn_id=representative.get("turn_id"), name=name,
            timestamp=start, completed_at=completed, status=status, duration_ms=duration, wall_ms=elapsed(start, completed) if calls else None,
            argument_bytes=argument.get("bytes"), result_bytes=result.get("bytes"), argument_tokens=argument.get("tokens"), result_tokens=result.get("tokens"),
            estimate_method=result.get("method", "unknown"), completeness=result.get("completeness", "unknown"),
            pattern_hash=pattern.get("pattern_hash"), pattern_kind=pattern.get("pattern_kind"),
            level="child" if parent_native else "outer_opaque" if opaque else "observed", parent_id=key(owner, parent_native) if parent_native else None,
            coverage="nested_unobserved" if opaque else "missing_native_identity" if native.startswith("unknown-record:") else "observed",
            details_json=json.dumps(dict(argument=argument, result=result, output_chunks=chunks, timing="explicit_execution_and_separate_observed_wall", pattern_version=pattern.get("pattern_version"), read_patterns=list(reads.values()))),
            model=representative.get("model"), project=representative.get("project"),
            refs=sorted({ref for r in rows for ref in r["refs"]})))
    return facts


def rebuild_tools(connection, sessions=None, retry_window_seconds=600):
    scope = sorted(set(sessions)) if sessions is not None else None
    if scope == []:
        return dict(invocations=0)
    query = """SELECT e.*,r.byte_start,r.digest,r.parser_version,g.source_id FROM normalized_events e INDEXED BY normalized_session_kind
        JOIN source_records r ON r.id=e.record_id JOIN source_generations g ON g.id=r.generation_id
        WHERE e.kind IN ('tool_call','tool_output','item_completed') AND
        ((r.table_name IS NOT NULL AND r.superseded=0) OR EXISTS(SELECT 1 FROM record_interpretations i WHERE i.record_id=r.id))"""
    edges = [(r[0], r[1]) for r in connection.execute("SELECT DISTINCT parent_id,child_id FROM session_edges")]
    for row in connection.execute("SELECT e.session_id,e.data_json FROM normalized_events e JOIN record_interpretations i ON i.record_id=e.record_id WHERE e.kind='session_meta'"):
        data = json.loads(row["data_json"])
        if data.get("parent"):
            edges.append((data["parent"], row["session_id"]))
    graph = defaultdict(set)
    for parent, child in edges:
        graph[parent].add(child)
        graph[child].add(parent)
    remaining = set(scope) if scope is not None else {r[0] for r in connection.execute("SELECT DISTINCT session_id FROM normalized_events WHERE kind IN ('tool_call','tool_output','item_completed')")}
    components = []
    while remaining:
        seed = remaining.pop()
        component, pending = {seed}, [seed]
        while pending:
            node = pending.pop()
            for related in graph[node] & remaining:
                remaining.remove(related)
                component.add(related)
                pending.append(related)
        components.append(component)
    facts = []
    for component in components:
        ids = [s for s in component if s is not None]
        conditions = ["e.session_id IN (" + ",".join("?" for _ in ids) + ")"] if ids else []
        if None in component:
            conditions.append("e.session_id IS NULL")
        facts.extend(build_tools(connection.execute(query + " AND (" + " OR ".join(conditions) + ")", ids), edges))
    delete_clause = " WHERE session_id IN (" + ",".join("?" for _ in scope) + ")" if scope else ""
    connection.execute("DELETE FROM tool_calls" + delete_clause, scope or [])
    if facts:
        columns = [k for k in facts[0] if k != "refs"]
        connection.executemany("INSERT INTO tool_calls(" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", (tuple(f[k] for k in columns) for f in facts))
        connection.executemany("INSERT INTO tool_sources VALUES (?,?)", ((f["id"], ref) for f in facts for ref in f["refs"]))
    last = {}
    for f in sorted(facts, key=lambda row: (row.get("timestamp") or "", row["id"])):
        patterns = json.loads(f["details_json"]).get("read_patterns", [])
        if f["pattern_hash"]:
            patterns.append(dict(pattern_hash=f["pattern_hash"], pattern_kind=f["pattern_kind"] or "exact_arguments"))
        for pattern in {p["pattern_hash"]:p for p in patterns}.values():
            group = (f["session_id"], pattern["pattern_hash"])
            previous = last.get(group)
            delta = elapsed(previous["timestamp"], f["timestamp"]) if previous else None
            retry = bool(previous and previous["status"] == "failed" and delta is not None and delta <= retry_window_seconds * 1000)
            connection.execute("INSERT INTO pattern_occurrences VALUES (?,?,?,?,?)", (pattern["pattern_hash"], f["id"], pattern["pattern_kind"], int(retry), previous["id"] if previous else None))
            last[group] = f
    connection.commit()
    return dict(invocations=len(facts), statuses=[dict(r) for r in connection.execute("SELECT status,count(*) AS calls FROM tool_calls GROUP BY status")])
