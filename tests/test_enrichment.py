import json
from pathlib import Path
import sqlite3

from codex_token_profiler.config import Config
from codex_token_profiler.db import connect
from codex_token_profiler.ingest import import_sources
from codex_token_profiler.sources.history import item_metrics


def test_duration_adapter_and_privacy():
    raw = dict(type="CommandExecution", id="c", aggregated_output="synthetic secret", command="synthetic private command", exit_code=0, duration=dict(secs=1, nanos=250000000))
    projected = dict(type="commandExecution", id="c", aggregatedOutput="synthetic secret", command="synthetic private command", exitCode=0, durationMs=1250)
    assert item_metrics(raw, "salt") == item_metrics(projected, "salt")
    assert "private command" not in json.dumps(item_metrics(raw, "salt"))
    assert "synthetic secret" not in json.dumps(item_metrics(projected, "salt"))


def test_live_wal_mutable_projection_and_db_only(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = Config.resolve(home, tmp_path / "data")
    writer = sqlite3.connect(home / "thread_history_1.sqlite")
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE thread_items(thread_id TEXT,item_id TEXT,item_json TEXT,updated_at_ordinal INTEGER)")
    item = dict(type="commandExecution", id="c", command="synthetic command", status="inProgress")
    writer.execute("INSERT INTO thread_items VALUES ('db-only','c',?,1)", (json.dumps(item),))
    writer.commit()
    db = connect(config.data_dir)
    try:
        assert import_sources(db, config)["failed"] == 0
        session = db.execute("SELECT * FROM sessions WHERE id='db-only'").fetchone()
        assert session["reported_state_tokens"] is None
        assert db.execute("SELECT count(*) FROM normalized_events").fetchone()[0] == 1
        assert import_sources(db, config)["records"] == 0
        item.update(status="completed", exitCode=0, durationMs=0, aggregatedOutput="synthetic output")
        writer.execute("UPDATE thread_items SET item_json=?,updated_at_ordinal=2", (json.dumps(item),))
        writer.commit()
        assert import_sources(db, config)["records"] == 1
        assert db.execute("SELECT count(*) FROM source_records WHERE superseded=0").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM source_records WHERE superseded=1").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM normalized_events WHERE kind LIKE '%usage%'").fetchone()[0] == 0
        assert "synthetic output" not in "\n".join(db.iterdump())
    finally:
        db.close()
        writer.close()


def test_bad_schema_reported_without_abandoning_other_sources(tmp_path):
    home = tmp_path / "home"
    (home / "sessions").mkdir(parents=True)
    (home / "sessions/a.jsonl").write_text('{"type":"session_meta","payload":{"id":"ok"}}\n')
    with sqlite3.connect(home / "thread_history_1.sqlite") as writer:
        writer.execute("CREATE TABLE thread_items(unsupported TEXT)")
    db = connect(tmp_path / "data")
    try:
        report = import_sources(db, Config.resolve(home, tmp_path / "data"))
        assert report["failed"] == 1
        assert db.execute("SELECT id FROM sessions WHERE id='ok'").fetchone()
    finally:
        db.close()


def test_replaced_database_retains_history_with_new_generation(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    path = home / "state_5.sqlite"
    def create(target, thread_id):
        with sqlite3.connect(target) as writer:
            writer.execute("CREATE TABLE threads(id TEXT,tokens_used INTEGER)")
            writer.execute("INSERT INTO threads VALUES (?,10)", (thread_id,))
        writer.close()
    create(path, "old")
    config = Config.resolve(home, tmp_path / "data")
    db = connect(config.data_dir)
    try:
        import_sources(db, config)
        replacement = home / "replacement.tmp"
        create(replacement, "new")
        replacement.replace(path)
        import_sources(db, config)
        assert db.execute("SELECT count(*) FROM source_generations").fetchone()[0] == 2
        assert {r[0] for r in db.execute("SELECT id FROM sessions")} == {"old", "new"}
    finally:
        db.close()
