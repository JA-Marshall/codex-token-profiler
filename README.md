# Codex token-usage profiler

A local Windows dashboard for reported Codex usage, tool activity, repeated
commands/reads, session timelines and workflow comparisons. Codex history is
read-only; metrics and provenance live in a separate SQLite database.

## Setup and launch

From PowerShell in `C:/Users/james/Desktop/Code/Emory`, with Python 3.12:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
.venv/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe -m codex_token_profiler start
```

Open **http://127.0.0.1:8765**. `start` imports history, resumes checkpoints and
launches a hidden worker. A second start returns the existing instance.

LAN access is currently enabled without a password, as requested. On the same
network, open **http://192.168.68.52:8765** (the address may change with DHCP).
To preserve LAN access when restarting, use:

```powershell
.venv/Scripts/python.exe -m codex_token_profiler stop
.venv/Scripts/python.exe -m codex_token_profiler start --lan
```

LAN mode accepts this computer's local IPv4 addresses and hostname. The Windows
firewall setup requests administrator approval to create `CodexTokenProfilerLAN`,
permitting TCP 8765 from the local subnet on Private networks. A plain `start` after
stopping returns to localhost-only mode.

```powershell
.venv/Scripts/python.exe -m codex_token_profiler status --json
.venv/Scripts/python.exe -m codex_token_profiler stop
# Alternative foreground mode; Ctrl+C stops gracefully:
.venv/Scripts/python.exe -m codex_token_profiler run
```

Defaults: `%USERPROFILE%/.codex` (or `CODEX_HOME`) for discovery and
`%LOCALAPPDATA%/CodexTokenProfiler` for storage. Override with `--codex-home`,
`--data-dir`, repeatable `--source-root`, or `--port`. Active and archived JSONL,
state/history projections and catalog metadata are supported. Other sources have
explicit diagnostic or exclusion dispositions.

## Inspect, reconcile and export

Stop the worker before manual import/reconcile. The writer lock prevents competing
writers. Read-only audits and exports can run while monitoring.

```powershell
.venv/Scripts/python.exe -m codex_token_profiler discover --inspect --output .private/discovery.json
.venv/Scripts/python.exe -m codex_token_profiler reconcile --output .private/reconcile.json
.venv/Scripts/python.exe -m codex_token_profiler audit --output .private/source-audit.json
.venv/Scripts/python.exe -m codex_token_profiler export --dataset usage --format json --output .private/usage.json
.venv/Scripts/python.exe -m codex_token_profiler export --dataset rankings --sort failures --format csv --start 2026-09-01 --end 2026-09-13 --timezone Europe/London --output .private/tools.csv
.venv/Scripts/python.exe -m codex_token_profiler start
```

Datasets: `usage`, `tools`, `rankings`, `results`, `patterns`, `sessions`, `timeline`,
`comparisons`. Shared filters: `--session`, `--scope own|descendants`, `--project`,
`--model`, `--start`, `--end`, `--timezone`. End dates are inclusive local dates;
exports retain UTC timestamps. Comparisons accept comma-separated session IDs and
show own-thread and unique-descendant totals. Optional benchmark labels are editable
on Sessions. CSV neutralizes formula-like text; JSON preserves nulls.

## Interpret results

Totals are supported known subtotals, not complete consumption. Cached input and
reasoning output are subsets already included in input/output. Ambiguous inherited
history, unexplained decreases and missing counters remain visible gaps. Unallocated
historical facts have no supported date/model attribution. Remote-only activity
absent from local sources is outside measured coverage.

Tool duration, wall time, bytes, completeness and provenance are available where
observed. Tool token estimates stay unknown until an explicit verified local
model-tokenizer mapping is supplied. Installing tiktoken does not guess one.
For optimization, Rankings also offers **rough result tokens** (characters ÷ 4),
clearly separated from model-tokenizer estimates. Tools/Results → **View command**
shows a short, digest-verified preview on demand. Overview/Sessions/Comparisons show
non-cached input and explicit model-response counts alongside reported totals.
Opaque orchestration does not invent nested calls. Repeat/retry patterns suggest
investigation; they do not prove waste. No billed-cost or quota inference.

See [accounting](docs/accounting.md), [tool metrics and offline tokenizer setup](docs/tool-metrics.md),
[operations, backups and optional login startup](docs/operations.md),
[telemetry decision](docs/telemetry.md), and [validation evidence](docs/validation.md).
The [coverage report](docs/coverage.md) explains source boundaries and unresolved gaps.
Telemetry and login startup remain disabled. No model workloads are used for tests.

Run tests with `.venv/Scripts/python.exe -m pytest -q`. All 78 tests pass.
[Measured performance](docs/performance.md) records the idle CPU target deviation
(1.47% of one core versus 1%) and blocked cleanup of temporary validation files.
