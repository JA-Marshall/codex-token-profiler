# Implementation and validation evidence

Goal remains M0–M8 from the two original plans. No milestone is accepted merely
because code exists. No model workload is used to generate tests.

| Milestone | Current state | Evidence / remaining gate |
|---|---|---|
| M0 | Validated foundation | Reproducible inventory, dispositions, numeric decrease classification, schema-family fixtures and read-only inspection. Final inventory refresh remains part of M8. |
| M1 | Validated foundation | Atomic checkpoints, generations, rolling full-prefix hashes, finalization and failure/recovery tests; historical normalization imported. Lifecycle integration remains M5/M8. |
| M2 | Validated foundation | State/catalog/history/index coverage, mutable WAL projections, replacement tests and actual cross-source correlation; remote catalog entries explicitly metadata-only. |
| M3 | Validated known usage with disclosed gaps | Independent source oracles agree; inherited/reset/null intervals remain explicit unknowns. Own/unique-descendant coverage-aware queries tested. Final refresh/audit remains M8. |
| M4 | Implemented and validated | Canonical tools, sizes, offline tokenizer support, read/command patterns and retries; real correlation checks, 56-test suite and resource measurements below. Live/UI integration remains M5/M6. |
| M5 | Not started | Continuous ingestion and verified lifecycle required. |
| M6 | Not started | Dashboard, filters, comparisons, exports and browser QA required. |
| M7 | Not started | Add-value decision required; telemetry disabled. |
| M8 | Not started | Real import, full acceptance audit, performance and delivery required. |

## Initial environment and checks — 2026-09-13

- Workspace initially contained only the two plans. No applicable AGENTS or
  override instructions were found in the directory chain; user Codex AGENTS was
  empty. Parent repository contains unrelated projects; edits stay under Emory.
- Python 3.12.6; CLI `codex-cli 0.153.4`; desktop Appx 26.901.6511.0.
- Created `.venv`, installed editable package with pinned direct dependencies.
- `python -m pytest -q`: **5 passed**, 0.11 seconds. Tests cover Windows path
  aliases, unsafe destination rejection, missing roots/config errors, schema
  variation, WAL-visible reads, rejected source writes, counter inspection,
  trailing partial bytes and body-free diagnostic output.
- `python -m codex_token_profiler discover --inspect --output .private/discovery.json`
  succeeded: 342 eligible sources, four excluded databases, 36 diagnostic-only
  sources; no inventory diagnostics. Shape scan took 3.57 seconds. This measures
  discovery, not ingestion. Inventory stores every path, schema signature,
  disposition and byte size locally. One DB-only thread has null usage.
- Official App Server and advanced configuration pages searched and opened;
  integration rationale and links recorded in `data-formats.md`.

## M0 counter and overlap inspection

The 23:36 UTC watermark scan contains 338 rollouts, 949,929,896 bytes and
206,952 records; zero malformed lines. Event range:
2026-06-26T12:21:01.448Z–2026-09-12T23:36:49.691Z. Unlike the earlier planning
snapshot, 66 component-wise decreases are present. All were classified by
numeric/identity context: 65 cross a turn boundary with last usage equal to the
new total; one has compaction between snapshots. None is silently called a proven
reset. Per-occurrence original offsets and categories remain in the private report.

Both files with the duplicated first metadata ID were scanned. The large file has
70 response records; the short second file has metadata, settings, one turn,
message/completion and a counter snapshot. First metadata IDs alone cannot prove
ownership. Both files remain imported with separate physical provenance.

## M1 real normalization and transaction evidence

`import --output .private/import-m1.json`: 338 rollouts, 207,010 source records,
159,940 normalized events, zero failed sources/record errors/pending tails;
14.01 seconds. This is normalization, not reconciled usage accounting.

Immediate repeat: 337 files skipped; one naturally active file added 12 source
records and 10 events; 2.47 seconds. Fixed synthetic imports add zero records on
repeat. Recorded import watermarks are stored transactionally per source generation.

`pytest -q`: **19 passed**, 3.40 seconds after enrichment work. New tests include
malformed middle lines, null envelopes, split UTF-8, oversized lines, before/after
commit failures, replacement, truncation, middle-of-file same-size edits, archive
moves, payload privacy, writer exclusion, explicit raw/projected duration agreement,
mutable WAL projections, DB-only coverage and changed required columns.

Physical provenance intentionally retains duplicates and superseded generations.
Canonical reconciliation belongs to M3; these physical counts are not usage or
tool-invocation totals. No accounting, server or lifecycle completion is claimed.

## M2 enrichment and scope findings

Actual enrichment succeeded with all 342 eligible sources imported: 338 rollout
files, state/history/catalog databases and the session index. No source or record
errors were reported. Parser changes intentionally created new physical generations;
these must not be added together as usage. `.private/import-m2-final.json` records
the subsequent enrichment pass and per-source outcomes (6.07 seconds).

The catalog contains 2,201 ChatGPT entries with metadata only, explicitly marked
`remote_metadata_only`; none is represented as locally measured usage. The known
local DB-only message thread remains present with null usage. Source/catalog data
supplies 129 locally cataloged threads; additional rollout/state sessions exist.

Read-only log inspection examined 31,101 database log rows and 68,853 desktop log
lines. No root JSON objects were found, so no reliable structured timing/usage
correlation was established. Logs remain diagnostic-only, not an additive stream.

Additional tests verify stable explicit final-line validation, malformed identity
shapes without poisoning following records, inaccessible-file recovery and database
replacement. Replaced DB evidence remains retained under its original generation.

## M3 work in progress — do not treat the ledger as accepted

`pytest -q`: **40 passed**, 4.96 seconds. Accounting fixtures independently specify
expected integers for legacy repeats, first unknown baseline, response/cumulative
overlap, mixed legacy/new coverage, equal values with different response IDs,
response replay, unresolved decreases, explicit zero baseline, inheritance,
zero versus null, model switches, conflicts, ordered file overlap, parent/child
ownership, lagged notifications and constant offsets between counter families.

Real exploratory reports are in `.private/reconcile-m3-*.json`. They are evidence
of remaining work, not final reconciliation reports. The latest persisted report
before the lag/offset fix was `reconcile-m3-ownership.json`; that pass had thousands
of acknowledged gaps. Do not use its totals as a completion claim or publish them
as complete dashboard usage.

Findings that change the next implementation steps:

- A parent relationship alone does not prove every child counter is inherited.
  189 files have parent/fork metadata; 176 expose a history-start ordinal. The
  ordinal is not established as an offset into the child file and must not be
  treated that way. Metadata/task-start/first-total-equals-last evidence is now
  recorded by parser v3, but requires real-source validation for copied histories.
- Some child files contain parent metadata epochs. One session ID appears across
  eleven related files, not only the previously known pair sharing a first ID.
  Native turn ownership from projections can help but cannot alone establish the
  owner when projection coverage is incomplete. Current `turn_owners` override in
  `accounting.py` is experimental and needs refinement using the state-catalog
  rollout path, owning thread creation boundary and original record sequence.
  Do not mark this ownership strategy accepted merely because synthetic tests pass.
- Some newer response thread counters restart while legacy counters preserve a
  constant historical offset. Exact component deltas can reconcile that offset.
- Some cumulative notifications refer to the preceding response checkpoint even
  though a newer response record already exists. Match explicit checkpoints in
  sequence rather than assigning all nearby response records by timestamp. The
  lag/offset implementation has fixture evidence but its real-data pass is still
  outstanding.
- A diagnostic join exposed missing record indexes; migration 005 adds them.
  The slow read-only audit process was explicitly stopped, then the indexed audit
  finished in 0.13 seconds. No ingestion process is left running.

Remaining release gates are unchanged: finish independent real source arithmetic
and ownership/epoch reconciliation (M3), then tool correlation/estimates/patterns
(M4), continuous lifecycle (M5), dashboard/export/browser verification (M6),
telemetry decision (M7), and full performance/import/restart/delivery audit (M8).
Telemetry and startup-at-login remain disabled. No genuine external blocker exists.

## Current state after source reconciliation and M4 (supersedes earlier provisional notes)

The preceding M3 exploration notes describe intermediate states. The accepted
current behavior is documented in `accounting.md` and `tool-metrics.md`.

The source format audit found the actual nested metadata sequence: child header,
replayed parent header/context, then new child activity after the recorded replay
boundary. Parser v4 restores the child context for this demonstrated family. It
does not blindly apply history-start ordinals to every old schema. The experimental
global projection turn-owner override was removed from reconciliation. Latest
physical-byte interpretations are indexed separately, preserving older source
records without retaining obsolete parser interpretations in canonical totals.

Independent audit: **256 monotonic source histories agree exactly**, including
201 active files, 55 archives, 128 branched histories and 43 with compaction
(categories overlap). The remaining 82 have precise oracle exclusions: 33 unproven
initial boundaries, 29 multiple metadata epochs, 14 decreases, five missing-category
cases and one without cumulative usage. An independent response-ID oracle agrees
on ownership and every category for all 6,626 response IDs at its recorded watermark;
subsequent natural activity increases that count. Private per-source watermarks and
results: `.private/independent-source-audit-final-m4.json`. There are no unexplained
oracle mismatches. The acknowledged inherited/decrease/null intervals are unknown,
not claimed as complete consumption. Current gap classes and records remain
queryable in `accounting_gaps` and the private reconciliation reports.

`pytest -q`: **56 passed**, 6.85 seconds. New checks include: replay-boundary owner
restoration; newest-parser provenance; an independent oracle that detects deliberate
ledger corruption; async tool chunks versus mirrors; pending/unknown/failure
distinctions; explicit nested IDs; unrelated same-ID invocations; privacy of read
patterns; configurable retry windows; raw/projected correlation; actual local
tiktoken encoding with network disabled; unique descendant scope despite cycles;
unknown aggregates; and full-prefix fingerprints at an intermediate batch crash.

Real M4 check (`.private/m4-validation.json`): 41,139 observed invocations, of which
1,342 have call + completion + database-projection support for one canonical fact.
8,867 have explicit durations. Pattern occurrences: 7,003 exact commands, 128
structured reads/ranges, 30,115 other exact argument patterns; 43 unique invocations
meet the failure/repeat retry heuristic. 21,713 outer orchestration calls explicitly
have unobserved nested coverage. No real model tokenizer mapping is enabled, so
real result token estimates are all null; observed byte sizes remain available.

Resource measurements and fixes:

- `.private/m4-runtime.json` measured only the Windows virtualenv launcher: its
  4.7 MB number is **invalid as a worker memory measurement** and must not be cited.
- Correct process-tree measurement initially reached 459 MB. Tool correlation now
  processes related-session components rather than the entire corpus at once.
- Partitioning exposed inefficient session queries and a missing foreign-key child
  index on pattern occurrences. The slow benchmarks were explicitly stopped before
  rerunning; no duplicate worker was started while an earlier handle was live.
- Final measured reconcile (including migration): **20.50 seconds, 264.00 MB peak
  process-tree RSS**, successful exit. Source reconciliation within it took 4.29
  seconds. Evidence: `.private/m4-runtime-cascade-indexed.json` and
  `.private/reconcile-m4-cascade-indexed.json`. This is not a fresh-import or idle
  overhead measurement; those remain required in M8.

Next: M5 continuous ingestion and verified foreground/start/stop/status lifecycle.
Session-scoped accounting/tool rebuild helpers exist but are not yet connected to
a monitor. Then M6 dashboard/exports/browser QA, M7 telemetry add-value decision,
and the full M8 delivery audit. No monitor or dashboard server is running. Source
history, user telemetry configuration and login startup have not been changed.

## M5–M7 delivery checks (supersedes the preceding next-step notes)

M5 continuous monitoring and instance-verified `run/start/stop/status` are implemented.
The live worker has been started, stopped gracefully and restarted on the actual
historical data. Synthetic subprocess tests cover duplicate and concurrent starts,
stale/reused PID records, occupied ports, verified worker kill/restart, downtime
recovery, partial records, archive moves, truncation, preserved-mtime same-size
rewrites and shutdown while a transaction is open. Default-interval measurements
recorded append visibility at **1.953 s**, new-file discovery at **28.204 s**
(`.private/m5-default-timings.json`). No model workload generated these records.

Routine discovery now skips unchanged sources using main-file/WAL metadata; full
content verification remains scheduled. SQLite read helpers hold a consistent
read-only snapshot across related queries. A frozen-corpus ten-minute idle benchmark
and a separate naturally active-worker measurement are in progress; neither is yet
claimed as a passed resource target.

M6 includes nine views: overview, usage, tool rankings, calls, largest results,
patterns, sessions, timeline and comparisons. Ranking controls cover calls, failures,
duration, bytes and estimated result tokens. Filters and CLI/browser CSV/JSON exports
share queries; exports preserve null/zero, units, timezone, measurement caveats and
source/canonical-fact references. Local display time and DST-aware date boundaries
are tested. Benchmark labels pass through the sole writer via an authenticated
same-site form; a real HTTP subprocess test verifies save and escaped redisplay.

Browser QA used preinstalled headless Edge/Playwright after the in-app browser tool
failed initialization. All nine views returned HTTP 200, with **zero page errors and
zero external requests across 44 requests**. Desktop (1440 px) and narrow-screen
(390 px) screenshots were inspected: readable cards, filters, coverage/gaps, local
chart and scrolling navigation/tables. Empty filter results render explicitly.
Private evidence: `.private/browser-qa.json`, `dashboard-overview.png`,
`dashboard-rankings.png`, `dashboard-mobile.png`. Host/Origin, CSRF, malicious labels,
formula-like model values and source provenance digest checks are fixture-tested.

Query measurement on imported data: warm medians **25–381 ms** across all nine
datasets, with the slowest observed warm run **424 ms**, below the 500 ms target.
Evidence: `.private/m8-query-performance.json`. Browser navigation includes rendering
and cold-load overhead and is not the same metric.

M7 decision: telemetry stays disabled, with no collector dependency or configuration
diff. Current documentation does not establish an installed-version call-ID contract
for useful additional measurements, and no retained OTLP payload exists locally to
verify one. Missing old timing cannot be recovered by enabling future collection.
See [the complete decision](telemetry.md). No user telemetry or analytics setting
was changed; no startup-at-login task was created.

M8 preliminary measurements: a fresh private import/reconcile processed **244,276
records in 29.61 s (8,249 records/s), 261.88 MB peak process-tree RSS**, no failed
sources. A repeat import took **3.96 s**, adding 15 naturally arriving records.
This repeat is not an unchanged-source idempotence claim. The installed optional
tokenizer package has no verified real-model mapping; real tokenization remains
unavailable, and the synthetic offline encoding test must not be extrapolated into
a real-tokenizer throughput claim. Evidence: `.private/m8-import-performance.json`.

Final idle overhead, frozen-source repeat/restart checks and final coverage evidence
remain before M8 completion. Latest full test run before these final refinements:
**67 passed in 43.42 s**; subsequent focused dashboard/monitor/label checks passed.

## Final M8 acceptance, 13 September 2026

The application is delivered and the main loopback service is running. Final suite:
**73 passed in 47.63 seconds**. A transient loopback timeout exposed during concurrent
validation was fixed with bounded stop retries; each retry verifies instance identity.
No PID-kill fallback was added. Source-history write protections remain in place.

Final source audit: **256 exact histories; 6,743 raw response IDs equal 6,743 ledger
responses, zero conflicts and zero mismatches**. The 82 simple-oracle exclusions and
7,736 gap observations remain disclosed rather than guessed. All 384 discovered
sources are accounted for: 342 imported, 38 diagnostic-only, four excluded; none
failed or pending at the saved snapshot. Watermarks and fingerprints are recorded in
`.private/m8-coverage-watermarks.json` and `.private/m8-source-audit.json`.

Frozen-corpus validation: unchanged import **3.704 seconds, zero records/events**;
restart and ten minutes of monitoring preserve exact ordered content digests for
**30,209 usage facts and 41,271 tool facts**. Temporary test workers stopped gracefully.
The main service was separately stopped and restarted on actual history, caught
naturally arriving activity and returned verified running health.

Optimized idle result over **600 seconds**, including full source reconciliation:
**1.47% of one CPU core, 126.10 MB peak process-tree RSS, zero new records**.
Logical I/O: 1,636,375,615 read bytes and 57,829,811 write bytes. This improves the
initial 2.31% CPU and 5.90 GB logical reads, but **does not meet the 1% idle target**.
The other measured import, memory, repeat-import and query targets were met. The
remaining small idle-target deviation and unavailable real-model tokenizer benchmark
are explicit limits, not hidden passes. See [performance](performance.md).

Final browser smoke test: nine HTTP 200 views, no script errors, 44 local requests
and zero external requests. Desktop and narrow-screen screenshots were inspected.
The built wheel contains all templates/static assets/migrations and no private data
(`.private/m8-package-verification.json`). Setup, lifecycle, filtered exports, backups,
rebuilds, optional login setup/removal, coverage and telemetry decisions are documented.

Automatic approval review blocked cleanup of temporary benchmark directories, even
with verified explicit paths, stating only "blocked by policy". The private folders
`.private/idle-source`, `.private/idle-data`, and `.private/benchmark-core` remain for
manual removal. The first contains raw source copies used solely for idle validation.
They are excluded from Git/package output and are not used by the running service.
This housekeeping limitation does not affect imported data or application operation.

| Milestone | Final status |
| --- | --- |
| M0 discovery and format contract | Complete; evidence and adapters recorded |
| M1/M2 ingestion and enrichment | Complete; historical corpus imported |
| M3 accounting | Complete; supported facts independently reconciled, gaps disclosed |
| M4 tool metrics and estimates | Complete; real token estimates remain unknown without a verified mapping |
| M5 lifecycle and monitoring | Complete; synthetic/live restart and deadline checks |
| M6 dashboard and exports | Complete; query, browser, security and export checks |
| M7 telemetry evaluation | Complete; disabled, no collector or config change |
| M8 delivery | Complete with documented idle-target deviation and blocked test-artifact cleanup |

## Optimization usability follow-up

Added separate characters/4 rough text-size estimates, explanatory missing-value
labels, digest-verified on-demand command previews, explicit model-response counts
and non-cached input. Existing normalized character counts were rebuilt into tool
summaries without reparsing or modifying source history. At the check, **37,627 of
41,429 calls** supported rough result sizes; verified model-tokenizer estimates
remain separate and unconfigured. New fields propagate through filtered exports.

Validation: **78 tests passed in 47.88 seconds**, including chunk aggregation,
reported-versus-rough separation, independently expected filtered response/non-cached
totals, credential redaction, HTML escaping, changed-source refusal and completion-record
command previews without result disclosure. Nine browser
views returned HTTP 200 with zero page errors and zero external requests across 44
requests. Desktop/narrow-screen layouts were checked, and an actual recent command
preview was verified through the LAN HTTP route (HTTP 200, no page errors or
horizontal overflow at a 390-pixel viewport). A real preview lookup took 0.8 ms. The service was restarted in the
user-authorized password-free LAN mode. Preview text is not persisted or exported;
redaction is explicitly best effort, and reads/display lengths are bounded.
