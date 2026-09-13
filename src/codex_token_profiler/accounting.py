"""Reported-usage ledger. Estimates never enter this module.

Response IDs establish semantic identity. Legacy snapshots are reconciled as ordered
sequences inside an owning session, not globally deduplicated by numeric values.
Unproven baseline/reset/overlap attribution is retained as a coverage gap.
"""
from collections import defaultdict
from difflib import SequenceMatcher
import hashlib
import json

from .normalize import TOKEN_FIELDS

ACCOUNTING_VERSION = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def valid(usage):
    if not isinstance(usage, dict):
        return False
    if any(v is not None and (type(v) is not int or v < 0) for v in usage.values()):
        return False
    i, o, total = (usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens"))
    if None not in (i, o, total) and i + o != total:
        return False
    for child, parent in (("cached_input_tokens", "input_tokens"), ("reasoning_output_tokens", "output_tokens")):
        if usage.get(child) is not None and usage.get(parent) is not None and usage[child] > usage[parent]:
            return False
    return True


def subtract(a, b):
    return {k: a.get(k) - b.get(k) if a.get(k) is not None and b.get(k) is not None else None for k in TOKEN_FIELDS}


def sum_usage(rows):
    # An unknown component in any covered response prevents an exact residual.
    return {k: sum(r[k] for r in rows) if all(r.get(k) is not None for r in rows) else None for k in TOKEN_FIELDS}


def all_zero(value):
    return value is not None and all(value.get(k) == 0 for k in ("input_tokens", "output_tokens", "total_tokens"))


def build_ledger(observations):
    facts, gaps = {}, []
    responses = defaultdict(list)
    cumulative = defaultdict(lambda: defaultdict(list))
    physical = {}
    for original in observations:
        row = dict(original)
        key = (row["source_id"], row["byte_start"], row["digest"]) if "source_id" in row else (row["record_id"],)
        existing = physical.get(key)
        if existing:
            refs = existing["refs"] + [row["record_id"]]
            if (row.get("parser_version", 0), row["record_id"]) > (existing.get("parser_version", 0), existing["record_id"]):
                physical[key] = row
            physical[key]["refs"] = refs
        else:
            row["refs"] = [row["record_id"]]
            physical[key] = row

    def gap(row, code, **details):
        gaps.append(dict(id=digest([row.get("record_id"), code]), session_id=row.get("session_id"), record_id=row.get("record_id"), code=code, detail_json=json.dumps(details, sort_keys=True), accounting_version=ACCOUNTING_VERSION))

    for original in physical.values():
        row = dict(original)
        row["data"] = json.loads(row["data_json"])
        if row["kind"] == "response_usage":
            if row.get("native_id"):
                responses[row["native_id"]].append(row)
            else:
                gap(row, "missing_response_identity")
        else:
            cumulative[row["session_id"]][row["generation_id"]].append(row)

    def fact(row, usage, method, refs, interval_start=None, unallocated=False, key=None):
        if not valid(usage):
            gap(row, "invalid_usage_categories", method=method)
            return
        known = [v for v in usage.values() if v is not None]
        if not known:
            gap(row, "unknown_usage_categories", method=method)
            return
        fact_id = digest([row.get("session_id"), method, key if key is not None else row["record_id"]])
        values = {k: usage.get(k) for k in TOKEN_FIELDS}
        facts[fact_id] = dict(id=fact_id, session_id=row["session_id"], turn_id=None if unallocated else row.get("turn_id"), timestamp=None if unallocated else row.get("timestamp"), interval_start=interval_start, interval_end=row.get("timestamp"), model=None if unallocated else row.get("model"), project=None if unallocated else row.get("project"), method=method, accounting_version=ACCOUNTING_VERSION, coverage="partial_categories" if any(v is None for v in values.values()) else "reported", refs=list(set(refs)), **values)
        return fact_id

    response_by_session = defaultdict(list)
    for response_id, copies in responses.items():
        # Prefer the newest parser evidence, retaining all supporting locations.
        row = max(copies, key=lambda x: x["record_id"])
        signatures = {digest([r["session_id"], r["data"].get("usage")]) for r in copies}
        if len(signatures) != 1:
            for copy in copies:
                gap(copy, "conflicting_response_usage", response_id=response_id)
            continue
        if len({r.get("model") for r in copies if r.get("model")}) > 1:
            row["model"] = None
        usage = row["data"].get("usage")
        key = fact(row, usage, "reported_response", [ref for r in copies for ref in r["refs"]], key=response_id)
        if key:
            response_by_session[row["session_id"]].append((row, usage, key))

    for session_id, streams in cumulative.items():
        groups = [sorted(group, key=lambda r: r["ordinal"]) for group in streams.values()]
        groups.sort(key=lambda group: (not group[0].get("generation_superseded", 0), len(group), group[0]["record_id"]), reverse=True)
        chosen = groups[0]

        def signature(row):
            return digest([row["session_id"], row.get("turn_id"), row.get("timestamp"), row["data"].get("total_token_usage"), row["data"].get("last_token_usage")])

        for group in groups[1:]:
            matcher = SequenceMatcher(None, [signature(r) for r in chosen], [signature(r) for r in group], autojunk=False)
            matched = set()
            for block in matcher.get_matching_blocks():
                # Ordered sequence overlap or explicit native turn identity is required.
                same_physical = block.size == 1 and group[block.b].get("source_id") is not None and group[block.b].get("source_id") == chosen[block.a].get("source_id") and group[block.b].get("digest") == chosen[block.a].get("digest") and group[block.b].get("byte_start") == chosen[block.a].get("byte_start")
                if block.size == 1 and not group[block.b].get("turn_id") and not same_physical:
                    continue
                for step in range(block.size):
                    chosen[block.a + step]["refs"].extend(group[block.b + step]["refs"])
                    matched.add(block.b + step)
            lower = min((r.get("timestamp") for r in chosen if r.get("timestamp")), default=None)
            upper = max((r.get("timestamp") for r in chosen if r.get("timestamp")), default=None)
            extra = []
            for index, row in enumerate(group):
                if index in matched:
                    continue
                timestamp = row.get("timestamp")
                if timestamp and lower and upper and (timestamp < lower or timestamp > upper):
                    extra.append(row)
                else:
                    gap(row, "ambiguous_source_overlap")
            chosen.extend(extra)
            chosen.sort(key=lambda r: (r.get("timestamp") or "", r["ordinal"], r["record_id"]))

        previous = None
        uncertain_epoch = False
        session_responses = sorted(response_by_session[session_id], key=lambda x: (x[0].get("timestamp") or "", x[0]["record_id"]))
        response_cursor = -1
        thread_offset = {k: 0 for k in TOKEN_FIELDS}
        for row in chosen:
            total = row["data"].get("total_token_usage")
            if not valid(total):
                gap(row, "null_or_invalid_cumulative")
                continue
            inherited = bool(row["data"].get("parent")) and not row["data"].get("own_counter_origin")
            current_time = row.get("timestamp")
            before_time = previous.get("timestamp") if previous else None
            if session_responses and (not current_time or any(not r[0].get("timestamp") for r in session_responses)):
                gap(row, "unknown_response_interval")
                previous = row
                continue
            covering = [(r, u, key) for r, u, key in session_responses if r.get("timestamp") <= current_time and (not before_time or r.get("timestamp") > before_time)]
            response_sum = sum_usage([u for _, u, _ in covering])
            previous_total = previous["data"].get("total_token_usage") if previous else None
            delta = subtract(total, previous_total) if previous_total else total
            decreases = any(v is not None and v < 0 for v in delta.values())
            if decreases:
                uncertain_epoch = True
                gap(row, "unresolved_counter_decrease", previous_record=previous["record_id"], new_turn=row.get("turn_id") != previous.get("turn_id"), last_equals_total=row["data"].get("last_token_usage") == total)
            if all_zero(total):
                uncertain_epoch = False
                previous = row
                continue
            if inherited:
                gap(row, "inherited_cumulative_unallocated")
                previous = row
                continue
            if uncertain_epoch:
                # Exact response facts survive; no speculative legacy deltas after
                # an unexplained decrease that could have replayed prior history.
                if not covering or response_sum != total:
                    gap(row, "unresolved_epoch_interval")
                previous = row
                continue
            if session_responses:
                # Match the actual cumulative checkpoint. A legacy notification can
                # lag a response record, so timestamp windows alone are insufficient.
                target = subtract(total, thread_offset)
                matched_index = next((i for i, (r, _, _) in enumerate(session_responses)
                    if i >= response_cursor and r["data"].get("thread_token_usage") == target
                    and (r.get("timestamp") <= current_time or r.get("turn_id") == row.get("turn_id"))), None)
                if matched_index is not None:
                    covering = session_responses[response_cursor + 1:matched_index + 1]
                    response_cursor = matched_index
                    response_sum = sum_usage([u for _, u, _ in covering])
                elif covering and delta == response_sum:
                    # A legacy counter can retain a historical offset when the newer
                    # response counter starts. Exact component deltas establish it.
                    checkpoint = covering[-1][0]["data"].get("thread_token_usage")
                    if valid(checkpoint):
                        thread_offset = subtract(total, checkpoint)
                        response_cursor = max(i for i, (_, _, key) in enumerate(session_responses) if key == covering[-1][2])
                elif all(v in (0, None) for v in delta.values()):
                    previous = row
                    continue
                elif current_time >= session_responses[0][0].get("timestamp"):
                    gap(row, "response_checkpoint_mismatch")
                    previous = row
                    continue
            if covering:
                residual = subtract(delta, response_sum)
                if not valid(residual):
                    gap(row, "response_interval_mismatch")
                    previous = row
                    continue
            else:
                residual = delta
            refs = row["refs"] + (previous["refs"] if previous else []) + [r["record_id"] for r, _, _ in covering]
            if any(v not in (None, 0) for v in residual.values()) or not previous and not covering:
                unallocated = previous is None and not row["data"].get("own_counter_origin")
                mixed = previous and (previous.get("model") != row.get("model") or previous.get("project") != row.get("project"))
                attributed = dict(row)
                if mixed:
                    attributed["model"] = None
                    attributed["project"] = None
                fact(attributed, residual, "unallocated_historical" if unallocated else "reported_interval_residual" if covering else "reported_cumulative_delta", refs, before_time, unallocated, key=[signature(row), signature(previous) if previous else None])
            previous = row
    return list(facts.values()), gaps


def reconcile(connection, sessions=None):
    scope = sorted(set(sessions)) if sessions is not None else None
    if scope == []:
        return dict(updated_facts=0)
    clause = " WHERE session_id IN (" + ",".join("?" for _ in scope) + ")" if scope else ""
    observations = connection.execute("SELECT * FROM usage_observations" + clause + " ORDER BY generation_id,ordinal", scope or []).fetchall()
    # Projection turn coverage is incomplete and cannot override native rollout
    # ownership on its own. Replay boundaries are handled by the source adapter.
    facts, gaps = build_ledger(observations)
    connection.execute("DELETE FROM usage_facts" + clause, scope or [])
    connection.execute("DELETE FROM accounting_gaps" + clause, scope or [])
    columns = ("id", "session_id", "turn_id", "timestamp", "interval_start", "interval_end", "model", "project", "method", "accounting_version", *TOKEN_FIELDS, "coverage")
    connection.executemany("INSERT INTO usage_facts(" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", [tuple(f[k] for k in columns) for f in facts])
    connection.executemany("INSERT INTO fact_sources VALUES (?,?)", [(f["id"], r) for f in facts for r in f["refs"]])
    connection.executemany("INSERT INTO accounting_gaps VALUES (?,?,?,?,?,?)", [(g["id"], g["session_id"], g["record_id"], g["code"], g["detail_json"], g["accounting_version"]) for g in {g["id"]: g for g in gaps}.values()])
    connection.commit()
    return dict(facts=len(facts), gaps=len(gaps), known_subtotals={k: connection.execute(f"SELECT sum({k}) FROM usage_facts").fetchone()[0] for k in TOKEN_FIELDS}, methods=[dict(r) for r in connection.execute("SELECT method,count(*) AS facts FROM usage_facts GROUP BY method")], gap_types=[dict(r) for r in connection.execute("SELECT code,count(*) AS intervals FROM accounting_gaps GROUP BY code")])
