# Source format contract

The implementation uses binary, bounded JSONL reads and SQLite URI `mode=ro`
with query-only connections. It never runs a Codex turn. Source bodies are
inspected transiently; diagnostics retain offsets, hashes, numeric counters,
identity context and field names. Private inventory reports belong in `.private/`.

## Observed families

Rollouts contain `session_meta`, `turn_context`, `event_msg/token_count`,
`token_usage_record`, `response_item`, `event_msg/item_completed`, settings events,
and `compacted`. Metadata can change inside one file. Replacement history inside
compaction is replay, not an additive event stream. Nullable token info occurs.
Version signatures range across 15 CLI versions; adapters must select by shape.

Response usage contains separate response, turn-cumulative and thread-cumulative
objects. Legacy total snapshots can repeat and decrease. Cached input and reasoning
output are subsets, not extra categories. Unknown values must remain null.

Raw completion items use PascalCase tags and snake_case fields; SQLite projections
use camelCase tags and fields. `{secs: 1, nanos: 250000000}` corresponds to
`durationMs: 1250`. Projection rows can mutate without changing their item IDs.
Database-only user messages establish session coverage without token usage.

`state_*.sqlite` supplies threads, rollout references and spawn edges. The desktop
catalog supplies explicit project IDs and local/remote host context. History
tables include turns, items, realtime items and projection offsets. Schema columns
are inspected before selecting optional fields. Logs are diagnostic-only pending
a demonstrated useful correlation adapter. Memory, queue and goal stores are
excluded because their bodies and duplicate counters are not independent spend.

## Counter-decrease policy

The initial fresh scan reproduces the known decreases. Numeric/identity evidence
is preserved for each in the private inspection report. A changed turn with
`last == total` suggests a reset but alone does not prove thread-counter semantics.
Compaction, changed identity or inherited prefixes also cannot imply new spend.
Until response or explicit boundary evidence resolves an interval, it remains
unresolved. Accounting must not clamp negative deltas or blindly start at zero.

The duplicated first metadata ID has two nonidentical files, including a short
second file associated with a database-only thread. Both remain eligible; neither
path nor the first metadata ID may serve as the sole semantic identity.

Hand-authored shape/numeric fixtures live in `tests/fixtures/families.py`.

## Official interfaces inspected 2026-09-13

[App Server](https://learn.chatgpt.com/docs/app-server) documents usage updates and
item lifecycle notifications. It does not establish a passive subscription to all
already-running desktop processes; no app server is started for collection.

[Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry)
documents optional OTel event export, tool-result timing and snippets. Aggregate
histograms cannot be treated as per-response facts. Local telemetry remains off;
no user configuration is changed. M7 will evaluate correlation after base coverage
is implemented. The public API does not stabilize private persisted schemas.
