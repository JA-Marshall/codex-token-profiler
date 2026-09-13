import json

from codex_token_profiler.accounting import reconcile
from codex_token_profiler.audit import audit_sources
from codex_token_profiler.config import Config
from codex_token_profiler.db import connect
from codex_token_profiler.ingest import import_sources
from .fixtures.families import record, usage


def test_independent_oracle_detects_corrupted_ledger(tmp_path):
    config = Config.resolve(tmp_path / "home", tmp_path / "data")
    folder = config.codex_home / "sessions"
    folder.mkdir(parents=True)
    records = [record("session_meta", dict(id="s")), record("event_msg", dict(type="task_started", turn_id="t")),
               record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(), last_token_usage=usage())), 1)]
    (folder / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    db = connect(config.data_dir)
    try:
        import_sources(db, config)
        reconcile(db)
        assert audit_sources(db)["counts"] == {"exact": 1}
        db.execute("UPDATE usage_facts SET input_tokens=input_tokens+7,total_tokens=total_tokens+7")
        db.commit()
        assert audit_sources(db)["counts"] == {"mismatch": 1}
    finally:
        db.close()
