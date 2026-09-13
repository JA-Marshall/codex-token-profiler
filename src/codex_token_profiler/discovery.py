"""Sanitized inventory: no conversation bodies or configuration values are retained."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

from .config import canonical, local_path
from .sources.sqlite import readonly, schema


def discover(config, versions=True):
    found = {}
    diagnostics = []

    def add(path, kind, disposition, reason):
        key = canonical(path)
        if key in found:
            return found[key]
        item = dict(path=str(path), canonical_path=key, kind=kind, disposition=disposition, reason=reason)
        try:
            stat = path.stat()
            item.update(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, file_id=f"{stat.st_dev}:{stat.st_ino}")
        except OSError as exc:
            item.update(disposition="unavailable", error=type(exc).__name__)
        found[key] = item
        return item

    def walk(root, suffixes, kind, disposition, reason):
        if not root.exists():
            add(root, kind, "unavailable", "source root missing")
            return
        def failed(exc):
            diagnostics.append(dict(path=exc.filename, error=type(exc).__name__))
        for parent, dirs, files in os.walk(root, onerror=failed, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(parent) / d).is_symlink()]
            for name in files:
                if Path(name).suffix.lower() in suffixes:
                    add(Path(parent) / name, kind, disposition, reason)

    for root in [config.codex_home / "sessions", config.codex_home / "archived_sessions", *config.extra_roots]:
        walk(root, {".jsonl"}, "rollout", "eligible", "primary history")
    for root in set([config.codex_home, config.sqlite_home or config.codex_home, config.codex_home / "sqlite"]):
        try:
            paths = list(root.iterdir())
        except OSError as exc:
            diagnostics.append(dict(path=str(root), error=type(exc).__name__))
            continue
        for path in paths:
            if path.suffix not in (".sqlite", ".db"):
                continue
            name = path.name
            kind = "state" if name.startswith("state_") else "history" if name.startswith("thread_history_") else "catalog" if name == "codex-dev.db" else "logs" if name.startswith("logs_") else "excluded_database"
            disposition = "eligible" if kind in ("state", "history", "catalog") else "diagnostic_only" if kind == "logs" else "excluded"
            item = add(path, kind, disposition, "metadata/projection" if disposition == "eligible" else "not independent usage; bodies not retained")
            if kind == "excluded_database":
                continue
            try:
                with readonly(path) as connection:
                    tables = schema(connection)
                    item["schema"] = {name: [c["name"] for c in cols] for name, cols in tables.items()}
                    item["schema_signature"] = hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest()
                    if kind == "state" and "threads" in tables:
                        columns = item["schema"]["threads"]
                        item["thread_count"] = connection.execute("SELECT count(*) FROM threads").fetchone()[0]
                        if "rollout_path" in columns:
                            for row in connection.execute("SELECT rollout_path FROM threads WHERE rollout_path IS NOT NULL"):
                                value = row[0]
                                if "://" in value or value.startswith("\\\\") and not value.startswith("\\\\?\\C:"):
                                    diagnostics.append(dict(kind="remote_reference", disposition="unavailable"))
                                else:
                                    add(local_path(value), "rollout", "eligible", "state catalog reference")
            except Exception as exc:
                item.update(disposition="failed", error=type(exc).__name__)
    add(config.codex_home / "session_index.jsonl", "session_index", "eligible", "metadata fallback; titles not retained")
    log_roots = [config.log_dir] if config.log_dir else []
    packages = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Packages"
    log_roots.extend(packages.glob("OpenAI.Codex_*/LocalCache/Local/Codex/Logs"))
    for root in log_roots:
        walk(root, {".log", ".jsonl"}, "desktop_log", "diagnostic_only", "no established additive usage; no body retention")
    result = dict(created_at=datetime.now(timezone.utc).isoformat(), codex_home=str(config.codex_home), sources=list(found.values()), diagnostics=diagnostics, telemetry_configured=config.telemetry_configured, config_error=config.config_error)
    if versions:
        executable = shutil.which("codex")
        result["cli_executable"] = executable
        if executable:
            try:
                result["cli_version"] = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
            except (OSError, subprocess.TimeoutExpired) as exc:
                result["cli_version_error"] = type(exc).__name__
    result["counts"] = dict(Counter(s["disposition"] for s in found.values()))
    return result
