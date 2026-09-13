import json

from codex_token_profiler.estimates import measure
from codex_token_profiler.patterns import fingerprint
from codex_token_profiler.tools import build_tools


def event(n, kind, native="c", owner="s", source=1, **data):
    return dict(record_id=n, kind=kind, native_id=native, session_id=owner, turn_id="t", timestamp=f"2026-09-01T00:00:{n:02d}Z", data_json=json.dumps(data), source_id=source, byte_start=n, digest=str(n), parser_version=5)


def test_call_output_and_projection_are_one_invocation():
    rows = [event(1,"tool_call",name="exec_command",argument_size=measure("echo x")),
            event(2,"tool_output",result_size=measure("wrapped result")),
            event(3,"item_completed",type="commandExecution",exitCode=0,durationMs=1250,result_size=measure("result"))]
    facts = build_tools(rows)
    assert len(facts) == 1
    assert facts[0]["status"] == "succeeded" and facts[0]["duration_ms"] == 1250
    assert facts[0]["result_bytes"] == 6
    assert facts[0]["result_tokens"] is None
    assert facts[0]["refs"] == [1,2,3]


def test_pending_output_unknown_and_failure_are_distinct():
    rows = [event(1,"tool_call",native="pending",name="read"),event(2,"tool_output",native="unknown",result_size=measure("output")),
            event(3,"item_completed",native="failed",type="commandExecution",exitCode=2,durationMs=0)]
    result = {f["native_id"]:f for f in build_tools(rows)}
    assert result["pending"]["status"] == "pending"
    assert result["unknown"]["status"] == "unknown_outcome"
    assert result["failed"]["status"] == "failed" and result["failed"]["duration_ms"] == 0


def test_async_chunks_and_mirrored_source_do_not_multiply():
    rows = [event(1,"tool_call",name="exec"),event(2,"tool_output",result_size=measure("one")),
            event(3,"tool_output",result_size=measure("two")),event(4,"tool_output",source=2,result_size=measure("one"))]
    fact = build_tools(rows)[0]
    assert fact["result_bytes"] == 6
    assert fact["coverage"] == "nested_unobserved"


def test_ancestry_copies_merge_but_unrelated_native_ids_do_not():
    rows = [event(1,"tool_call",owner="parent",name="read"),event(2,"tool_call",owner="child",name="read"),event(3,"tool_call",owner="unrelated",name="read")]
    facts = build_tools(rows, [("parent","child")])
    assert {f["session_id"] for f in facts} == {"parent","unrelated"}


def test_explicit_nested_identity_and_out_of_order_arrival():
    rows = [event(2,"tool_output",native="child",result_size=measure("done")),
            event(1,"tool_call",native="child",name="read",parent_call_id="outer"),event(3,"tool_call",native="outer",name="functions.exec")]
    facts = {f["native_id"]:f for f in build_tools(rows)}
    assert facts["child"]["parent_id"] == facts["outer"]["id"]
    assert facts["child"]["level"] == "child"


def test_unknown_tokenizer_and_mixed_media_are_honest():
    value = [{"type":"text","text":"hello"},{"type":"image","data":"synthetic"}]
    metric = measure(value,"unknown-model")
    assert metric["tokens"] is None and metric["completeness"] == "partial"
    assert metric["characters"] == 5
    assert "unsupported_media" in metric["flags"]


def test_local_encoding_metadata_and_estimates(monkeypatch):
    class FixtureEncoding:
        def encode(self, text, **kwargs):
            return list(text.encode())
    monkeypatch.setattr("codex_token_profiler.estimates.tokenizer",lambda model:(FixtureEncoding(),{"encoding":"fixture-byte-encoding","package_version":"synthetic","mapping":"fixture"}))
    metric = measure("abc","synthetic")
    assert metric["tokens"] == 3 and metric["method"] == "local_tokenizer_estimate"
    assert metric["encoding"] == "fixture-byte-encoding"


def test_patterns_preserve_argument_order_and_read_ranges():
    a = fingerprint("exec_command", '{"cmd":"run a b"}', "salt")
    b = fingerprint("exec_command", '{"cmd":"run b a"}', "salt")
    assert a["pattern_hash"] != b["pattern_hash"]
    a = fingerprint("read_file", {"path":"secret/path","offset":1,"limit":2}, "salt")
    b = fingerprint("read_file", {"path":"secret/path","offset":2,"limit":2}, "salt")
    assert a["pattern_hash"] != b["pattern_hash"]
    assert a["pattern_kind"] == "exact_read_and_range"
    assert "secret/path" not in json.dumps(a)


def test_structured_read_actions_have_private_range_sensitive_patterns():
    from codex_token_profiler.sources.history import item_metrics
    a = item_metrics(dict(type="commandExecution", commandActions=[dict(type="read", path="secret",command="read 1:20")]), "salt")
    b = item_metrics(dict(type="commandExecution", commandActions=[dict(type="read", path="secret",command="read 20:40")]), "salt")
    assert a["read_patterns"][0]["pattern_hash"] != b["read_patterns"][0]["pattern_hash"]
    assert "secret" not in json.dumps(a)


def test_structured_output_exit_code_proves_failure():
    facts = build_tools([event(1,"tool_call",name="exec_command"),event(2,"tool_output",exitCode=1,result_size=measure("error"))])
    assert facts[0]["status"] == "failed"
