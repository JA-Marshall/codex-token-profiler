import threading
import socket

from codex_token_profiler.config import Config
from codex_token_profiler.web import create_app


def test_lan_host_allowed_only_when_enabled(tmp_path,monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.168.68.52',8765))])
    config=Config.resolve(tmp_path/'home',tmp_path/'data')
    for enabled in (False,True):
        app=create_app(config,{'status':'running'},threading.Event(),'secret',8765,lan=enabled)
        client=app.test_client()
        assert client.get('/health',base_url='http://192.168.68.52:8765').status_code==(200 if enabled else 400)
        assert client.get('/health',base_url='http://attacker.example:8765').status_code==400
        assert client.get('/health',base_url='http://192.168.68.52:8765',headers={'Origin':'http://attacker.example'}).status_code in (400,403)
        assert client.post('/control/stop',base_url='http://192.168.68.52:8765').status_code in (400,403)
        if enabled:
            assert client.get('/health',base_url='http://192.168.68.52:8765',headers={'Origin':'http://192.168.68.52:8765'}).status_code==200
