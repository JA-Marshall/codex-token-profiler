"""Bounded, numeric/key-only format audit. Never emits message/tool payloads."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import time

from .sources.sqlite import readonly, schema

MAX_RECORD = 32 * 1024 * 1024


def inspect_inventory(inventory):
    started = time.perf_counter()
    families = defaultdict(Counter)
    versions = Counter()
    files = []
    decreases = []
    ids = defaultdict(list)
    rollout_ids = set()
    for source in inventory["sources"]:
        if source["kind"] != "rollout" or source["disposition"] != "eligible":
            continue
        report = dict(path=source["path"], records=0, usage_records=0, null_usage=0, repeats=0, errors=0, pending_bytes=0, first_timestamp=None, last_timestamp=None)
        previous = None
        previous_context = None
        context = dict(session=None, turn=None, model=None, parent=None, compactions=0)
        digest = hashlib.sha256()
        prefix = []
        try:
            with Path(source["path"]).open("rb") as stream:
                while True:
                    offset = stream.tell()
                    raw = stream.readline(MAX_RECORD + 1)
                    if not raw:
                        break
                    digest.update(raw)
                    if len(raw) > MAX_RECORD:
                        while raw and not raw.endswith(b"\n"):
                            raw = stream.readline(MAX_RECORD + 1)
                            digest.update(raw)
                        report["errors"] += 1
                        continue
                    if not raw.endswith(b"\n"):
                        report["pending_bytes"] = len(raw)
                        break
                    try:
                        record = json.loads(raw)
                        if not isinstance(record, dict):
                            raise ValueError()
                    except (ValueError, UnicodeError):
                        report["errors"] += 1
                        continue
                    report["records"] += 1
                    kind, payload = record.get("type"), record.get("payload")
                    payload = payload if isinstance(payload, dict) else {}
                    family = str(kind) + "/" + str(payload.get("type", ""))
                    families[family][",".join(sorted(payload))] += 1
                    timestamp = record.get("timestamp")
                    if isinstance(timestamp, str):
                        report["first_timestamp"] = min(report["first_timestamp"] or timestamp, timestamp)
                        report["last_timestamp"] = max(report["last_timestamp"] or timestamp, timestamp)
                    if kind == "session_meta":
                        context.update(session=payload.get("id"), parent=payload.get("parent_thread_id") or payload.get("forked_from_id"))
                        rollout_ids.add(payload.get("id"))
                        versions[str(payload.get("cli_version"))] += 1
                        if "first_session" not in report:
                            report["first_session"] = payload.get("id")
                    elif kind == "turn_context":
                        context.update(turn=payload.get("turn_id"), model=payload.get("model"))
                    elif kind == "compacted":
                        context["compactions"] += 1
                    elif kind == "event_msg" and payload.get("type") == "token_count":
                        info = payload.get("info")
                        if not isinstance(info, dict):
                            report["null_usage"] += 1
                            continue
                        total = info.get("total_token_usage")
                        if not isinstance(total, dict):
                            continue
                        total = {k: v for k, v in total.items() if isinstance(v, int) and not isinstance(v, bool)}
                        report["usage_records"] += 1
                        if previous == total:
                            report["repeats"] += 1
                        if previous and any(total[k] < previous[k] for k in total.keys() & previous.keys()):
                            last = info.get("last_token_usage")
                            last = {k: v for k, v in last.items() if isinstance(v, int) and not isinstance(v, bool)} if isinstance(last, dict) else None
                            evidence = "identity_change" if context["session"] != previous_context["session"] else "compaction_between" if context["compactions"] != previous_context["compactions"] else "new_turn_last_equals_total" if context["turn"] != previous_context["turn"] and total == last else "unexplained"
                            decreases.append(dict(path=source["path"], offset=offset, timestamp=timestamp, previous=previous, current=total, last=last, before_context=previous_context, context=dict(context), evidence=evidence, classification="unresolved_decrease"))
                        previous, previous_context = total, dict(context)
                    if len(prefix) < 100:
                        prefix.append(hashlib.sha256(raw).hexdigest())
                inspected_bytes = stream.tell()
            report.update(sha256=digest.hexdigest(), inspected_bytes=inspected_bytes)
        except OSError as exc:
            report["error"] = type(exc).__name__
        files.append(report)
        if report.get("first_session"):
            ids[report["first_session"]].append(dict(path=source["path"], sha256=report.get("sha256"), prefix=prefix))
    database_only = []
    projections = Counter()
    database_errors = []
    for source in inventory["sources"]:
        if source["kind"] != "history" or source["disposition"] != "eligible":
            continue
        try:
            with readonly(Path(source["path"])) as connection:
                tables = schema(connection)
                for table in ("thread_turns", "thread_items", "thread_realtime_items"):
                    columns = {r["name"] for r in tables.get(table, [])}
                    if "thread_id" in columns:
                        for row in connection.execute(f'SELECT DISTINCT thread_id FROM "{table}"'):
                            if row[0] not in rollout_ids:
                                database_only.append(dict(thread_id=row[0], table=table, usage=None))
                    if "item_json" in columns:
                        for row in connection.execute(f'SELECT item_json FROM "{table}"'):
                            try:
                                item = json.loads(row[0])
                                projections[str(item.get("type"))] += 1
                                families["projection/" + str(item.get("type"))][",".join(sorted(item))] += 1
                            except (ValueError, TypeError, AttributeError):
                                projections["malformed"] += 1
        except Exception as exc:
            database_errors.append(dict(path=source["path"], error=type(exc).__name__))
    return dict(seconds=time.perf_counter() - started, files=files, families={k: dict(v) for k, v in sorted(families.items())}, versions=dict(versions), decreases=decreases, duplicate_first_ids={k: v for k, v in ids.items() if len(v) > 1}, database_only=database_only, database_errors=database_errors, projection_types=dict(projections))
