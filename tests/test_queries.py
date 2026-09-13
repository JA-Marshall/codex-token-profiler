import json

from codex_token_profiler.accounting import reconcile
from codex_token_profiler.config import Config
from codex_token_profiler.db import connect
from codex_token_profiler.ingest import import_sources
from codex_token_profiler.queries import usage_summary
from .fixtures.families import record, usage


def test_descendants_are_unique_even_with_cycles_and_unknown_stays_null(tmp_path):
    config = Config.resolve(tmp_path / "home", tmp_path / "data")
    folder = config.codex_home / "sessions"
    folder.mkdir(parents=True)
    for session, parent in (("root",None),("child","root"),("grandchild","child")):
        records = [record("session_meta",dict(id=session,parent_thread_id=parent)),record("event_msg",dict(type="task_started",turn_id=session)),
                   record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(),last_token_usage=usage())),1)]
        (folder / f"{session}.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records))
    db = connect(config.data_dir)
    try:
        import_sources(db,config)
        reconcile(db)
        db.execute("INSERT INTO session_edges VALUES ('grandchild','root','synthetic_cycle',1)")
        own = usage_summary(db,"root")
        inclusive = usage_summary(db,"root",True)
        assert own["total_tokens"] == 120
        assert inclusive["total_tokens"] == 360 and inclusive["sessions_in_scope"] == 3
        unknown = usage_summary(db,"missing")
        assert unknown["total_tokens"] is None and unknown["total_tokens_known_facts"] == 0
    finally:
        db.close()
