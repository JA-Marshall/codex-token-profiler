"""Optional explicitly mapped local tokenizers. No downloads or network fallback."""
from importlib.metadata import version
import hashlib
import json
from pathlib import Path

_models = {}
_loaded = {}


def configure(data_dir):
    global _models, _loaded
    _models, _loaded = {}, {}
    path = Path(data_dir) / "tokenizers.json"
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
            _models = config.get("models", {}) if isinstance(config, dict) else {}
        except (OSError, ValueError):
            pass


def tokenizer(model):
    if not model or model not in _models:
        return None
    if model in _loaded:
        return _loaded[model]
    _loaded[model] = None
    spec = _models[model]
    try:
        path = Path(spec["bpe_path"])
        if not path.is_absolute() or "://" in str(path) or not path.is_file():
            return None
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != spec["sha256"]:
            return None
        import tiktoken
        import base64
        ranks = {base64.b64decode(token): int(rank) for token, rank in (line.split() for line in content.splitlines() if line)}
        encoding = tiktoken.Encoding(name=spec["encoding"], pat_str=spec["pattern"], mergeable_ranks=ranks, special_tokens=spec.get("special_tokens", {}))
        _loaded[model] = (encoding, dict(encoding=spec["encoding"], package_version=version("tiktoken"), mapping="explicit_local_model_map", mapping_sha256=spec["sha256"]))
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        pass
    return _loaded[model]


def measure(value, model=None):
    if value is None:
        return dict(bytes=None, characters=None, tokens=None, method="unavailable", completeness="unknown")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    flags = []
    if "truncated" in text.lower():
        flags.append("truncated")
    media = False
    text_parts = []
    def inspect(node):
        nonlocal media
        if isinstance(node, list):
            for part in node:
                inspect(part)
        elif isinstance(node, dict):
            kind = str(node.get("type", "")).lower()
            if any(marker in kind for marker in ("image", "audio", "video")):
                media = True
            if isinstance(node.get("text"), str):
                text_parts.append(node["text"])
            for child in node.values():
                if isinstance(child, (dict, list)):
                    inspect(child)
    inspect(value)
    if media:
        flags.append("unsupported_media")
    measured = "\n".join(text_parts) if media else text
    result = dict(bytes=len(text.encode("utf-8")), characters=len(measured), tokens=None,
        method="no_verified_local_tokenizer", scope="extracted_text_only" if media else "retained_text" if isinstance(value, str) else "serialized_json",
        completeness="partial" if flags else "retained_content", flags=flags)
    available = tokenizer(model)
    if available:
        encoding, metadata = available
        result.update(tokens=len(encoding.encode(measured, disallowed_special=())), method="local_tokenizer_estimate", **metadata)
    return result
