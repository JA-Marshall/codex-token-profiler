import hashlib
import json
from pathlib import Path

import pytest

from codex_token_profiler.config import Config
from codex_token_profiler.db import connect, writer_lock
from codex_token_profiler.discovery import discover
from codex_token_profiler.ingest import import_sources, ingest_file, register


def envelope(kind="session_meta", **payload):
    return json.dumps(dict(type=kind, timestamp="2026-09-01T00:00:00Z", payload=payload), ensure_ascii=False).encode() + b"\n"


@pytest.fixture
def corpus(tmp_path):
    config = Config.resolve(tmp_path / "home", tmp_path / "data")
    (config.codex_home / "sessions").mkdir(parents=True)
    (config.codex_home / "archived_sessions").mkdir()
    path = config.codex_home / "sessions" / "test.jsonl"
    path.write_bytes(envelope(id="s", cwd="C:/synthetic"))
    db = connect(config.data_dir)
    yield config, path, db
    db.close()


def count(db, table="source_records"):
    return db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_idempotency_and_readonly(corpus):
    config, path, db = corpus
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    first = import_sources(db, config)
    second = import_sources(db, config)
    assert first["records"] == 1 and second["records"] == 0
    assert second["skipped"] == 1 and count(db) == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert db.execute("SELECT record_id FROM normalized_events").fetchone()[0] == 1


def test_malformed_unknown_and_partial_utf8(corpus):
    config, path, db = corpus
    first = path.read_bytes()
    partial = envelope("turn_context", turn_id="t", model="synthetic-é")
    cut = partial.index("é".encode()) + 1
    path.write_bytes(first + b"bad json\nnull\n" + partial[:cut])
    report = import_sources(db, config)
    assert report["errors"] == 2 and report["pending"] == 1
    assert db.execute("SELECT byte_offset FROM checkpoints").fetchone()[0] == len(first) + len(b"bad json\nnull\n")
    with path.open("ab") as out:
        out.write(partial[cut:])
    assert import_sources(db, config)["records"] == 1
    assert count(db) == 4


def test_oversized_line_continues(corpus, monkeypatch):
    config, path, db = corpus
    monkeypatch.setattr("codex_token_profiler.ingest.MAX_RECORD", 256)
    with path.open("ab") as out:
        out.write(b"x" * 400 + b"\n" + envelope("turn_context", turn_id="t"))
    report = import_sources(db, config)
    assert report["records"] == 3 and report["errors"] == 1
    assert count(db, "normalized_events") == 2


@pytest.mark.parametrize("stage,expected", [("before_commit", 0), ("after_commit", 1)])
def test_atomic_checkpoint_crash(corpus, stage, expected):
    config, path, db = corpus
    source = next(s for s in discover(config, False)["sources"] if s["kind"] == "rollout")
    source_id = register(db, source)
    db.commit()
    def crash(point):
        if point == stage:
            raise RuntimeError("synthetic crash")
    with pytest.raises(RuntimeError):
        ingest_file(db, source, source_id, "salt", fault=crash)
    db.rollback()
    assert count(db) == expected
    import_sources(db, config)
    assert count(db) == 1


@pytest.mark.parametrize("mode", ["truncate", "replace", "same_size_middle"])
def test_generation_rewrites_preserve_old_evidence(corpus, mode):
    config, path, db = corpus
    if mode == "same_size_middle":
        with path.open("ab") as out:
            out.write(envelope("turn_context", turn_id="a") * 200)
    import_sources(db, config)
    old_count = count(db)
    if mode == "truncate":
        path.write_bytes(envelope(id="x"))
    elif mode == "replace":
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(envelope(id="x"))
        replacement.replace(path)
    else:
        data = bytearray(path.read_bytes())
        index = data.index(b'"a"', len(data) // 2)
        data[index + 1] = ord("b")
        path.write_bytes(data)
    result = import_sources(db, config, full=True)
    assert result["failed"] == 0
    assert count(db, "source_generations") == 2
    assert count(db) > old_count
    assert db.execute("SELECT superseded FROM source_generations ORDER BY id").fetchone()[0] == 1


def test_archive_move_preserves_physical_provenance(corpus):
    config, path, db = corpus
    import_sources(db, config)
    path.rename(config.codex_home / "archived_sessions" / path.name)
    import_sources(db, config)
    assert count(db) == 2  # physical copies; M3 canonical facts must merge these
    assert db.execute("SELECT count(*) FROM sources WHERE disposition='unavailable'").fetchone()[0] >= 1


def test_payload_privacy(corpus):
    config, path, db = corpus
    secret = "synthetic-secret-do-not-store"
    with path.open("ab") as out:
        out.write(envelope("response_item", type="function_call", call_id="c", name="exec_command", arguments=secret))
        out.write(envelope("response_item", type="function_call_output", call_id="c", output=secret))
    import_sources(db, config)
    assert secret not in "\n".join(db.iterdump())


def test_writer_lock_excludes_second_writer(corpus):
    config, path, db = corpus
    with writer_lock(config.data_dir):
        with pytest.raises(RuntimeError, match="already running"):
            with writer_lock(config.data_dir):
                pass


def test_final_line_requires_explicit_stable_finalization(corpus):
    config, path, db = corpus
    with path.open("ab") as out:
        out.write(envelope("turn_context", turn_id="t").rstrip(b"\n"))
    assert import_sources(db, config, finalized_sources=[path])["pending"] == 1
    assert import_sources(db, config)["pending"] == 1
    report = import_sources(db, config, finalized_sources=[path])
    assert report["pending"] == 0 and report["records"] == 1
    assert import_sources(db, config)["records"] == 0


def test_bad_identity_shape_does_not_poison_following_records(corpus):
    config, path, db = corpus
    with path.open("ab") as out:
        out.write(envelope(id={"unexpected": "private"}))
        out.write(envelope("turn_context", turn_id="t"))
    report = import_sources(db, config)
    assert report["failed"] == 0 and report["errors"] == 1
    assert db.execute("SELECT session_id FROM normalized_events ORDER BY id DESC LIMIT 1").fetchone()[0] == "s"


def test_inaccessible_file_recovers_without_abandoning_other_files(corpus, monkeypatch):
    config, path, db = corpus
    second = path.with_name("other.jsonl")
    second.write_bytes(envelope(id="other"))
    original_open = Path.open
    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError("synthetic denied")
        return original_open(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", denied)
        report = import_sources(db, config)
        assert report["failed"] == 1 and report["records"] == 1
    assert import_sources(db, config)["records"] == 1
    assert count(db) == 2


def test_batch_crash_preserves_full_prefix_fingerprint(corpus, monkeypatch):
    config, path, db = corpus
    monkeypatch.setattr("codex_token_profiler.ingest.BATCH_RECORDS", 100)
    path.write_bytes(envelope(id="s") + envelope("turn_context",turn_id="a") * 150)
    source = next(s for s in discover(config,False)["sources"] if s["kind"] == "rollout")
    source_id = register(db,source)
    db.commit()
    def crash(stage):
        if stage == "after_commit":
            raise RuntimeError("synthetic batch crash")
    with pytest.raises(RuntimeError):
        ingest_file(db,source,source_id,"salt",fault=crash)
    offset, digest = db.execute("SELECT byte_offset,content_hash FROM checkpoints").fetchone()
    assert digest == hashlib.sha256(path.read_bytes()[:offset]).hexdigest()
    original = bytearray(path.read_bytes())
    position = original.index(b'"a"',4500)
    original[position+1] = ord("b")
    path.write_bytes(original)
    assert import_sources(db,config,full=True)["failed"] == 0
    assert count(db,"source_generations") == 2
