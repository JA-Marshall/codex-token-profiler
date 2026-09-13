# Codex token-usage profiler

Build and verify a local Codex token-usage profiler that imports all available historical activity and continuously processes new activity.

Work autonomously through discovery, implementation, and validation. Make reasonable implementation choices and document them. Do not modify Codex session history or launch model workloads merely to generate test data.

## Objective

Help me understand which projects, tasks, models, tools, and repeated behaviors account for the most token usage, and compare the efficiency of different workflows.

## 1. Discover the available data

- Locate the actual Codex data directory, installed version, session archives, logs, and any relevant local databases.
- Inspect representative records using read-only access. Avoid printing private conversation content or credentials.
- Identify where historical tool calls, tool results, usage counters, timestamps, model changes, compaction events, and parent/child task relationships are recorded.
- Consult current official OpenAI documentation for supported telemetry and event interfaces.
- Establish the available historical coverage and schema variations before choosing an ingestion strategy.
- Never assume the current session format applies to every historical record.

## 2. Implement historical ingestion

- Import all discoverable historical and archived sessions into a separate local SQLite database.
- Preserve source provenance so every metric can be traced to its source record.
- Make ingestion incremental, restartable, and idempotent.
- Handle malformed records, partial files, duplicates, schema changes, and inaccessible sources without abandoning the whole import.
- Use safe read-only access to live databases.
- Provide an import summary showing discovered, imported, skipped, and failed sources, date coverage, and missing usage data.

## 3. Implement continuous ingestion

- Watch supported local event/session sources and process appended data.
- Handle partial writes, file rotation, truncation, restarts, and files created while the profiler is running.
- Periodically reconcile sources to catch missed filesystem events.
- If supported telemetry adds useful information, provide a reviewed configuration and integrate it without duplicating existing records.
- Support foreground operation plus explicit start, stop, and status commands.
- Make startup-at-login optional; do not enable it automatically.
- Keep ingestion lightweight and independent of model calls.

## 4. Build honest token accounting

- Separate reported usage from estimated attribution in storage and UI.
- Detect cumulative versus per-response counters and avoid double-counting.
- Track input, cached input, output, and reasoning tokens when available.
- Do not add cached tokens to input totals when they are already included, or reasoning tokens to output totals when already included.
- Respect counter resets, branching, resumed sessions, and compaction.
- Estimate tool-call argument and tool-result token sizes only when sufficient content and a suitable tokenizer are available.
- Label tokenizer assumptions, truncated results, and unsupported media.
- Never claim a tool-result token estimate is its exact billed cost.
- Leave unavailable values unknown rather than treating them as zero.
- Do not infer subscription quota consumption from token counts.
- Account for nested tool orchestration when observable; otherwise report the outer tool and the coverage limitation.

## 5. Build a local dashboard

Include:

- Historical coverage and live ingestion status.
- Usage over time, filterable by project, session, model, and date.
- Reported input, cached input, output, and reasoning breakdowns.
- Tool rankings by calls, failures, duration, and estimated result size.
- Largest individual tool results.
- Repeated commands, repeated reads, and retry patterns as potential inefficiency indicators.
- A session timeline connecting tool activity with reported usage updates.
- Session comparisons and optional benchmark labels.
- CSV/JSON export.

Keep the dashboard bound to localhost. Store aggregates and source references by default; avoid copying full conversations unnecessarily. Do not send data to external services.

## 6. Validate and deliver

- Test meaningful failure cases: duplicate ingestion, restart recovery, partial writes, cumulative counters, counter resets, and schema variation.
- Reconcile usage totals against representative original sessions.
- Verify historical import and live ingestion using existing activity or synthetic fixtures, without paid model runs.
- Measure import time, database size, and idle monitoring overhead.
- Deliver working code, the historical import, a verified dashboard, and concise setup/start/stop instructions.
- Document data coverage, estimation limitations, and any unresolved gaps.

## Completion criteria

Completion means the available historical data is imported, new records are ingested without duplication, dashboard totals reconcile with source usage records, and the application can be restarted reliably.
