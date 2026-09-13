# Codex token-usage profiler: implementation plan

Prepared 13 September 2026 for `C:\Users\james\Desktop\Code\Emory`.

Source of requirements: [codex-token-profiler-plan.md](codex-token-profiler-plan.md). This document plans implementation; it does not claim that the application, import, or dashboard already exists. The original specification remains unchanged.

## 1. Scope and operating rules

Deliver a local Windows application that imports every discoverable Codex history source, follows new activity, explains reported token usage and estimated tool sizes, and supports workflow comparisons. Completion requires a real historical import, reconciled totals, verified live ingestion and restart behavior, a working localhost dashboard, and setup/start/stop documentation.

- Read Codex sources only. Never rewrite, migrate, truncate, checkpoint, or change journal settings on Codex databases or session files.
- Do not launch model turns, API requests, or other model workloads for discovery or testing. Use existing history and synthetic fixtures.
- Keep profiler storage separate from Codex. Do not send history, aggregates, estimates, or diagnostics externally. Serve all dashboard assets locally.
- Store normalized metrics and provenance by default, not full messages, reasoning, tool arguments, outputs, or log bodies. Inspect sensitive payloads only in memory when needed for extraction.
- Work autonomously on the implementation milestones. Telemetry configuration is conditional and must be concrete and reviewed before activation. Startup at login is explicit opt-in and remains disabled by default.
- Re-read applicable workspace instructions before implementing. During planning, no `AGENTS.md` or `AGENTS.override.md` existed in the directory chain from `C:\` through Emory; `C:\Users\james\.codex\AGENTS.md` was empty. There were no descendant directories or instructions in Emory.
- Emory currently contains only the specification. Git resolves to the parent `C:\Users\james\Desktop\Code`, with unrelated untracked sibling projects. Keep all project changes inside Emory; do not stage or modify the parent tree indiscriminately.

## 2. Verified local evidence

Discovery used directory inventories, streaming JSON decoding with aggregate/key-only output, and SQLite URI connections with `mode=ro` and `PRAGMA query_only=ON`. No credentials or conversation bodies were printed. Values below are a live snapshot, not frozen acceptance counts.

| Source / environment | Observed | Implementation consequence |
| --- | --- | --- |
| Codex home | `C:\Users\james\.codex`; no `sqlite_home` or `log_dir` overrides in inspected user config | Resolve `--codex-home`, then `CODEX_HOME`, then user home; support discovered overrides and explicit additional source roots |
| Installed CLI | `codex-cli 0.153.4`, executable under `%LOCALAPPDATA%\OpenAI\Codex\bin\8e5b6932251c2c1c\codex.exe` | Record executable/version in discovery; do not assume desktop and CLI versions are interchangeable |
| Desktop | Appx `OpenAI.Codex`, version `26.901.6511.0` | Record separately from CLI |
| Runtime | Python 3.12.6; Node also available | Use Python 3.12 with built-in SQLite; no Node build pipeline needed |
| `sessions/**/*.jsonl` | 265 files, approximately 797 MB | Primary source of active and historical rollout records |
| `archived_sessions/**/*.jsonl` | 72 files, approximately 152 MB | Include archives in every full discovery/reconciliation |
| Full rollout scan | 337 files, 336 distinct first metadata IDs; UTC event range `2026-06-26T12:21:01.448Z`–`2026-09-12T23:25:04.125Z` | Approximately 949 MB of available history; filename dates are not authoritative event timestamps |
| Version variation | 15 recorded CLI versions, from 0.142.2 through 0.153.4, including alpha versions | Detect record shape, not just version; maintain versioned fixture families |
| Usage availability | 332 files with usage, five without; six null token-count info records | Show missing usage explicitly; file counts are not distinct session counts |
| Counter behavior | 34,506 `event_msg/token_count` records; 896 adjacent equal total counters and 59 decreases within files | Summing snapshots or treating every decrease as new consumption is incorrect |
| Response records | 6,570 `token_usage_record` events in the full scan; later live scan had more | Response-level usage is available in newer history, not uniformly across archives |
| Compaction / identity | 210 top-level `compacted` events; 366 metadata records; parent and fork fields present; one first metadata ID appears in two nonidentical files | Preserve identity epochs and inherited history; neither file path nor first session ID alone identifies every event |
| `state_5.sqlite` | 336 threads, 72 archived; 153 spawn edges; all referenced rollouts exist | Metadata, project mappings and relationship enrichment; `tokens_used` is a cross-check, not another additive usage stream |
| Windows paths | 59 rollout paths initially looked external because of extended Windows path notation; after canonicalization all were inside the discovered rollout roots | Normalize separators, case and `\\?\` forms before path comparisons; preserve original source paths |
| `thread_history_1.sqlite` | `thread_turns`, `thread_items`, `thread_realtime_items`, projection state; one thread absent from rollout metadata has only one `userMessage` item | Import database-only coverage with unknown usage; the database also duplicates/projectively transforms rollout items |
| `logs_2.sqlite` | About 161 MB main file; 30,732 log rows at inspection, Unix-second range 1788460324–1789255497; WAL present | Useful diagnostic enrichment, shorter retention than history; never assume each log line is a usage event |
| Desktop logs | 35 `.log` files under `%LOCALAPPDATA%\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\Codex\Logs`; sampled first lines were timestamp-prefixed text | Inventory and conservatively extract recognized structured diagnostics; no generic body scraping into the profiler |
| Other local stores | `session_index.jsonl` has `id`, `thread_name`, `updated_at`; `sqlite/codex-dev.db` has local catalog/automation metadata, but its timeline ledger was empty | Metadata fallback; do not assume this ledger contains historical events |
| Other databases | Goals, memory, queue and thread-summary databases exist | Inventory with explicit exclusion reasons; goals' `tokens_used` is not independent billing; memory/queue/summary bodies are not needed |
| Telemetry | No `[otel]` keys in inspected user config | No existing local OTLP history established; base functionality must work without enabling telemetry |

The full JSONL shape scan decoded all available lines without malformed-record errors at that moment and took about 2.23 seconds. This is discovery timing only, not an ingestion/tokenization benchmark. Sampling and scans did not establish exact billed costs, complete remote history, or the semantics of every counter decrease.

### Verified record families

- JSONL envelope: `timestamp`, `type`, `payload`.
- `session_meta`: `id`, optional `session_id`, `cwd`, `cli_version`, `source`, optional `parent_thread_id`, `forked_from_id`, `agent_path`, `subagent_history_start_ordinal`, and changing additional fields. Multiple metadata records can occur in one file.
- `turn_context`: `turn_id`, sometimes `root_turn_id`, `model`, `cwd`, `effort`, and other context. `event_msg/thread_settings_applied` also carries model/settings changes. Do not apply today's model to old turns.
- `event_msg/token_count`: nullable `info`, containing `total_token_usage`, `last_token_usage`, `model_context_window`; sibling `rate_limits` is not token consumption.
- `token_usage_record`: `response_id`, `session_id`, `thread_id`, `turn_id`, `root_turn_id`, `usage`, `turn_token_usage`, `thread_token_usage`. Each usage object exposes input, cached input, cache-write input, output, reasoning output and total tokens. Sample response usage matched successive cumulative increments; the full response scan found no `total != input + output` cases.
- `response_item`: function/custom tool call and output variants, with `call_id`, names/namespaces, arguments or input, and output. Other observed variants include tool search, web search, messages, reasoning and compaction.
- `event_msg/item_completed`: `thread_id`, `turn_id`, completion time and sometimes start time; raw items use PascalCase types and often snake_case fields. Tool `duration` was observed as `{secs, nanos}`.
- Database `thread_items.item_json` uses lower camelCase types/fields, including `durationMs`, `aggregatedOutput`, `commandActions`, `exitCode`, `appContext`, `contentItems`, and `agentThreadId`. Explicit adapters must handle these representations; generic case conversion is insufficient.
- `compacted`: window identifiers, replacement history and optional `latest_token_usage_record`; replacement history is contextual replay, not new spend. `ContextCompaction` items also exist and can duplicate the same compaction.
- Parent/child evidence exists in metadata, `state_5.thread_spawn_edges`, subagent activity items and collaboration calls. This is distinct from nested tool orchestration inside a tool such as `functions.exec`.

## 3. Current official documentation and integration decision

Official pages were searched and opened on 13 September 2026. Developer URLs currently redirect to ChatGPT Learn. Public event APIs are not a promise that private on-disk rollout and SQLite schemas remain stable.

1. [Codex App Server](https://learn.chatgpt.com/docs/app-server): documents `thread/tokenUsage/updated`, item lifecycle events, compaction items, and CLI-generated version-specific JSON schemas. Use these for an optional future event adapter and schema comparison. A newly launched app server is not established as a passive subscription to every existing desktop process. Do not launch/resume threads to collect telemetry.
2. [Advanced configuration: observability and telemetry](https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry): describes OTel request/stream events and tool results, including durations and output snippets. Prompt redaction does not remove every potentially private tool field. The docs place telemetry configuration at user level. Keep an optional collector local and extract allowlisted fields only.
3. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): documents `sqlite_home`, `log_dir`, output-history limits and OTel exporter/protocol settings. Use discovery to respect configured locations; a stored tool result can be truncated before this profiler sees it.
4. [Responses usage schema](https://developers.openai.com/api/reference/python/resources/responses/methods/retrieve): represents cached input and reasoning output as details within input/output, with total tokens separate. This informs subset accounting; local adapter behavior still requires source reconciliation.

**Decision:** ingest rollouts as the primary event stream, reconcile SQLite projections as supplemental coverage, and use logs only for supported diagnostic enrichment. Use periodic filesystem polling as the initial watch implementation: it works on Windows, handles missed notifications by design, and is sufficient for the observed file count. No SDK, API key, cloud database, model invocation, or always-on app-server client is required.

OTel is a bounded conditional milestone. Implement and activate it only if inspected events provide useful missing fields and stable correlation. If they do not, deliver a documented evaluation and leave it disabled. Lack of an attachable desktop event socket is not a blocker to file-based continuous ingestion.

## 4. Smallest maintainable architecture

One Python package, one CLI, one local SQLite database, one background ingestion loop and one localhost web server. Use `argparse`, `sqlite3`, `pathlib`, `json`, `hashlib`, `tomllib`, `logging` and `threading` from the standard library. Use Flask/Jinja for routes/templates and Waitress for the Windows WSGI server; pin tested versions during setup. Use pytest for tests. An optional tokenizer extra may use `tiktoken` with a verified local encoding cache; no runtime downloads. No ORM, frontend framework, message broker, separate worker service or generated application scaffolding is needed.

Suggested layout:

```text
pyproject.toml
src/codex_token_profiler/
  cli.py, config.py, discovery.py, db.py
  sources/rollout.py, sources/state.py, sources/history.py, sources/logs.py
  normalize.py, accounting.py, tools.py, estimates.py, patterns.py
  ingest.py, monitor.py, lifecycle.py, queries.py, exports.py, web.py
  migrations/, templates/, static/
tests/fixtures/, tests/unit/, tests/integration/
docs/data-formats.md, docs/accounting.md, docs/operations.md
docs/coverage.md, docs/validation.md, docs/telemetry.md
```

Default runtime directory: `%LOCALAPPDATA%\CodexTokenProfiler`, overridable with `--data-dir`. Database, process lock, heartbeat, private logs and local configuration live there, outside the source repository and outside `.codex`. Reject a destination that resolves to a Codex source database. Ignore runtime outputs, local reports, virtual environments and private fixture material in Git.

The worker is the only writer; request threads use short reader connections. Enable foreign keys, WAL and a bounded busy timeout on the **profiler database only**. Apply numbered migrations transactionally and back up the profiler database before upgrades. Keep normalized facts authoritative and derive aggregates with indexed SQL queries initially. Store parser/accounting versions so affected facts can be rebuilt deterministically from available sources.

### Storage contract

| Tables / concepts | Essential data |
| --- | --- |
| `sources`, `source_generations`, `checkpoints` | Source kind, canonical/original path, file identity, size/mtime, fingerprints, generation, committed byte offset or DB cursor, schema signature, availability/error, coverage range |
| `source_records`, `fact_sources` | Source generation, byte range/line ordinal or database/table/primary key, payload digest, record kind and timestamp, parser version; many source references may support one fact |
| `sessions`, `turns`, `session_edges`, `projects` | Stable native IDs with source namespace, observed identity aliases, start/end/status, project/cwd intervals, model intervals, parent/fork relationship and evidence |
| `usage_observations` | Original reported numeric fields, counter scope, response/turn/thread IDs, epoch, source references, conflict/coverage flags; no conversation body |
| `usage_facts` | Canonical non-overlapping response usage or validated cumulative interval delta; nullable token categories, attribution interval/model/project, reconciliation state, method/version |
| `tool_calls`, `tool_estimates` | Native call/item IDs, outer/child relationship, tool identity, status, timing and provenance, byte/character sizes, separate argument/result estimates, encoding/version/assumptions and truncation/media flags |
| `pattern_occurrences`, `benchmark_labels` | Locally salted fingerprints, safe display descriptors, occurrence references, heuristic version/confidence; user-defined comparison labels, never inferred success claims |
| `ingestion_runs`, `diagnostics` | Discovered/imported/skipped/failed/pending source counts, record errors, freshness, unresolved records, lag, runtime measurements and missing-data counts |

Use NULL for unknown numerical values. Aggregation must return known subtotal **and coverage**, not silently present a partial subtotal as complete. All-unknown groups remain unknown; a verified measured zero remains zero. Store UTC timestamps with original precision/unit; default display timezone is Europe/London, configurable, with DST-aware date filtering.

### Provenance and privacy

Provenance lookup resolves only registered sources; no arbitrary file-read HTTP route. Verify the referenced digest before trusting a byte offset after source mutation. If the source disappears, retain existing metrics but flag that the original is no longer available. An error record contains location, error class and hash, not the malformed body. Use templating escaping and no raw HTML rendering of source strings. Command/read patterns store a salted fingerprint and a minimal safe descriptor by default, rather than raw commands that may contain secrets. Keep benchmark labels local and escaped.

Bind to `127.0.0.1`, reject non-loopback host configuration, restrict Host/Origin, disable CORS, and use CSRF protection for label mutations. Package scripts/styles/fonts locally; test that viewing the dashboard triggers no external requests. No telemetry or crash uploader in the profiler itself.

## 5. Correctness rules to implement before presenting totals

### Source identity and ingestion

1. Discover default active/archive roots, explicitly added roots, configured database/log locations and catalog-referenced rollout paths. Treat remote-only references as unavailable local coverage, without connecting to external services. Record non-history stores as intentionally excluded with reasons.
2. Stream binary JSONL and commit only complete newline-terminated records. Keep the checkpoint at the start of an incomplete trailing line, including when UTF-8 characters span writes. A complete malformed line produces a diagnostic and ingestion continues. A stable final line without newline remains pending until an explicit finalized-source check validates it; never finalize an actively growing partial line merely because it looks like JSON.
3. Persist facts and checkpoint in the same transaction. A crash before commit replays safely; a crash after commit advances once. Bound record sizes and batch memory, and isolate errors by source.
4. Distinguish physical record identity from semantic event identity. Use source/generation/offset for provenance; native response/call/item IDs and observed owning thread for facts. Identical timestamp/value pairs alone are not a deduplication key. Where IDs are missing, use ordered overlap matching within known identity boundaries; retain an explicit ambiguity rather than globally deduplicating identical content.
5. Preserve both nonidentical files for the duplicated metadata ID and reconcile their overlapping event sequences. Handle session metadata changes inside a file. Deduplicate active-to-archive moves and database projections without discarding novel records.
6. Detect rotation, replacement and truncation with file identity/size plus prefix and checkpoint-neighborhood fingerprints. Full reconciliation verifies content fingerprints to catch in-place edits. Rebuild affected derived facts from surviving generations; do not erase valid old usage merely because a source is deleted or rotated. Historical facts with conflicting rewritten evidence are flagged.
7. Read live SQLite through URI `mode=ro`, query-only connections and bounded short transactions, including WAL-visible rows. Do not use `immutable=1` on live databases or copy only the main file. If snapshotting is needed, use SQLite's backup API into profiler-owned storage. Reopen on replacement, retry busy/inaccessible sources, and never checkpoint/vacuum the source.
8. Database projections can update existing rows. Cursor by supported revision fields with overlap, plus periodic full key/revision reconciliation; do not assume append-only row IDs. Schema inspection precedes queries. Catalog/history enrichment can never add a second copy of rollout usage/tool activity.

### Reported token accounting

1. Keep every numeric usage observation and its scope. In verified newer records, `usage` is per response while `thread_token_usage` and `turn_token_usage` are cumulative checkpoints. Prefer unique response facts where those records cover the interval; legacy snapshots provide reconciliation and uncovered intervals, not additional consumption.
2. For a verified legacy cumulative series, derive component-wise deltas within an epoch. Repeated snapshots add nothing. A first cumulative value is attributable as a delta only when a zero baseline/new-session boundary is established. Otherwise retain it as an unallocated historical reported subtotal; do not assign prior usage to the first observed timestamp or current model.
3. Counter decreases trigger classification, not `max(0, delta)` or automatic baseline reset. Use session/turn/window IDs, parent/fork metadata, response records and last-usage fields to distinguish replay, branch inheritance, correction and a real reset. A proven reset starts an epoch; unexplained intervals stay unresolved and visible. Do not blindly sum `last_token_usage`, which may repeat.
4. Where response facts overlap a cumulative interval, use the response facts and validate their sum against that interval. Emit a residual only if component-wise nonnegative, scope-compatible and not attributable to inherited/duplicated history; label it as an interval with unknown finer attribution. Conflicts remain discrepancies. Never drop legacy coverage just because a later part of the thread has response records.
5. Ownership is distinct from where a record is stored. Response IDs and originating thread metadata prevent inherited fork/subagent history and compaction replacement history from being counted again. Store parent/child edges separately; provide own-thread and unique-descendant totals. Never add a parent inclusive subtotal to its children's usage again. Missing parent history creates an explicit inheritance/coverage gap.
6. Input includes cached input; output includes reasoning output. Standard total is input + output, when both are known. Display cached and reasoning as subsets, not additive stacked categories. Preserve observed `cache_write_input_tokens` without inventing its billing treatment. Validate supplied totals and subset bounds; flag anomalies instead of adjusting source values.
7. Apply model/project changes by observed intervals and precedence of response-specific evidence, turn context/settings, then metadata fallback. If an interval crosses a model switch without enough evidence to split it, attribute to unknown/mixed rather than guess. Map projects from explicit local project IDs/roots first, then canonical cwd; do not collapse all projects into the broad parent Git repository.
8. Associate activity and usage by IDs and temporal intervals. The timeline can show correlation but must not allocate all subsequent model usage to the preceding tool. Reported usage is not verified billing, subscription quota consumption, or an exact measure of saved cost. No price conversion or quota inference is required.

### Tool estimates and workflow indicators

- Merge call/output/lifecycle evidence by native identity. Count failed calls from explicit status/error/exit evidence; missing output is pending or unknown, not automatically failure. Prefer explicit execution duration; call-to-result elapsed time is separately labeled observed wall time, and asynchronous process lifetime is separate again.
- Use local tokenizer mappings only when supported. Persist package version, encoding, mapping provenance, measured text scope and assumptions. For an unknown model/encoding or unavailable cache, show bytes/characters and unknown token estimate. Never substitute a characters-divided-by-four estimate silently.
- Estimate arguments and result text separately while reading source content; do not retain payload text. Serialized JSON versus extracted text must be explicit. Non-text media, encrypted content and truncation markers produce flags. Text-only portions of mixed media may have partial estimates; never imply a complete image/audio token count.
- Stored truncated output measures only visible retained text. Exclude wrappers only through a documented adapter; avoid counting `stdout`, `aggregated_output` and formatted copies as three results. Largest-result rankings show source, observed bytes and estimate completeness.
- Correlate nested tools only when structured child calls/results or reliable identifiers are present. Do not execute or regex-expand arbitrary JavaScript/shell code to invent a call graph. Otherwise rank the outer tool and disclose nested coverage limits. Distinguish invocation counts at each level and avoid summing the same result estimate twice.
- Detect exact repeated normalized commands, repeated recognized file reads/ranges, and failure-followed-by-repeat retries within a configurable window (initially ten minutes). Keep normalization conservative and versioned; don't equate commands whose argument order matters. Group exact repeats separately from likely retries, with drilldown provenance and confidence. Repetition is a potential inefficiency indicator, not proof of waste.
- Compare selected sessions using total/known tokens, turns, calls, failures, durations, tool sizes and coverage. Provide optional benchmark labels, model/settings/context and own-thread/descendant scope. Do not rank workflows as equivalent quality without a user-supplied benchmark context.

## 6. Ordered milestones

Each milestone ends with its acceptance evidence saved in `docs/validation.md` (safe summaries only). Implement in dependency order; no multi-agent delegation is required. Do not mark a milestone done based only on code existing or a test that restates its implementation.

### M0 — Reproducible discovery and format contract

**Depends on:** nothing. **Deliver:** project skeleton, pinned environment, `discover` command, source inventory and synthetic fixture families.

Re-run and automate the sanitized inventory above. Include filesystem, source catalogs, DB-only history, log locations, available version signatures and import inclusion/exclusion decisions. Generate version-matched app-server JSON schema with `codex app-server generate-json-schema --out <profiler-owned-temp>` if useful; schema generation must not start turns. Inspect the 59 decrease locations by numeric/identity context and the duplicated-ID files. Document baseline/reset/inheritance examples and raw versus projected duration conversion. Create hand-authored fixtures preserving shape and numeric relationships without copying private bodies.

**Acceptance:** every discovered source has a disposition; the known DB-only thread is represented with unknown usage; extended Windows paths normalize correctly; at least one fixture covers each materially distinct local schema family, not merely each version string.

**Validation:** read-only discovery against existing data; tests for missing directories, path aliases, inaccessible files and changed optional columns. Record inventory date, bytes, event ranges and schema signatures. Gate later accounting on classifying representative decreases; unresolved cases must be explicitly supported as unknown intervals.

### M1 — Database and restartable raw normalization

**Depends on:** M0. **Deliver:** migrations, source provenance, JSONL adapters, `import` command and structured import summary.

Implement source/generation tracking, byte-offset checkpoints, transactional batches, bounded parsing and record diagnostics. Normalize metadata, turn boundaries, compaction markers, usage observations and tool events without yet exposing aggregate token totals as reliable. Import all active/archive files and path aliases, including their overlapping histories.

**Acceptance:** second unchanged import creates no new facts; every normalized fact has source references; a bad line/file does not abandon the other sources; complete versus pending trailing bytes are correctly distinguished.

**Validation:** duplicate ingestion, nonidentical overlapping files, valid duplicate events with distinct native IDs, malformed middle line, null/unknown envelope, over-limit record, split UTF-8/JSON, abrupt termination before and after commit, inaccessible source recovery and clean restart. Verify the source bytes remain unchanged in controlled fixtures.

### M2 — SQLite enrichment and complete historical source coverage

**Depends on:** M1. **Deliver:** state/history adapters and conservative log enrichment.

Read projects/roots, thread metadata and spawn edges; ingest DB-only turns/items and realtime items; reconcile item projections using identities and source ordinals. Track mutable rows/revisions and projection lag. Inspect logs for extractable timing/correlation records and add only fields that actually close a coverage gap; otherwise inventory them as diagnostic-only. Exclude queue/memory/summary bodies with a reason.

**Acceptance:** rollout plus database import does not inflate call or usage counts; the database-only user-message thread has coverage but no invented tokens; all missing paths/unsupported DB schemas appear in the summary and dashboard data model.

**Validation:** synthetic live WAL database, writer updating an existing item, projection catching up later, missing optional table, replacement database, busy lock and read-only failure. Verify imported WAL rows without source writes. Compare representative raw and projected items after normalization, including duration units.

### M3 — Reconciled reported usage ledger

**Depends on:** M1 and M2. **Deliver:** accounting module, SQL summaries, `reconcile` command and accounting documentation.

Implement the precedence/interval rules in section 5. Preserve all original observations; construct non-overlapping usage facts, baseline epochs, source ownership, model/project attribution and explicit ambiguous intervals. Rebuild affected ledgers when late evidence arrives.

**Acceptance:** exact integer agreement for all categories in representative unambiguous sessions; response/cumulative/projection duplicates count once; unresolved intervals and unallocated historical subtotals are visible and excluded from unsupported time/model allocations. Aggregate known subtotals remain consistent with drilldowns.

**Validation:** independent hand-calculated fixtures: repeated snapshots; missing first baseline; null category; known zero; cumulative reset; unexplained decrease; resume; forked prefix; parent/child overlap; compaction replacement; mixed legacy/new usage; model switch; conflicting sources; out-of-order arrival. Reconcile at least one real session per materially different counter family and examples involving archives, resets, compaction and branching. Use a separate read-only calculation over source records, not the production accounting function as its own oracle. Investigate every unexplained mismatch before presenting totals as complete.

### M4 — Tool metrics, estimates and repetition analysis

**Depends on:** M2 and M3. **Deliver:** correlated tool facts, rankings, size estimates, pattern queries and benchmark-label storage.

Implement call/status/duration normalization, argument/result size extraction, locally available tokenizer support, nested orchestration coverage and conservative repeat/retry rules. Token estimates are always stored separately from reported usage.

**Acceptance:** a tool appearing in a call record, completion item and projection is one invocation; pending and unknown outcomes are distinguishable from failures; unknown duration/tokenizer/media stays unknown; direct and nested counts clearly state their level.

**Validation:** success/failure/pending/out-of-order output, multiple async output chunks, mixed media, truncated output, duplicated output representations, unknown model, absent tokenizer cache, explicit nested calls versus opaque orchestration, exact repeats versus commands differing materially, repeated reads with different ranges and failure/retry windows. Confirm no payload bodies or secrets enter persisted fixtures/logs/database.

### M5 — Continuous ingestion and process lifecycle

**Depends on:** M1–M4. **Deliver:** `run`, `start`, `stop`, `status`, resumable monitoring and heartbeat.

Poll known active files every two seconds by metadata, discovering new files and archive moves every 30 seconds. Perform full source/catalog reconciliation, including content verification, every five minutes initially; make intervals configurable and tune from measurements. Poll database revisions with overlap and bounded reads. Back off inactive/error sources. A native filesystem watcher is an optional optimization only if measurements justify it.

Use one OS-held process lock per data directory plus a random instance identifier and private heartbeat/control file. `start` launches the current virtualenv interpreter as a hidden detached process, waits for health, and reports startup failures. `stop` targets the verified profiler instance and requests graceful shutdown; never kill an unrelated process on PID reuse. `run` stays in the foreground. Starting twice returns the existing instance. A second manual import must report the running writer rather than contend silently. `status` distinguishes starting/running/stale/stopped/degraded and reports checkpoint freshness and backlog.

**Acceptance:** normal complete appended records appear within five seconds; newly created files within 35 seconds; events missed during a downtime reconcile on restart. Rotation/truncation does not inflate totals. A second start creates no extra worker. Startup at login remains off; provide a separate explicit enable/disable command or documented Windows Task Scheduler setup only after lifecycle verification.

**Validation:** synthetic append writer, partial writes, rotation, truncation, same-size rewrite, new files, archive move, worker kill/restart, stale PID file, reused PID, concurrent start attempts, stop during transaction, temporarily inaccessible sources and unavailable port. Replay existing/synthetic data without generating model activity.

### M6 — Local dashboard, comparisons and exports

**Depends on:** M3–M5. **Deliver:** Flask/Waitress UI, indexed queries and CSV/JSON exports.

Build a simple server-rendered dashboard with small local JavaScript/SVG charts and five-second status refresh. Include:

1. Coverage and ingestion health: date bounds, discovered/imported/skipped/failed/pending sources, unknown usage, unresolved accounting, last successful reconcile and live lag.
2. Usage over time with project/session/model/date filters; input/cached/output/reasoning values and subset labeling; unknown/mixed and unallocated historical buckets.
3. Tool rankings by calls, failures, duration and estimated result size; largest individual results, observed bytes, completeness, call identifiers and provenance.
4. Repeated commands/reads and likely retries with occurrence drilldowns and heuristic caveats.
5. Session timeline tying tool events, turns, compactions/model changes and reported usage updates together without causal cost attribution.
6. Session comparisons and editable optional benchmark labels; own-thread/descendant scope and coverage side by side.
7. CSV and JSON export of each relevant filtered table, including units, timezone, unknown flags, reported-versus-estimated method and provenance IDs. Preserve numeric zero versus missing values. Mitigate spreadsheet formula execution in CSV text cells; JSON retains explicit nulls.

**Acceptance:** filters affect charts, tables and exports consistently; empty, partially covered and large histories render; all totals drill down to the same canonical facts. Server binds only loopback. No source text is executable HTML and no external assets/requests are used.

**Validation:** API/query fixtures with independently expected totals, timezone/DST boundaries, pagination and stable sort, CSV/JSON round-trip, escaped malicious labels and source strings, Host/Origin/CSRF checks, and browser smoke testing on the imported dataset. Check request logs/network inspection for zero external dashboard requests. Record screenshots or a concise visual QA checklist locally.

### M7 — Evaluate supplemental telemetry

**Depends on:** M0, M3 and M5; not a prerequisite for M6. **Deliver:** documented decision and a reviewed local-only configuration, plus adapter only if useful.

Compare documented OTel fields with current coverage. Do not confuse aggregate metric histograms with per-response events. If timing or identifiable nested activity is missing and available from OTel, add a bounded local OTLP/HTTP JSON logs endpoint and fixture-tested adapter. Proposed configuration must use a loopback endpoint such as `http://127.0.0.1:4318/v1/logs`, `log_user_prompt = false`, no external exporter, and no raw body retention. Confirm exact syntax against installed-version support before presenting the diff.

Correlate by explicit response/call/thread identifiers. Uncorrelatable OTel observations remain supplemental diagnostics, never an additive duplicate of existing usage. Prepare the complete user-config diff and rollback instructions; review before activation as requested by the specification. Do not change unrelated existing analytics settings. If no useful, safely correlated fields are available, document that evidence and leave telemetry disabled with no collector dependency.

**Acceptance:** a clear tested add-value decision; optional activation cannot double-count history. Base import/live monitoring/dashboard work with telemetry off.

**Validation:** synthetic OTLP payloads, duplicate/reordered deliveries, uncorrelatable events, oversized/malformed payloads, prompt/tool snippet stripping and loopback binding. If activated, verify with naturally occurring activity only. No paid test turn.

### M8 — Full import, end-to-end verification and delivery

**Depends on:** M0–M6 and M7's documented decision. **Deliver:** working application, actual historical import, verified dashboard and operations/coverage/validation reports.

Run final discovery, import all currently accessible eligible sources and reconcile again to catch activity generated naturally during implementation. Establish a per-source committed watermark for reproducible validation while Codex continues writing. Run a second import, stop/start cycle and live append replay. Verify every required dashboard view against the canonical database and representative original source records.

Measure complete import time with tokenization both enabled and disabled where available, events/second, peak memory, profiler main/WAL database size, repeat-import time, query latency and ten-minute idle CPU/read/write behavior. Measure the whole watch/reconcile cycle, including full fingerprints. Initial engineering targets for the approximately 949 MB corpus: core import under two minutes, tokenizer-enabled import under ten minutes, unchanged import under ten seconds, peak worker memory under 300 MB, idle mean CPU under 1% of one logical core, and common dashboard queries under 500 ms after warmup. These are targets to measure, not claimed results; document deviations and fix material latency/resource problems without weakening accounting.

**Acceptance:** all available eligible local history through recorded watermarks is imported or has a precise failed/pending disposition; new records arrive once; representative exact totals reconcile and all unresolved gaps are disclosed; restart leaves canonical totals unchanged; source history remains unmodified; the dashboard works without Internet access or model credentials.

**Validation:** full meaningful test suite plus the real-data reconciliation report, duplication/restart checks, performance report and browser smoke test. Use fixture source checksums to prove read-only behavior; for live files record allowed append changes rather than demanding static hashes while Codex is running. No performance claims without measurements.

Deliver `README.md` with exact PowerShell setup commands, local URL, data/source locations, start/stop/status/export/reconcile examples, optional login setup and removal, backup/rebuild instructions and schema/tokenizer limits. Provide a short completion report identifying any incomplete coverage without calling it complete data.

## 7. Planned command contract

Implement this consistent interface (commands below are targets, not commands already available):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m codex_token_profiler discover
.\.venv\Scripts\python.exe -m codex_token_profiler import
.\.venv\Scripts\python.exe -m codex_token_profiler reconcile
.\.venv\Scripts\python.exe -m codex_token_profiler run
# In another terminal, or instead of foreground run:
.\.venv\Scripts\python.exe -m codex_token_profiler start
.\.venv\Scripts\python.exe -m codex_token_profiler status
.\.venv\Scripts\python.exe -m codex_token_profiler stop
.\.venv\Scripts\python.exe -m codex_token_profiler export --dataset usage --format json --output usage.json
.\.venv\Scripts\python.exe -m pytest
```

All commands accept consistent `--data-dir` and applicable source/filter options. Default dashboard port: 8765; choose another explicit local port if occupied. `import` exits nonzero on source failures while still retaining successful progress and a machine-readable summary. `reconcile` distinguishes unexplained mismatches from acknowledged coverage gaps. `status --json` supports health checks. Optional tokenizer installation and cache preparation must be documented separately; normal ingestion must not fetch tokenizer assets over the network.

## 8. Requirement coverage and release gates

| Specification requirements | Milestones and required evidence |
| --- | --- |
| Locate versions, data directories, archives, logs, databases; inspect read-only; establish schemas/coverage; official docs | M0; section 2 evidence, repeatable inventory, format contract and section 3 citations |
| All history, separate SQLite, provenance, incremental/restartable/idempotent ingestion, malformed/partial/duplicate/schema/inaccessible resilience, import summary | M1, M2, M8; source dispositions, atomic checkpoints, failure fixtures and full import report |
| Continuous appended data, partial writes/rotation/truncation/restarts/new files, periodic reconciliation, optional supported telemetry, foreground/start/stop/status, optional login, lightweight/no model calls | M5, M7, M8; lifecycle/live replay tests and overhead measurements |
| Reported versus estimated, cumulative/per-response, token categories/subsets, resets/branches/resumes/compaction, suitable tokenizer/truncation/media, unknowns, no exact tool billing/quota claims, nested orchestration coverage | M3, M4; independent reconciliation, accounting fixtures and explicit UI labels |
| Coverage/live status; usage filters/breakdowns; tool calls/failures/durations/sizes; largest results; repeated commands/reads/retries; timeline; comparisons/labels; CSV/JSON | M4, M6; query, export and browser verification |
| Localhost, minimum retained content, no external data transfer | M1–M8; storage inspection, loopback/escaping controls and offline dashboard validation |
| Duplicate/restart/partial/cumulative/reset/schema tests; source reconciliation; historical/live verification without paid runs; import/size/idle measurements; working code/import/dashboard/instructions and limitations | M8, supported by all preceding gates; documented measurements and completion report |

No implementation blocker was established during planning: the data is locally readable and Python/SQLite are available. Genuine limitations that must remain explicit are missing usage in some history, a DB-only message, incomplete timing/nested-tool evidence, private schema instability, unproven semantics of some decreases/inherited prefixes, and model-tokenizer mappings that may be unavailable. These block particular claims of completeness or exact attribution, not the overall application. Do not manufacture data to remove these gaps.

If a new source cannot be read, continue other sources and retain a retryable failure. If a source's accounting cannot be reconciled, retain its observations and unknown interval; do not silently include a guessed total. Remote/cloud-only activity absent from local sources remains outside measured local coverage.

## 9. Execution handoff

Use the following prompt to execute this plan in this workspace:

> Read `codex-token-profiler-plan.md` and `codex-token-profiler-implementation-plan.md`, then implement milestones M0–M8 in dependency order. Re-check applicable AGENTS.md instructions and current local formats. Preserve all specification requirements, keep Codex history read-only, and use no model workloads to generate tests. Maintain a milestone checklist and evidence in `docs/validation.md`. Continue through working code, the complete available historical import, live ingestion/restart verification, the localhost dashboard, and setup/start/stop instructions. Keep estimates and unknowns honest. Evaluate optional telemetry as specified, leaving it disabled unless its concrete configuration is reviewed; do not enable login startup automatically. Report genuine blockers precisely and continue independent work where possible.
