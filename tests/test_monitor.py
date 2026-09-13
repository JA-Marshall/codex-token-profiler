import json
import os

from codex_token_profiler.config import Config
from codex_token_profiler.db import connect
from codex_token_profiler.monitor import Monitor
from .test_lifecycle import initial, write_records
from .fixtures.families import record,usage


def test_monitor_partial_archive_move_and_truncation_do_not_inflate(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    active=config.codex_home/"sessions"
    archive=config.codex_home/"archived_sessions"
    active.mkdir(parents=True)
    archive.mkdir()
    path=active/"s.jsonl"
    write_records(path,initial())
    db=connect(config.data_dir)
    def total():
        return db.execute("SELECT sum(total_tokens) FROM usage_facts").fetchone()[0]
    try:
        monitor=Monitor(db,config)
        monitor.scan(initial=True)
        value=record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(130,30,50,7),last_token_usage=usage(30,10,10,2))),2)
        with path.open("a") as out:
            out.write(json.dumps(value))
        monitor.poll()
        assert total()==120 and monitor.state["pending_bytes"]>0
        with path.open("a") as out:
            out.write("\n")
        monitor.poll()
        assert total()==160 and monitor.state["pending_bytes"]==0
        moved=archive/path.name
        path.rename(moved)
        monitor.scan(full=True)
        assert total()==160
        write_records(moved,initial())
        monitor.scan(full=True)
        assert total()==160  # Historical tail remains retained, not re-added.
    finally:
        db.close()


def test_full_scan_finds_same_size_rewrite_with_preserved_mtime(tmp_path):
    config=Config.resolve(tmp_path/'home',tmp_path/'data')
    folder=config.codex_home/'sessions'
    folder.mkdir(parents=True)
    path=folder/'s.jsonl'
    write_records(path,initial())
    db=connect(config.data_dir)
    try:
        monitor=Monitor(db,config)
        monitor.scan(full=True,initial=True)
        before=db.execute('SELECT count(*) FROM source_generations').fetchone()[0]
        stat=path.stat()
        content=path.read_bytes()
        # Replace an identity with another equally long identity; unchanged stat hints
        # must not prevent the scheduled full content check from finding it.
        assert b'"s"' in content
        path.write_bytes(content.replace(b'"s"',b'"x"'))
        os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        monitor.scan()
        assert db.execute('SELECT count(*) FROM source_generations').fetchone()[0]==before
        monitor.scan(full=True)
        assert db.execute('SELECT count(*) FROM source_generations').fetchone()[0]>before
    finally:
        db.close()
