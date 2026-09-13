import json
import socket
import threading
import time

import pytest

from codex_token_profiler.config import Config
from codex_token_profiler.lifecycle import start, stop, status
from codex_token_profiler.sources.sqlite import readonly
from codex_token_profiler.web import create_app
from .fixtures.families import record,usage


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        return sock.getsockname()[1]


def write_records(path, records, mode="w"):
    with path.open(mode,encoding="utf-8") as stream:
        for value in records:
            stream.write(json.dumps(value)+"\n")


def total(config, session="s"):
    with readonly(config.data_dir / "profiler.sqlite") as connection:
        return connection.execute("SELECT sum(total_tokens) FROM usage_facts WHERE session_id=?",(session,)).fetchone()[0]


def await_total(config, expected, session="s", timeout=5):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if total(config,session)==expected:
            return
        time.sleep(.05)
    assert total(config,session)==expected


def initial(session="s"):
    return [record("session_meta",dict(id=session)),record("event_msg",dict(type="task_started",turn_id=session)),
            record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(),last_token_usage=usage())),1)]


def test_real_worker_append_new_file_duplicate_start_stop_and_restart(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    folder=config.codex_home/"sessions"
    folder.mkdir(parents=True)
    path=folder/"s.jsonl"
    write_records(path,initial())
    port=free_port()
    try:
        running=start(config,port,.1,.3,.8,timeout=15)
        assert running["status"]=="running"
        assert start(config,port,.1,.3,.8)["instance"]==running["instance"]
        assert total(config)==120
        write_records(path,[record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(130,30,50,7),last_token_usage=usage(30,10,10,2))),2)],"a")
        await_total(config,160)
        new=folder/"new.jsonl"
        write_records(new,initial("new"))
        await_total(config,120,"new")
        assert stop(config)["status"]=="stopped"
        assert status(config)["status"]=="stopped"
        write_records(path,[record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(150,40,60,8),last_token_usage=usage(20,10,10,1))),3)],"a")
        restarted=start(config,port,.1,.3,.8,timeout=15)
        assert restarted["instance"]!=running["instance"]
        await_total(config,190)
    finally:
        stop(config)


def test_stale_reused_pid_is_never_a_kill_target(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    config.data_dir.mkdir()
    (config.data_dir/"heartbeat.json").write_text(json.dumps(dict(status="running",pid=1,instance="stale",port=free_port())))
    assert status(config)["status"]=="stale"
    assert stop(config)["status"]=="stopped"


def test_unavailable_port_reports_startup_failure(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        sock.listen()
        with pytest.raises(RuntimeError,match="startup failed"):
            start(config,sock.getsockname()[1],timeout=10)
    assert status(config)["writer_lock"] is False


def test_host_origin_and_control_secret(tmp_path):
    event=threading.Event()
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    app=create_app(config,{"instance":"test"},event,"secret",8765)
    client=app.test_client()
    assert client.get("/health",base_url="http://evil.test").status_code==400
    assert client.get("/health",base_url="http://127.0.0.1:8765",headers={"Origin":"https://evil.test"}).status_code==403
    assert client.post("/control/stop",base_url="http://127.0.0.1:8765").status_code==403
    assert not event.is_set()
    assert client.post("/control/stop",base_url="http://127.0.0.1:8765",headers={"X-Profiler-Control":"secret"}).status_code==200
    assert event.is_set()


def test_concurrent_start_and_verified_worker_crash_recovery(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import psutil
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    folder=config.codex_home/"sessions"
    folder.mkdir(parents=True)
    write_records(folder/"s.jsonl",initial())
    port=free_port()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(start,config,port,.1,.3,.8,timeout=15) for _ in range(2)]
            results=[future.result() for future in futures]
        assert results[0]["instance"]==results[1]["instance"]
        worker=psutil.Process(results[0]["pid"])
        command=worker.cmdline()
        assert "codex_token_profiler" in command and str(config.data_dir) in command
        worker.kill()  # This is the synthetic worker created and verified above.
        worker.wait(timeout=5)
        assert status(config)["status"]=="stale"
        recovered=start(config,port,.1,.3,.8,timeout=15)
        assert recovered["instance"]!=results[0]["instance"]
        assert total(config)==120
    finally:
        stop(config)


def test_default_polling_meets_append_and_new_file_deadlines(tmp_path):
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    folder=config.codex_home/"sessions"
    folder.mkdir(parents=True)
    path=folder/"s.jsonl"
    write_records(path,initial())
    try:
        start(config,free_port(),timeout=15)
        began=time.monotonic()
        write_records(path,[record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(130,30,50,7),last_token_usage=usage(30,10,10,2))),2)],"a")
        await_total(config,160,timeout=5)
        append_seconds=time.monotonic()-began
        began=time.monotonic()
        write_records(folder/"new.jsonl",initial("new"))
        await_total(config,120,"new",timeout=35)
        new_file_seconds=time.monotonic()-began
        (tmp_path/"timings.json").write_text(json.dumps(dict(append_seconds=append_seconds,new_file_seconds=new_file_seconds)))
    finally:
        stop(config)


def test_shutdown_request_during_transaction_commits_and_releases_lock(tmp_path,monkeypatch):
    from codex_token_profiler import monitor as monitor_module
    from codex_token_profiler.lifecycle import run,read_heartbeat,request_local
    config=Config.resolve(tmp_path/"home",tmp_path/"data")
    folder=config.codex_home/"sessions"
    folder.mkdir(parents=True)
    path=folder/"s.jsonl"
    write_records(path,initial())
    enabled,inside,release=threading.Event(),threading.Event(),threading.Event()
    original=monitor_module.ingest_file
    def slow_commit(*args,**kwargs):
        def barrier(stage):
            if enabled.is_set() and stage=="before_commit":
                inside.set()
                assert release.wait(5)
        return original(*args,**kwargs,fault=barrier)
    monkeypatch.setattr(monitor_module,"ingest_file",slow_commit)
    worker=threading.Thread(target=run,args=(config,free_port(),.1,30,300),daemon=True)
    worker.start()
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and status(config).get("status")!="running":
            time.sleep(.05)
        enabled.set()
        write_records(path,[record("event_msg",dict(type="token_count",info=dict(total_token_usage=usage(130,30,50,7),last_token_usage=usage(30,10,10,2))),2)],"a")
        assert inside.wait(5)
        heartbeat=read_heartbeat(config)
        assert request_local(heartbeat,"/control/stop",heartbeat["control_token"])["status"]=="stopping"
        release.set()
        worker.join(5)
        assert not worker.is_alive() and total(config)==160
    finally:
        release.set()
        if worker.is_alive():
            stop(config)
            worker.join(5)


def test_label_saved_via_http_single_writer_queue(tmp_path):
    import http.cookiejar
    import re
    import urllib.parse
    import urllib.request
    from codex_token_profiler.sources.sqlite import readonly
    config=Config.resolve(tmp_path/'home',tmp_path/'data')
    folder=config.codex_home/'sessions'
    folder.mkdir(parents=True)
    write_records(folder/'s.jsonl',initial())
    port=free_port()
    try:
        start(config,port,.1,.3,.8,timeout=15)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        url=f'http://127.0.0.1:{port}'
        page=opener.open(url+'/view/sessions').read().decode()
        csrf=re.search(r'name="csrf" value="([^"]+)"',page).group(1)
        data=urllib.parse.urlencode(dict(csrf=csrf,session_id='s',label='<b>synthetic</b>')).encode()
        saved=opener.open(url+'/labels',data=data).read().decode()
        assert '&lt;b&gt;synthetic&lt;/b&gt;' in saved
        with readonly(config.data_dir/'profiler.sqlite') as connection:
            assert connection.execute('SELECT label FROM benchmark_labels WHERE session_id=?',('s',)).fetchone()[0]=='<b>synthetic</b>'
    finally:
        stop(config)


def test_stop_retries_transient_loopback_failure(tmp_path,monkeypatch):
    import urllib.error
    from codex_token_profiler import lifecycle
    config=Config.resolve(tmp_path/'home',tmp_path/'data')
    folder=config.codex_home/'sessions'
    folder.mkdir(parents=True)
    write_records(folder/'s.jsonl',initial())
    original=lifecycle.request_local
    calls=[]
    def transient(*args,**kwargs):
        calls.append(args[1])
        if len(calls)==1:
            raise urllib.error.URLError('synthetic transient timeout')
        return original(*args,**kwargs)
    try:
        start(config,free_port(),.1,.3,.8,timeout=15)
        monkeypatch.setattr(lifecycle,'request_local',transient)
        assert stop(config,timeout=5)['status']=='stopped'
        assert calls==['/health','/health','/control/stop']
    finally:
        stop(config)
