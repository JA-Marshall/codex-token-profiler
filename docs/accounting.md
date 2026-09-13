# Reported usage accounting

The ledger stores reported usage separately from tool-size estimates. Input includes
cached input; output includes reasoning output. Cache-write input is retained without
inventing a billing treatment. Unknown categories remain null. Counts do not measure
subscription quota, money or causal tool cost.

Unique response IDs are the preferred evidence. Repeated observations support one
fact; conflicting numeric observations remain discrepancies. Legacy snapshots are
ordered within source identity epochs. Repeats add zero. Component deltas supply
uncovered legacy intervals. A first snapshot without a verified initial boundary
is an unallocated historical subtotal. No current model/date is assigned to it.

Counter checkpoints are matched in sequence because legacy notifications can lag
the corresponding response record. A constant historical offset between the newer
thread counter and legacy counter is accepted only when exact component deltas
establish it. Residuals must be nonnegative and scope-compatible. Response counts
never get added on top of a cumulative interval that already includes them.

The source adapter preserves metadata epochs. In the observed nested-metadata
family, a child header is followed by replayed parent metadata. The explicit replay
boundary restores the child's original context after that prefix. This does not
assume every history-start ordinal in every old format means the same thing.
Incomplete projection turn coverage cannot globally override source ownership.
When a parser is upgraded, the latest interpretation of the same physical bytes
is used; older supporting provenance is retained, not counted as independent facts.

## Disclosed unknown intervals

Unexplained decreases are not clamped or treated as automatic resets. Subsequent
cumulative intervals remain unknown until an explicit zero baseline or independent
response evidence establishes consumption. Reported response facts remain available.
Some older child files contain reconstructed parent counters with rewritten times
and unproven ownership. Those inherited cumulative intervals are disclosed rather
than presented as the child's spend. Missing/null counters remain coverage gaps.

## Independent validation

`python -m codex_token_profiler audit --output .private/source-audit.json` reads
original source bytes through each committed watermark and validates their hash.
It does not call the accounting/normalization functions. Its monotonic-source oracle
compares final counters (or complete response sequences when notifications lag)
against canonical per-session totals. A second oracle compares every native response
ID, owning thread and token category directly with the ledger. A test deliberately
corrupts a ledger total and verifies the independent oracle detects it.

On the 2026-09-13 validation pass: **256 histories matched exactly**, including
55 archives, 128 branched histories and 43 histories with compaction. The categories
overlap. The other 82 files are explicitly outside the simple lifetime oracle:
33 unproven first boundaries, 29 multiple metadata epochs, 14 decreases, five missing
category cases and one with no cumulative usage. Across the entire corpus,
**6,626 response IDs matched all categories and ownership**, with no conflicts or
mismatches. These are watermark-specific results, not a claim of complete usage in
the acknowledged unknown intervals.
