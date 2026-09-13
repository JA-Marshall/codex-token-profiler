"""Explicit raw/projected lifecycle adaptation without storing command/output text."""
import hashlib
import json

from ..normalize import selected, size

ITEM_TYPES = {
    "CommandExecution": "commandExecution", "McpToolCall": "mcpToolCall", "DynamicToolCall": "dynamicToolCall",
    "FileChange": "fileChange", "WebSearch": "webSearch", "ImageView": "imageView",
    "ContextCompaction": "contextCompaction", "SubAgentActivity": "subAgentActivity",
    "CollabAgentToolCall": "collabAgentToolCall", "CollabToolCall": "collabAgentToolCall",
    "UserMessage": "userMessage", "AgentMessage": "agentMessage", "Reasoning": "reasoning",
    "Sleep": "sleep", "ImageGeneration": "imageGeneration", "FunctionCallOutput": "functionCallOutput",
}
FIELDS = {
    "exit_code": "exitCode", "aggregated_output": "aggregatedOutput", "content_items": "contentItems",
    "agent_thread_id": "agentThreadId", "agent_path": "agentPath", "sender_thread_id": "senderThreadId",
    "receiver_thread_ids": "receiverThreadIds", "new_thread_id": "newThreadId",
    "duration_ms": "durationMs", "call_id": "callId",
    "command_actions": "commandActions", "parent_call_id": "parentCallId",
}


def item_metrics(raw, salt, model=None):
    item = {FIELDS.get(k, k): v for k, v in raw.items()}
    kind = ITEM_TYPES.get(item.get("type"), item.get("type"))
    result = selected(item, ("id", "callId", "tool", "server", "namespace", "name", "status", "exitCode", "success", "durationMs", "agentThreadId", "agentPath", "senderThreadId", "newThreadId", "parentCallId"))
    result["type"] = kind
    duration = item.get("duration")
    if isinstance(duration, dict) and isinstance(duration.get("secs"), (int, float)) and isinstance(duration.get("nanos"), (int, float)):
        result["durationMs"] = duration["secs"] * 1000 + duration["nanos"] / 1000000
    if "durationMs" in result:
        result["duration_method"] = "explicit_execution"
    if isinstance(item.get("receiverThreadIds"), list):
        result["receiverThreadIds"] = [x for x in item["receiverThreadIds"] if isinstance(x, str)]
    if item.get("error") is not None or item.get("failure") is not None:
        result["explicit_error"] = True
    if kind in ("commandExecution", "mcpToolCall", "dynamicToolCall", "functionCallOutput"):
        arguments = item.get("command") if kind == "commandExecution" else item.get("arguments")
        result["argument_size"] = size(arguments, model)
        if arguments is not None:
            from ..patterns import fingerprint
            result.update(fingerprint("exec_command" if kind == "commandExecution" else item.get("tool", kind), arguments, salt))
        # One preferred result representation, never sum wrappers and copies.
        output = item.get("aggregatedOutput", item.get("output", item.get("result", item.get("contentItems"))))
        result["result_size"] = size(output, model)
    from ..patterns import fingerprint
    result["read_patterns"] = [fingerprint("read_file", action, salt) for action in item.get("commandActions", [])
                               if isinstance(action, dict) and action.get("type") in ("read", "Read")]
    return result
