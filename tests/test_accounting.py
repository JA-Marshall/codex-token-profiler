import json

from codex_token_profiler.accounting import build_ledger
from .fixtures.families import usage


def obs(n, total=None, response=None, native=None, session="s", generation=1, turn="t", model="a", parent=None, timestamp=None):
    data = {"usage": response, "thread_token_usage": total} if response is not None else {"total_token_usage": total, "last_token_usage": total}
    data["parent"] = parent
    return dict(record_id=n, id=n, kind="response_usage" if response is not None else "cumulative_usage", session_id=session, turn_id=turn, timestamp=timestamp or f"2026-09-01T00:00:{n:02d}Z", model=model, project="p", native_id=native, data_json=json.dumps(data), generation_id=generation, ordinal=n, generation_superseded=0)


def totals(facts):
    return [sum(f[k] for f in facts if f[k] is not None) for k in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens")]


def test_legacy_repeats_and_unknown_first_attribution():
    facts, gaps = build_ledger([obs(1, usage()), obs(2, usage()), obs(3, usage(130, 30, 50, 7))])
    assert totals(facts) == [130, 30, 50, 7]
    assert len(facts) == 2 and not gaps
    initial = next(f for f in facts if f["method"] == "unallocated_historical")
    assert initial["timestamp"] is None and initial["model"] is None


def test_response_and_cumulative_are_nonadditive():
    facts, gaps = build_ledger([obs(1, usage(), usage(), "r1"), obs(2, usage()), obs(3, usage(130,30,50,7), usage(30,10,10,2), "r2"), obs(4, usage(130,30,50,7))])
    assert totals(facts) == [130, 30, 50, 7]
    assert len(facts) == 2 and not gaps


def test_mixed_legacy_response_preserves_legacy_prefix():
    facts, gaps = build_ledger([obs(1, usage()), obs(2, usage(130,30,50,7), usage(30,10,10,2), "r2"), obs(3, usage(130,30,50,7))])
    assert totals(facts) == [130, 30, 50, 7]
    assert {f["method"] for f in facts} == {"unallocated_historical", "reported_response"}
    assert not gaps


def test_distinct_response_ids_identical_values_are_both_counted():
    facts, _ = build_ledger([obs(1, usage(), usage(), "r1"), obs(2, usage(), usage(), "r2")])
    assert totals(facts) == [200, 40, 80, 10]


def test_replayed_response_identity_retains_all_provenance():
    a = obs(1, usage(), usage(), "r1")
    b = obs(2, usage(), usage(), "r1", generation=2)
    facts, gaps = build_ledger([a,b])
    assert totals(facts) == [100,20,40,5] and not gaps
    assert set(facts[0]["refs"]) == {1,2}


def test_unexplained_decrease_is_not_new_consumption():
    facts, gaps = build_ledger([obs(1, usage()), obs(2, usage(30,10,10,2), turn="new"), obs(3, usage(50,15,15,3), turn="new")])
    assert totals(facts) == [100,20,40,5]
    assert "unresolved_counter_decrease" in {g["code"] for g in gaps}


def test_explicit_zero_reestablishes_baseline():
    facts, gaps = build_ledger([obs(1, usage()), obs(2, usage(0,0,0,0)), obs(3, usage(30,10,10,2))])
    assert totals(facts) == [130,30,50,7]
    assert any(g["code"] == "unresolved_counter_decrease" for g in gaps)


def test_inherited_counter_is_not_child_usage():
    facts, gaps = build_ledger([obs(1, usage(), parent="parent"), obs(2, usage(130,30,50,7), parent="parent")])
    assert facts == []
    assert all(g["code"] == "inherited_cumulative_unallocated" for g in gaps)


def test_unknown_categories_stay_unknown_and_zero_stays_zero():
    value = usage(0,0,0,0)
    value["reasoning_output_tokens"] = None
    facts, _ = build_ledger([obs(1, value, value, "r1")])
    assert facts[0]["input_tokens"] == 0
    assert facts[0]["reasoning_output_tokens"] is None


def test_model_switch_interval_is_unknown_mixed():
    facts, _ = build_ledger([obs(1, usage(), model="a"), obs(2, usage(130,30,50,7), model="b")])
    assert all(f["model"] is None for f in facts)


def test_conflicting_response_excluded_with_gap():
    facts, gaps = build_ledger([obs(1, usage(), usage(), "r"), obs(2, usage(130,30,50,7), usage(130,30,50,7), "r")])
    assert facts == [] and len(gaps) == 2


def test_ordered_cross_file_overlap_and_novel_tail():
    a, b = obs(1, usage()), obs(2, usage(130,30,50,7))
    c = dict(a, generation_id=2, record_id=3)
    d = dict(b, generation_id=2, record_id=4)
    e = obs(5, usage(150,40,60,8), generation=2)
    facts, gaps = build_ledger([a,b,c,d,e])
    assert totals(facts) == [150,40,60,8]
    assert not gaps


def test_parent_relationship_does_not_exclude_proven_own_counter():
    rows = [obs(1, usage(), parent="parent"), obs(2, usage(130,30,50,7), parent="parent")]
    for row in rows:
        data = json.loads(row["data_json"])
        data["own_counter_origin"] = True
        row["data_json"] = json.dumps(data)
    facts, gaps = build_ledger(rows)
    assert totals(facts) == [130,30,50,7] and not gaps
    assert all(f["timestamp"] for f in facts)


def test_latest_parser_interpretation_replaces_obsolete_owner_without_double_counting():
    old = obs(1, usage(), session="parent-metadata", turn="child-turn")
    old.update(source_id=1, byte_start=0, digest="same-physical-record", parser_version=1)
    current = dict(old, record_id=2, session_id="child", parser_version=2)
    facts, _ = build_ledger([old,current])
    assert len(facts) == 1 and facts[0]["session_id"] == "child"
    assert facts[0]["refs"] == [1,2]
    assert totals(facts) == [100,20,40,5]


def test_lagged_cumulative_notification_matches_checkpoint_not_nearest_time():
    rows = [obs(1, usage(), usage(), "r1"), obs(2, usage()),
            obs(3, usage(130,30,50,7), usage(30,10,10,2), "r2"),
            obs(4, usage()), obs(5, usage(130,30,50,7))]
    facts, gaps = build_ledger(rows)
    assert totals(facts) == [130,30,50,7] and not gaps


def test_response_counter_with_legacy_offset_reconciles_by_exact_delta():
    rows = [obs(1, usage()), obs(2, usage(30,10,10,2), usage(30,10,10,2), "r1"), obs(3, usage(130,30,50,7)),
            obs(4, usage(50,20,20,3), usage(20,10,10,1), "r2"), obs(5, usage(150,40,60,8))]
    facts, gaps = build_ledger(rows)
    assert totals(facts) == [150,40,60,8] and not gaps
