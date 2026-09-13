import json
from pathlib import Path
import sqlite3

import pytest

from codex_token_profiler.config import Config, canonical
from codex_token_profiler.discovery import discover
from codex_token_profiler.inspection import inspect_inventory
from codex_token_profiler.sources.sqlite import readonly


def test_windows_aliases():
    assert canonical(r"\\?\C:\Users\Test\sessions\a.jsonl") == canonical("c:/users/test/sessions/a.jsonl")
    assert canonical(r"\\?\UNC\server\share\a") == canonical(r"\\server\share\a")


def test_source_destination_guard(tmp_path):
    with pytest.raises(ValueError):
        Config.resolve(tmp_path, tmp_path / "output")
    with pytest.raises(ValueError):
        Config.resolve(tmp_path / "home", tmp_path / "extra/data", [tmp_path / "extra"])


def test_missing_sources_and_invalid_config(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("bad = [")
    result = discover(Config.resolve(home, tmp_path / "data"), versions=False)
    assert result["config_error"] == "TOMLDecodeError"
    assert sum(s["disposition"] == "unavailable" for s in result["sources"]) >= 3


def test_readonly_wal_and_optional_columns(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    path = home / "state_5.sqlite"
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE threads(id TEXT)")
    writer.execute("INSERT INTO threads VALUES ('synthetic')")
    writer.commit()
    with readonly(path) as reader:
        assert reader.execute("SELECT id FROM threads").fetchone()[0] == "synthetic"
        with pytest.raises(sqlite3.OperationalError):
            reader.execute("DELETE FROM threads")
    result = discover(Config.resolve(home, tmp_path / "data"), versions=False)
    source = next(s for s in result["sources"] if s["kind"] == "state")
    assert source["thread_count"] == 1
    assert source["disposition"] == "eligible"
    writer.close()


def test_inspection_numeric_only_and_partial(tmp_path):
    home = tmp_path / "home"
    sessions = home / "sessions"
    sessions.mkdir(parents=True)
    path = sessions / "fixture.jsonl"
    records = [
        {"type": "session_meta", "payload": {"id": "s", "cli_version": "synthetic", "private": "DO_NOT_RETAIN"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 12, "output_tokens": 3}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 2, "output_tokens": 1}}}},
    ]
    original = b"".join(json.dumps(r).encode() + b"\n" for r in records) + b'{"partial":'
    path.write_bytes(original)
    result = inspect_inventory(discover(Config.resolve(home, tmp_path / "data"), versions=False))
    assert len(result["decreases"]) == 1
    assert result["files"][0]["pending_bytes"] == 11
    assert "DO_NOT_RETAIN" not in json.dumps(result)
    assert path.read_bytes() == original
