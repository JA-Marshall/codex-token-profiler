# Coverage and limits

At the 13 September 2026 delivery audit, all **338 rollout files** and the supported
state, history, catalog and session-index sources were imported: 342 sources total.
Another 38 logs were diagnostic-only and four databases were explicitly excluded.
There were no failed or pending sources at that snapshot. Coverage begins
**26 June 2026 12:21 UTC** and continues with naturally arriving local activity.
These are snapshot counts; the dashboard reports the current state.

The private `m8-coverage-watermarks.json` records committed offsets and fingerprints.
The independent source audit records its own exact watermarks. Files can append
after those points without invalidating the completed-prefix calculation. Raw
JSONL provenance links verify the retained byte-range digest against the current
source. Removed/rewritten bytes report unavailable/changed; database references
identify table/row revisions checked during import, not a guaranteed live row match.

## Reported usage

The independent arithmetic audit agrees on every token category for **256 supported
monotonic source histories** (including 55 archives, 128 branched histories and 44
with compaction; these groups overlap). The other 82 have explicit oracle exclusions:
33 unproven initial boundaries, 29 multiple metadata epochs, 14 counter decreases,
five missing-category cases and one without cumulative usage.

A separate raw response-ID audit agrees on ownership and all categories for
**6,743 response IDs**, with no conflicts or mismatches at its recorded watermark.
This supports the included facts; it does not make excluded intervals complete.

At the coverage snapshot, 7,736 accounting-gap observations remained:

| Gap class | Observations |
| --- | ---: |
| Inherited cumulative usage without supported allocation | 3,482 |
| Null or invalid cumulative observation | 6 |
| Unexplained counter decrease | 66 |
| Subsequent unresolved epoch interval | 4,182 |

These are observations, not 7,736 disjoint token amounts. They must not be summed
into usage or used to extrapolate missing consumption. The dashboard reports known
subtotals and exposes gaps. Unknown date/model attribution is not assigned from
today's model settings. Cached input and reasoning output remain subset categories.

## Tools and workflow comparisons

Calls, completions and database mirrors merge by supported identity and ownership.
An explicit duration is different from observed wall time; missing timing remains
unknown. Result bytes measure retained content. Token sizes require a verified
offline encoding and are estimates, never billed cost. No verified real-model
tokenizer mapping is configured in this delivery.

Explicit nested invocations are represented where available. Opaque outer calls
such as `functions.exec` cannot disclose an invented inner graph. Repeated command
and read hashes retain semantic distinctions such as ranges and argument order,
but the hashes do not retain plaintext commands. Follow occurrence provenance to
inspect the original record locally. Likely retries are heuristics, not proof of
waste, quality equivalence or causality.

Own-thread and unique-descendant comparisons avoid multiplying inherited parent
history. Optional labels are annotations, not accounting inputs. Timeline proximity
does not assign a response's usage to a preceding tool. Missing local/cloud history
remains outside measured coverage, and subscription quota is never inferred.

## Storage and versioning

Private Codex disk schemas are not a public compatibility contract. Adapters retain
unsupported diagnostics and original locators instead of inventing fields. Parser
upgrades can preserve earlier physical observations for provenance while canonical
facts use the latest supported interpretation. Consequently an upgraded working DB
can be larger than a fresh rebuild. Rebuilding loses source bytes no longer available
and does not recover user annotations automatically; see [operations](operations.md).
