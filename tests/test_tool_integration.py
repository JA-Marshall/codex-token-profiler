import json

from codex_token_profiler.config import Config
from codex_token_profiler.db import connect
from codex_token_profiler.ingest import import_sources
from codex_token_profiler.tools import rebuild_tools
from .fixtures.families import record


def test_failure_followed_by_same_command_and_read_is_likely_retry(tmp_path):
    config = Config.resolve(tmp_path / "home", tmp_path / "data")
    folder = config.codex_home / "sessions"
    folder.mkdir(parents=True)
    records = [record("session_meta", dict(id="s"))]
    for i, code in enumerate((1,0)):
        native = f"c{i}"
        records.append(record("response_item",dict(type="function_call",call_id=native,name="exec_command",arguments='{"cmd":"cat private-path"}'),i*2+1))
        records.append(record("event_msg",dict(type="item_completed",item=dict(type="CommandExecution",id=native,command="cat private-path",exit_code=code,command_actions=[dict(type="read",path="private-path",command="cat private-path")])),i*2+2))
    (folder / "s.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records))
    db = connect(config.data_dir)
    try:
        import_sources(db,config)
        assert rebuild_tools(db)["invocations"] == 2
        assert db.execute("SELECT count(DISTINCT tool_id) FROM pattern_occurrences WHERE likely_retry=1").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM pattern_occurrences WHERE kind='exact_read_and_range'").fetchone()[0] == 2
        before = list(db.execute("SELECT id,result_bytes,status FROM tool_calls ORDER BY id"))
        import_sources(db,config)
        rebuild_tools(db)
        assert [tuple(x) for x in before] == [tuple(x) for x in db.execute("SELECT id,result_bytes,status FROM tool_calls ORDER BY id")]
        assert "private-path" not in "\n".join(db.iterdump())
        rebuild_tools(db, retry_window_seconds=1)
        assert db.execute("SELECT count(*) FROM pattern_occurrences WHERE likely_retry=1").fetchone()[0] == 0
    finally:
        db.close()
