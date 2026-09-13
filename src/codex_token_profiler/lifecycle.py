"""Instance-verified lifecycle. PIDs are informational, never kill targets."""
import json
import os
import queue
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

from .db import connect, now, writer_lock
from .monitor import Monitor


def read_heartbeat(config):
    try:
        return json.loads((config.data_dir / "heartbeat.json").read_text())
    except (OSError,ValueError):
        return {}


def write_heartbeat(config, state, token):
    path = config.data_dir / "heartbeat.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(state,control_token=token)),encoding="utf-8")
    temporary.replace(path)


def locked(config):
    try:
        with writer_lock(config.data_dir):
            return False
    except RuntimeError:
        return True


def request_local(heartbeat, route, token=None):
    port = heartbeat.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid profiler port")
    headers = {"X-Profiler-Control":token} if token else {}
    request = urllib.request.Request(f"http://127.0.0.1:{port}{route}",headers=headers,data=b"" if token else None)
    # Disable environment proxies for private control traffic.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request,timeout=2) as response:
        return json.load(response)


def status(config):
    heartbeat = read_heartbeat(config)
    heartbeat.pop("control_token",None)
    if not locked(config):
        stale = heartbeat.get("status") in ("starting","running","degraded")
        return dict(heartbeat,status="stale" if stale else "stopped",writer_lock=False,service_verified=False)
    try:
        health = request_local(heartbeat,"/health")
        if health.get("instance") != heartbeat.get("instance"):
            return dict(heartbeat,status="stale",writer_lock=True)
        return dict(health,writer_lock=True,service_verified=True)
    except (OSError,ValueError,urllib.error.URLError):
        return dict(heartbeat,status="starting" if not heartbeat else "degraded",writer_lock=True,service_verified=False)


def run(config, port=8765, poll_interval=2, discovery_interval=30, reconcile_interval=300, retry_window=600, lan=False):
    from waitress import create_server
    from .web import create_app
    stop_event = threading.Event()
    mutations=queue.Queue()
    instance, token = secrets.token_hex(16), secrets.token_hex(32)
    with writer_lock(config.data_dir):
        connection = connect(config.data_dir)
        monitor = Monitor(connection,config,retry_window)
        state = monitor.state
        state.update(instance=instance,pid=os.getpid(),port=port,started_at=now(),heartbeat=now(),lan=lan)
        server = None
        try:
            server = create_server(create_app(config,state,stop_event,token,port,mutations,lan=lan),host="0.0.0.0" if lan else "127.0.0.1",port=port,threads=4)
            server_thread = threading.Thread(target=server.run,daemon=True,name="profiler-http")
            server_thread.start()
            write_heartbeat(config,state,token)
            monitor.scan(full=True,initial=True)
            next_discovery = time.monotonic() + discovery_interval
            next_reconcile = time.monotonic() + reconcile_interval
            while not stop_event.is_set():
                started = time.monotonic()
                try:
                    while not mutations.empty():
                        mutation=mutations.get_nowait()
                        try:
                            connection.execute("INSERT INTO benchmark_labels VALUES (?,?,?) ON CONFLICT(session_id) DO UPDATE SET label=excluded.label,updated_at=excluded.updated_at",(mutation["session_id"],mutation["label"],now()))
                            connection.commit()
                        except Exception as exc:
                            connection.rollback()
                            mutation["result"]["error"]=type(exc).__name__
                        finally:
                            mutation["done"].set()
                    if started >= next_reconcile:
                        monitor.scan(full=True)
                        next_reconcile = time.monotonic() + reconcile_interval
                        next_discovery = time.monotonic() + discovery_interval
                    elif started >= next_discovery:
                        monitor.scan()
                        next_discovery = time.monotonic() + discovery_interval
                    else:
                        monitor.poll()
                    state.pop("error",None)
                except Exception as exc:
                    connection.rollback()
                    state.update(status="degraded",error=type(exc).__name__)
                state.update(heartbeat=now(),last_cycle_seconds=time.monotonic()-started)
                write_heartbeat(config,state,token)
                stop_event.wait(max(.05,poll_interval-(time.monotonic()-started)))
        except KeyboardInterrupt:
            pass
        finally:
            state.update(status="stopped",heartbeat=now())
            write_heartbeat(config,state,token)
            if server:
                server.close()
            connection.close()
    return dict(state)


def start(config, port=8765, poll_interval=2, discovery_interval=30, reconcile_interval=300, retry_window=600, timeout=120, lan=False):
    existing_writer = locked(config)
    config.data_dir.mkdir(parents=True,exist_ok=True)
    command = [sys.executable,"-m","codex_token_profiler","run","--codex-home",str(config.codex_home),"--data-dir",str(config.data_dir),"--port",str(port),"--poll-interval",str(poll_interval),"--discovery-interval",str(discovery_interval),"--reconcile-interval",str(reconcile_interval),"--retry-window",str(retry_window)]
    for root in config.extra_roots:
        command.extend(("--source-root",str(root)))
    if lan:
        command.append('--lan')
    flags = getattr(subprocess,"CREATE_NO_WINDOW",0) | getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0)
    process = None
    if not existing_writer:
        with (config.data_dir / "service.log").open("ab") as output:
            process = subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=output,creationflags=flags,close_fds=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = status(config)
        if result.get("status") in ("running","degraded") and result.get("service_verified"):
            return result
        if process is not None and process.poll() is not None:
            if locked(config):
                time.sleep(.1)
                continue
            raise RuntimeError("Profiler startup failed; inspect the private service.log")
        if process is None and not locked(config):
            raise RuntimeError("Existing profiler writer stopped before health was ready")
        time.sleep(.1)
    raise RuntimeError("Profiler startup is still pending; use status to inspect the same instance")


def stop(config, timeout=60):
    heartbeat = read_heartbeat(config)
    deadline = time.monotonic() + timeout
    requested=False
    while time.monotonic() < deadline:
        if not locked(config):
            return dict(status="stopped",instance=heartbeat.get("instance"))
        if not requested:
            try:
                health = request_local(heartbeat,"/health")
                if health.get("instance") != heartbeat.get("instance"):
                    raise RuntimeError("Instance mismatch; no stop request sent")
                request_local(heartbeat,"/control/stop",heartbeat.get("control_token"))
                requested=True
            except (OSError,ValueError,urllib.error.URLError):
                # A brief busy loopback endpoint is not proof of a stale instance.
                # Every retry re-verifies identity; no PID-based fallback exists.
                pass
        time.sleep(.1)
    return dict(status="stopping" if requested else "degraded",instance=heartbeat.get("instance"),stop_requested=requested)
