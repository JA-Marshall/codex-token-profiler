# Measured performance

Windows, Python 3.12, September 2026. Measurements use existing history and synthetic
fixtures; no model workload was launched to generate data. Memory covers the actual
worker and Windows virtualenv launcher, not just the small launcher process.

| Check | Measurement |
| --- | ---: |
| Fresh import plus accounting/tool reconciliation | 29.61 s |
| Source records processed | 244,276 |
| Overall throughput | 8,249 records/s |
| Fresh process-tree peak RSS | 261.88 MB |
| Repeat import with 15 naturally arriving records | 3.96 s |
| Frozen-source repeat import, zero new records/events | 3.70 s |
| Fresh database, closed worker | 404,307,968 bytes |
| Dashboard query warm median range | 25–381 ms |
| Slowest measured warm query | 424 ms |
| Synthetic default-interval appended record visibility | 1.953 s |
| Synthetic new-file visibility | 28.204 s |

The core-import, repeat-import, memory and warm-query engineering targets were met.
Tokenizer-enabled historical throughput is **not available**: the optional package
is installed and fixture-tested offline, but no suitable real-model mapping has
been established. Assigning an arbitrary encoding just to populate that benchmark
would misrepresent the estimates. No real tokenization throughput is claimed.

The working database at the coverage snapshot was 1,445,302,272 bytes, plus a
93,960,752-byte WAL. It retains earlier parser observations and provenance from
development; this is why it exceeds a fresh rebuild. WAL size varies with active
readers and checkpointing of profiler-owned storage. Codex source databases are
never checkpointed by the profiler.

## Monitoring

A ten-minute naturally active worker interval processed 196 new records, used 8.49%
of one CPU core on average, peaked at 109.68 MB RSS, and recorded 33,648,251,684 logical
read bytes and 1,063,773,299 logical write bytes. This was **not an idle measurement**.
Windows process I/O counters include cached reads and writes; they are not physical
disk traffic or bytes copied from Codex history.

An initial ten-minute frozen-corpus measurement had zero new records, 2.31% mean
single-core CPU, 130.55 MB peak RSS, 5,901,327,839 logical read bytes and 61,834,676
logical write bytes. It exceeded the 1% idle target. Profiling identified a query
planner choosing a full session-index scan for an empty event tail. The worker now
uses the integer-primary-key range and avoids repeated Path construction. A focused
unchanged-poll check fell from approximately 20 ms to 5.42 ms per poll.

The optimized ten-minute repeat completed with **zero new records, 1.47% mean
single-core CPU, 126.10 MB peak RSS, 1,636,375,615 logical read bytes and 57,829,811
logical write bytes**. CPU fell 36%; logical reads fell 72% from the initial idle
run. The **1% idle CPU target remains unmet** by 0.47 percentage points. This is a
recorded engineering-target deviation; correctness and visibility deadlines remain
unchanged. The measurement includes default periodic full-source verification.

The frozen corpus contained 954,381,843 rollout bytes plus read-only database
snapshots. Only copied state rollout-path references were redirected into that
temporary corpus; original history was not changed. A repeat import added zero
records/events in 3.70 seconds. Restart and the monitoring interval retained
identical content digests for all 30,209 usage facts and 41,271 tool facts. Both test
workers stopped gracefully.

Automatic approval review blocked recursive cleanup, including a retry with explicit
verified paths, with the reason "blocked by policy". Therefore temporary validation
folders remain: `.private/idle-source` (raw source copies), `.private/idle-data` and
`.private/benchmark-core` (profiler databases). They are private local test artifacts,
not used by the running application and not included in its package. They can be
removed manually in File Explorer; preserve the sibling JSON evidence reports.
No original Codex source or live profiler directory is a cleanup target.

Private evidence: `m8-import-performance.json`, `m8-query-performance.json`,
`m8-idle-performance.json`, `m8-frozen-idle-performance.json`,
`m8-frozen-idempotence.json`, and `m8-optimized-idle-performance.json` in `.private/`.
All listed reports are present in this working directory.
