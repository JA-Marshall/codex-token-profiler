import json
from .fixtures.families import LEGACY, RESPONSE, RAW_TOOLS, PROJECTED
from codex_token_profiler.normalize import normalize
from codex_token_profiler.sources.history import item_metrics


def test_synthetic_material_families_are_normalized_without_bodies():
    for family in (LEGACY, RESPONSE, RAW_TOOLS):
        context = {}
        for record in family:
            events, error = normalize(record, context, "synthetic-salt")
            assert error is None
            assert events
    for item in PROJECTED:
        metric = item_metrics(item, "synthetic-salt")
        assert metric["type"] == item["type"]
        assert "synthetic DB-only message" not in json.dumps(metric)


def test_replayed_parent_metadata_restores_child_after_explicit_boundary():
    from .fixtures.families import record, usage
    records = [record("session_meta", dict(id="child", parent_thread_id="parent", subagent_history_start_ordinal=3)),
               record("session_meta", dict(id="parent")),
               record("turn_context", dict(turn_id="old")),
               record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(), last_token_usage=usage()))),
               record("event_msg", dict(type="task_started", turn_id="new"), 1),
               record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(30,10,10,2), last_token_usage=usage(30,10,10,2))), 2)]
    context = {}
    owners = []
    for ordinal, r in enumerate(records):
        context["_ordinal"] = ordinal
        events, error = normalize(r, context, "salt")
        assert error is None
        owners.append(events[0]["session_id"])
    assert owners == ["child","parent","parent","parent","child","child"]
