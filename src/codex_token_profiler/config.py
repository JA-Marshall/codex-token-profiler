from dataclasses import dataclass, field
from pathlib import Path
import ntpath
import os
import tomllib


def local_path(value: str | Path) -> Path:
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(text).expanduser().resolve()


def canonical(value: str | Path) -> str:
    text = str(value)
    if text.startswith("\\\\?\\UNC\\"):
        text = "\\\\" + text[8:]
    elif text.startswith("\\\\?\\"):
        text = text[4:]
    if ntpath.isabs(text) and ("\\" in text or ":" in text):
        return ntpath.normcase(ntpath.normpath(text))
    return os.path.normcase(str(local_path(text)))


@dataclass
class Config:
    codex_home: Path
    data_dir: Path
    extra_roots: list[Path] = field(default_factory=list)
    sqlite_home: Path | None = None
    log_dir: Path | None = None
    config_error: str | None = None
    telemetry_configured: bool = False

    @classmethod
    def resolve(cls, codex_home=None, data_dir=None, extra_roots=()):
        home = local_path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        data = local_path(data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "CodexTokenProfiler")
        result = cls(home, data, [local_path(p) for p in extra_roots])
        try:
            with (home / "config.toml").open("rb") as stream:
                settings = tomllib.load(stream)
            for key in ("sqlite_home", "log_dir"):
                if isinstance(settings.get(key), str):
                    path = Path(settings[key]).expanduser()
                    setattr(result, key, local_path(path if path.is_absolute() else home / path))
            result.telemetry_configured = bool(settings.get("otel"))
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            result.config_error = type(exc).__name__
        source_roots = [home, *result.extra_roots]
        source_roots += [p for p in (result.sqlite_home, result.log_dir) if p]
        if any(data == p or data.is_relative_to(p) for p in source_roots):
            raise ValueError("Profiler storage must be outside all Codex source roots")
        return result
