"""Conservative fingerprints; raw commands/paths do not enter pattern storage."""
import hashlib
import json


def fingerprint(name, arguments, salt):
    if arguments is None:
        return {}
    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except ValueError:
            pass
    short = str(name).split(".")[-1]
    kind, value = "exact_arguments", arguments
    if short in ("exec_command", "shell", "shell_command", "commandExecution"):
        if isinstance(parsed, dict):
            value = parsed.get("cmd", parsed.get("command", arguments))
        kind = "exact_command"
    elif short in ("read_file", "read", "read_text_file", "get_file_contents") and isinstance(parsed, dict):
        kind = "exact_read_and_range"
        value = parsed
    serialized = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256((salt + "\0" + kind + "\0" + str(name) + "\0" + serialized).encode()).hexdigest()
    return dict(pattern_hash=key, pattern_kind=kind, pattern_descriptor=f"{kind} {key[:10]}", pattern_version=1)
