"""Allowlist extraction. Raw payloads never enter normalized storage."""
import hashlib
import json

PARSER_VERSION = 6
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")


def numeric_usage(value):
    if not isinstance(value, dict):
        return None
    return {k: value[k] if type(value.get(k)) is int else None for k in TOKEN_FIELDS}


def selected(value, keys):
    return {k: value[k] for k in keys if k in value and isinstance(value[k], (str, int, float, bool, type(None)))}


def size(value, model=None):
    from .estimates import measure
    return measure(value, model)


def normalize(record, context, salt):
    ordinal = context.get("_ordinal", 0)
    restore = context.get("replay_restore")
    if restore and ordinal > restore["boundary"]:
        context.update(restore["context"])
        context.pop("replay_restore", None)
    kind = record.get("type")
    payload = record.get("payload")
    if not isinstance(kind, str) or not isinstance(payload, dict):
        return [], "unsupported_envelope"
    if any(k in payload and payload[k] is not None and not isinstance(payload[k], str)
           for k in ("id", "session_id", "thread_id", "turn_id", "root_turn_id", "response_id", "model", "cwd", "parent_thread_id", "forked_from_id")):
        return [], "unsupported_identity_shape"
    subtype = payload.get("type")
    data = None
    native = None
    event_kind = kind
    if kind == "session_meta":
        header = context.get("file_header")
        if header and header.get("parent") == payload.get("id") and type(header.get("boundary")) is int and ordinal <= header["boundary"]:
            context["replay_restore"] = {"boundary": header["boundary"], "context": {k: context.get(k) for k in ("session_id", "turn_id", "model", "project", "identity_epoch", "metadata_timestamp", "task_started_timestamp", "seen_usage", "own_counter_origin", "parent")}}
        context.update(session_id=payload.get("id"), turn_id=None, model=None, project=payload.get("cwd"), identity_epoch=context.get("identity_epoch", 0) + 1)
        context.update(metadata_timestamp=record.get("timestamp"), task_started_timestamp=None, seen_usage=False, own_counter_origin=False)
        data = selected(payload, ("id", "session_id", "cli_version", "cwd", "parent_thread_id", "forked_from_id", "agent_path", "subagent_history_start_ordinal"))
        context["parent"] = data.get("parent_thread_id") or data.get("forked_from_id")
        if header is None:
            context["file_header"] = {"id": payload.get("id"), "parent": context["parent"], "boundary": payload.get("subagent_history_start_ordinal")}
    elif kind == "turn_context":
        context.update({k: payload[source] for k, source in (("turn_id", "turn_id"), ("model", "model"), ("project", "cwd")) if source in payload})
        data = selected(payload, ("turn_id", "root_turn_id", "model", "cwd", "effort"))
    elif kind == "token_usage_record":
        data = {k: numeric_usage(payload.get(k)) for k in ("usage", "turn_token_usage", "thread_token_usage")}
        data.update(selected(payload, ("response_id", "session_id", "thread_id", "turn_id", "root_turn_id", "model")))
        native = payload.get("response_id")
        event_kind = "response_usage"
    elif kind == "event_msg" and subtype == "token_count":
        info = payload.get("info")
        info = info if isinstance(info, dict) else {}
        data = {k: numeric_usage(info.get(k)) for k in ("total_token_usage", "last_token_usage")}
        data.update(selected(info, ("model_context_window",)))
        meta_time, task_time, event_time = context.get("metadata_timestamp"), context.get("task_started_timestamp"), record.get("timestamp")
        if not context.get("seen_usage") and data["total_token_usage"] is not None:
            context["own_counter_origin"] = bool(all(isinstance(t, str) for t in (meta_time, task_time, event_time)) and meta_time <= task_time <= event_time and data["total_token_usage"] == data["last_token_usage"])
            context["seen_usage"] = True
        data["own_counter_origin"] = context.get("own_counter_origin", False)
        data["boundary_evidence"] = "metadata_then_task_start_then_first_total_equals_last" if data["own_counter_origin"] else None
        event_kind = "cumulative_usage"
    elif kind == "compacted":
        # Deliberately do not descend into replacement history or latest usage.
        data = selected(payload, ("window_id", "turn_id"))
        context["compactions"] = context.get("compactions", 0) + 1
    elif kind == "event_msg" and subtype in ("task_started", "task_complete", "turn_aborted", "thread_settings_applied"):
        data = selected(payload, ("turn_id", "root_turn_id", "model", "effort", "status"))
        if data.get("turn_id"):
            context["turn_id"] = data["turn_id"]
        if subtype == "task_started":
            context["task_started_timestamp"] = record.get("timestamp")
        if data.get("model"):
            context["model"] = data["model"]
        event_kind = str(subtype)
    elif kind == "response_item" and subtype in ("function_call", "custom_tool_call", "function_call_output", "custom_tool_call_output", "web_search_call", "tool_search_call", "tool_search_output"):
        native = payload.get("call_id") or payload.get("id")
        data = selected(payload, ("call_id", "id", "name", "namespace", "status", "parent_call_id"))
        data["type"] = subtype
        if subtype.endswith("output"):
            data["result_size"] = size(payload.get("output"), context.get("model"))
            output = payload.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except ValueError:
                    pass
            if isinstance(output, dict):
                data.update(selected(output, ("success", "status", "exitCode")))
                if type(output.get("exit_code")) is int:
                    data["exitCode"] = output["exit_code"]
                if output.get("isError") is True:
                    data["explicit_error"] = True
        else:
            arguments = payload.get("arguments", payload.get("input"))
            data["argument_size"] = size(arguments, context.get("model"))
            from .patterns import fingerprint
            data.update(fingerprint(payload.get("name"), arguments, salt))
        event_kind = "tool_output" if subtype.endswith("output") else "tool_call"
    elif kind == "event_msg" and subtype == "item_completed":
        item = payload.get("item")
        if not isinstance(item, dict):
            return [], "unsupported_completed_item"
        native = item.get("id")
        from .sources.history import item_metrics
        data = item_metrics(item, salt, context.get("model"))
        data.update(selected(payload, ("thread_id", "turn_id", "started_at", "completed_at")))
        event_kind = "item_completed"
    else:
        # Known content-only families still have physical provenance, without bodies.
        return [], None if kind in ("response_item", "event_msg", "world_state", "inter_agent_communication_metadata") else "unknown_record_kind"
    data["identity_epoch"] = context.get("identity_epoch", 0)
    data["compactions"] = context.get("compactions", 0)
    data["parent"] = context.get("parent")
    return [dict(kind=event_kind, session_id=data.get("thread_id") or context.get("session_id"), turn_id=data.get("turn_id") or context.get("turn_id"), timestamp=record.get("timestamp"), model=data.get("model") or context.get("model"), project=context.get("project"), native_id=native, data_json=json.dumps(data, separators=(",", ":")))], None
