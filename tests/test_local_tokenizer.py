import base64
import hashlib
import json

import pytest

from codex_token_profiler.estimates import configure, measure


def test_real_tiktoken_with_local_synthetic_bpe_and_no_network(tmp_path, monkeypatch):
    pytest.importorskip("tiktoken")
    def network_forbidden(*args, **kwargs):
        raise AssertionError("tokenization must not use the network")
    monkeypatch.setattr("socket.create_connection", network_forbidden)
    content = b"".join(base64.b64encode(bytes([i])) + b" " + str(i).encode() + b"\n" for i in range(256))
    path = tmp_path / "synthetic.bpe"
    path.write_bytes(content)
    config = {"models":{"synthetic-byte-model":{"bpe_path":str(path),"sha256":hashlib.sha256(content).hexdigest(),"encoding":"synthetic-byte","pattern":"(?s).","special_tokens":{}}}}
    (tmp_path / "tokenizers.json").write_text(json.dumps(config))
    try:
        configure(tmp_path)
        result = measure("abc", "synthetic-byte-model")
        assert result["tokens"] == 3 and result["package_version"] == "0.11.0"
        assert measure("abc", "unmapped-real-model")["tokens"] is None
        path.write_bytes(b"corrupted")
        configure(tmp_path)
        assert measure("abc", "synthetic-byte-model")["tokens"] is None
    finally:
        configure(tmp_path / "empty")
