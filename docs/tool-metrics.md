# Tool metrics and estimates

Call records, outputs and completion projections share a canonical invocation when
native identity and owning session agree. Cross-thread copies merge only along an
observed ancestor relationship; unrelated threads reusing an ID stay separate.
Parser upgrades use the newest interpretation of physical bytes. Original source
records remain available for provenance. Actual invocation counts do not include
content-only reasoning/message items.

Explicit error/success/exit status determines failures. A call without output is
pending; output without an explicit outcome remains `unknown_outcome`. Execution
duration and observed call-to-result wall time are separate millisecond fields.
Zero duration remains zero. A completion projection's aggregate result takes
precedence over formatted output copies; without one, observed async chunks from
the most complete source sequence are combined. No result is added once per mirror.

`functions.exec` is an opaque outer invocation unless explicit child identifiers
are present. No JavaScript or shell text is executed or regex-expanded into a
fictional nested-call graph. The `level` and `coverage` columns disclose this limit.

Command fingerprints retain exact argument order. Recognized read-tool arguments
and structured command read actions include the supplied path/range/command in a
locally salted hash. Neither commands nor paths are stored in the pattern itself.
Repeated commands and reads are separate occurrence kinds. A failure followed by
the same fingerprint in the same session within `--retry-window` seconds (default
600) is a **likely retry**, not proof of waste or equivalent-quality work. Occurrence
records link back to the invocation and its original source records.

## Optional local tokenizer

No real model mapping is enabled by default. Bytes/characters remain available;
unknown token estimates remain null. Installing the extra does not enable a model
mapping and does not download encoding assets during ingestion:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-tokenizer-lock.txt
```

When a model's encoding is independently established, prepare its BPE file separately
in profiler-owned storage and create `%LOCALAPPDATA%\CodexTokenProfiler\tokenizers.json`:

```json
{
  "models": {
    "EXACT_VERIFIED_MODEL_NAME": {
      "bpe_path": "C:/absolute/profiler-owned/path/encoding.bpe",
      "sha256": "SHA256_OF_LOCAL_BPE_FILE",
      "encoding": "VERIFIED_ENCODING_NAME",
      "pattern": "VERIFIED_ENCODING_REGEX",
      "special_tokens": {}
    }
  }
}
```

Use the encoding's actual special-token table and regex; placeholders above are
not a working model mapping. BPE rows are base64 token bytes followed by an integer
rank. There is no implicit model-family guess and no network fallback. Missing,
corrupt or unmapped assets yield unknown estimates. The stored estimate records
encoding, package version, explicit-map provenance and BPE digest. No encoding file
has been downloaded or real-model mapping enabled as part of this implementation.

Mapping changes apply when source observations are parsed. Existing retained size
measurements are not silently re-tokenized by an unchanged import. To backfill a
newly verified mapping, prepare `tokenizers.json` and its local assets in a fresh
profiler data directory, then run `reconcile --data-dir` for that directory. Preserve
your original database and labels as described in `operations.md`. This also makes
comparisons between mapping versions reproducible.

Arguments and results are measured separately. Structured text serialization is
labeled; mixed image/audio/video content measures only extracted text for the token
estimate and flags unsupported media. Truncated retained content is flagged partial.
These are visible-content token-size estimates, never exact billed tool cost.

## Optimization views

The dashboard additionally computes `rough_argument_tokens` and `rough_result_tokens`
as retained text characters divided by four, rounded up per invocation. This is a
language-dependent heuristic, **not a verified model-tokenizer count**, and never
fills the reported-usage or tokenizer-estimate fields. It excludes non-text media
from the character count; partial/truncated content stays marked partial. Missing
character measurements remain unavailable rather than becoming zero. Rankings show
how many calls support the rough subtotal; wrappers and inner outputs may overlap.
CSV/JSON include the heuristic method separately. Existing normalized character
counts are reused, so no source re-tokenization or external request is required.

Tools and Results have a **View command** link; pattern occurrences link to the same
detail page. It reads at most eight registered call or completion records, each capped at 1 MiB,
verifies their byte digests and displays at most 2,000 characters of command/path
fields or custom-tool input. Common credential formats are redacted on a best-effort
basis. Preview text is escaped, never executed, never persisted by the profiler and
not included in CSV/JSON exports. Full tool results and conversation messages are
not served. Changed, removed, oversized or unsupported sources show a specific reason.
LAN users can view these previews when password-free LAN mode is enabled.

Overview, Sessions and Comparisons now show recorded response counts and non-cached
input. Responses count explicit response facts only; cumulative intervals do not
establish individual model-call counts. Non-cached input is input minus cached input
per fact, only where both counts are known and consistent. It includes cache writes
and is not a billing or subscription-quota measure. These values follow the same
filters as exports and reported totals.

Validation includes real `tiktoken 0.11.0` against a hand-authored byte encoding with
network connections disabled. That synthetic encoding is not used for real history.
