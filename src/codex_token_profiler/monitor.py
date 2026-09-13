"""Single-writer polling with fast append ingestion and periodic reconciliation."""
import json
import os
from pathlib import Path
import time

from .accounting import reconcile
from .db import now
from .estimates import configure
from .ingest import import_sources, ingest_file
from .tools import rebuild_tools


def related_sessions(connection, sessions):
    selected = {s for s in sessions if s is not None}
    if not selected:
        return selected
    edges = [(r[0],r[1]) for r in connection.execute("SELECT DISTINCT parent_id,child_id FROM session_edges")]
    changed = True
    while changed:
        changed = False
        for parent, child in edges:
            if (parent in selected or child in selected) and not {parent,child} <= selected:
                selected.update((parent,child))
                changed = True
    return selected


class Monitor:
    def __init__(self, connection, config, retry_window=600):
        self.connection, self.config = connection, config
        self.retry_window = retry_window
        self.known = {}
        self.signature_cache = {}
        self.state = dict(status="starting", last_success=None, last_reconcile=None, records=0, failed=0, pending_bytes=0, startup_at_login=False, telemetry=False)
        configure(config.data_dir)

    def refresh_known(self):
        previous = self.known
        self.known = {}
        for row in self.connection.execute("SELECT id,original_path,canonical_path,kind FROM sources WHERE kind IN ('rollout','session_index')"):
            source = dict(row)
            if Path(source["original_path"]).suffix.lower() != ".jsonl":
                continue
            source["path"] = source.pop("original_path")
            source["disposition"] = "eligible"
            source["signature"] = previous.get(source["id"], {}).get("signature")
            source["retry_at"] = previous.get(source["id"], {}).get("retry_at", 0)
            self.known[source["id"]] = source

    def update_derived(self, previous_id, full=False):
        # NOT INDEXED prevents DISTINCT from choosing a full session-index scan
        # over the cheap integer-primary-key range for the usually empty tail.
        sessions = None if full else related_sessions(self.connection, [r[0] for r in self.connection.execute("SELECT DISTINCT session_id FROM normalized_events NOT INDEXED WHERE id>?", (previous_id,))])
        if sessions == set():
            return
        reconcile(self.connection, sessions)
        rebuild_tools(self.connection, sessions, self.retry_window)

    def scan(self, full=False, initial=False):
        before = self.connection.execute("SELECT coalesce(max(id),0) FROM normalized_events").fetchone()[0]
        report = import_sources(self.connection, self.config, full=full,signature_cache=self.signature_cache)
        self.update_derived(before, full=initial)
        self.refresh_known()
        self.state.update(records=self.state["records"] + report["records"], failed=report["failed"], last_success=now())
        if full:
            self.state["last_reconcile"] = now()
        self.health()
        return report

    def poll(self):
        before = self.connection.execute("SELECT coalesce(max(id),0) FROM normalized_events").fetchone()[0]
        salt = self.connection.execute("SELECT value FROM settings WHERE key='pattern_salt'").fetchone()[0]
        for source in self.known.values():
            if time.monotonic() < source["retry_at"]:
                continue
            try:
                stat = os.stat(source["path"])
                signature = (stat.st_ino,stat.st_size,stat.st_mtime_ns)
                if signature == source["signature"]:
                    continue
                report = ingest_file(self.connection,source,source["id"],salt)
                source["signature"] = signature
                self.state["records"] += report["records"]
            except Exception as exc:
                self.connection.rollback()
                source["retry_at"] = time.monotonic() + 30
                disposition = "unavailable" if isinstance(exc,FileNotFoundError) else "failed"
                self.connection.execute("UPDATE sources SET disposition=?,error=? WHERE id=?", (disposition,type(exc).__name__,source["id"]))
                self.connection.commit()
        self.update_derived(before)
        self.state["last_success"] = now()
        self.health()

    def health(self):
        self.state["failed"] = self.connection.execute("SELECT count(*) FROM sources WHERE disposition='failed'").fetchone()[0]
        self.state["pending_bytes"] = self.connection.execute("SELECT coalesce(sum(c.pending_bytes),0) FROM checkpoints c JOIN source_generations g ON g.id=c.generation_id WHERE g.superseded=0").fetchone()[0]
        self.state["status"] = "degraded" if self.state["failed"] else "running"
