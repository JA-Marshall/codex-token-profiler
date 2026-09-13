"""Hand-authored fixtures; values and text do not originate in user history."""


def usage(input=100, output=20, cached=40, reasoning=5):
    return dict(input_tokens=input, output_tokens=output, cached_input_tokens=cached,
                reasoning_output_tokens=reasoning, cache_write_input_tokens=0, total_tokens=input + output)


def record(kind, payload, second=0):
    return dict(timestamp=f"2026-09-01T12:00:{second:02d}.000Z", type=kind, payload=payload)


LEGACY = [
    record("session_meta", dict(id="legacy", cwd="C:/synthetic/project", cli_version="0.142.2")),
    record("turn_context", dict(turn_id="t1", model="synthetic-model", cwd="C:/synthetic/project")),
    record("event_msg", dict(type="token_count", info=None)),
    record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(), last_token_usage=usage())), 1),
    record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(), last_token_usage=usage())), 2),
    record("event_msg", dict(type="token_count", info=dict(total_token_usage=usage(130, 30, 50, 7), last_token_usage=usage(30, 10, 10, 2))), 3),
]

RESPONSE = [
    record("session_meta", dict(id="response", cwd="C:/synthetic/project", cli_version="0.153.4")),
    record("turn_context", dict(turn_id="t2", root_turn_id="t2", model="synthetic-model")),
    record("token_usage_record", dict(response_id="r1", thread_id="response", session_id="response", turn_id="t2", root_turn_id="t2", usage=usage(), turn_token_usage=usage(), thread_token_usage=usage()), 1),
    record("compacted", dict(replacement_history=[dict(type="message", content="synthetic replay")], latest_token_usage_record=dict(response_id="r1", usage=usage())), 2),
    record("session_meta", dict(id="child", parent_thread_id="response", forked_from_id="response", agent_path="/root/child", subagent_history_start_ordinal=4), 3),
]

RAW_TOOLS = [
    record("response_item", dict(type="function_call", call_id="c1", name="exec_command", arguments='{"cmd":"echo synthetic"}')),
    record("response_item", dict(type="function_call_output", call_id="c1", output="synthetic result"), 1),
    record("response_item", dict(type="custom_tool_call", call_id="c2", name="apply_patch", input="synthetic patch"), 2),
    record("response_item", dict(type="custom_tool_call_output", call_id="c2", output=[dict(type="input_text", text="synthetic"), dict(type="image", image_url="synthetic")]), 3),
    record("event_msg", dict(type="item_completed", thread_id="response", turn_id="t2", item=dict(type="CommandExecution", id="c1", command="echo synthetic", aggregated_output="synthetic result", exit_code=0, duration=dict(secs=1, nanos=250000000))), 4),
    record("event_msg", dict(type="thread_settings_applied", model="different-synthetic-model"), 5),
]

PROJECTED = [
    dict(type="commandExecution", id="c1", command="echo synthetic", aggregatedOutput="synthetic result", exitCode=0, durationMs=1250, status="completed", commandActions=[]),
    dict(type="mcpToolCall", id="c3", server="synthetic", tool="read", arguments={}, result={"content": [{"type": "text", "text": "synthetic"}]}, status="completed"),
    dict(type="dynamicToolCall", id="c4", tool="synthetic", arguments={}, contentItems=[], success=False, durationMs=0),
    dict(type="subAgentActivity", id="c5", agentThreadId="child", status="completed"),
    dict(type="contextCompaction", id="compact1"),
    dict(type="userMessage", id="u1", content=[dict(type="text", text="synthetic DB-only message")]),
    dict(type="functionCallOutput", id="c1", name="exec_command", output="synthetic result"),
    dict(type="fileChange", id="c2", changes=[], status="completed"),
    dict(type="webSearch", id="c6", query="synthetic", action=dict(type="search")),
    dict(type="collabAgentToolCall", id="c7", tool="spawnAgent", senderThreadId="response", newThreadId="child", status="completed"),
]
