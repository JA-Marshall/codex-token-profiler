# Operations

`start` launches the virtualenv interpreter in a hidden process, verifies its random
instance ID over loopback and waits for import health. A second `start` returns the
same instance. `run` is the foreground form. One OS-held lock protects each data
directory. Dashboard queries and exports use read-only SQLite snapshots.

`stop` verifies the instance and submits its private control token, then waits for
the current transaction and writer lock to finish. It never kills a stored PID.
`status` reports stale or degraded instances rather than trusting heartbeat files.
After an interrupted process, `start` resumes committed checkpoints. If another
process owns the selected port, choose `--port 8766`.

Default intervals: known files every two seconds, discovery every 30 seconds,
full fingerprint/revision reconciliation every 300 seconds. Override with
`--poll-interval`, `--discovery-interval`, `--reconcile-interval`. Main-file and WAL
metadata invalidate the routine scan cache. Full scans verify contents even when
size/mtime are preserved. Error sources are retried. A partial trailing record is
pending, not malformed or measured usage. A closed file lacking its final newline
can be explicitly accepted after stable validation with `--finalized-source PATH`
on a manual import/reconcile.

`last_success` is the latest completed scan/poll, not the time of a model response.
`last_reconcile` is the last full source scan. Pending bytes measure known incomplete
tails; newly created files wait for discovery. Old source timestamps do not imply
an unhealthy watcher. The dashboard refreshes health every five seconds; refresh a
table to see new facts. Accounting gaps and unknown schemas are separate from health.

## Backup and rebuild

Stop the worker and verify `status` reports `stopped` before copying the entire
profiler data directory to a private backup folder. Preserve the database and any
remaining WAL/SHM sidecars together, plus `tokenizers.json` and local BPE files.
Benchmark labels and the pattern salt live in the profiler DB. Do not copy only a
live main database file. Backups contain private paths and metrics.

Test a clean rebuild without deleting anything by choosing a fresh directory:

```powershell
.\.venv\Scripts\python.exe -m codex_token_profiler reconcile --data-dir "$env:LOCALAPPDATA\CodexTokenProfiler-Rebuilt"
.\.venv\Scripts\python.exe -m codex_token_profiler start --data-dir "$env:LOCALAPPDATA\CodexTokenProfiler-Rebuilt" --port 8766
```

A rebuild recovers only source history still available. The existing DB can retain
observations from subsequently removed/truncated sources. Export labels before
rebuilding: annotations are not source history. Migrations affect only profiler
storage. No Codex database migration, checkpoint or journal-mode write occurs.

## Optional login startup (not enabled)

After verifying `start`, use Windows Task Scheduler's **Create Task** if desired.
Name it **CodexTokenProfiler**, select your user and **Run only when user is logged
on**, with an **At log on** trigger for that user. Do not enable elevated privileges.
Set the action to **Start a program**:

- Program: `C:\Users\james\Desktop\Code\Emory\.venv\Scripts\python.exe`
- Arguments: `-m codex_token_profiler start`
- Start in: `C:\Users\james\Desktop\Code\Emory`

Choose **If the task is already running: Do not start a new instance**. The launcher
exits once the hidden worker is healthy; use the profiler `stop` command to stop
that worker. To undo login startup, disable or delete this named task in Task
Scheduler, then run `stop`. No scheduled task has been created here.

## Privacy and troubleshooting

By default the server binds only `127.0.0.1`. With `start --lan` or `run --lan`, it
binds IPv4 interfaces without a password, accepting this computer's local addresses
and hostname in Host/Origin checks. LAN access was explicitly enabled by the user
after initial delivery. The server uses a
same-site CSRF token for labels. It serves local assets only. Other processes with
access to your account can read your profiler data; keep its folder private.

Use `discover --inspect` for schema/coverage inventory and `audit` for independent
raw-source arithmetic. Reports contain paths and identifiers; `.private/` is ignored
by Git. `service.log` records startup failures. Error reporting retains exception
classes and locators, not conversation bodies. New schema gaps must not be filled
with guessed usage.

The service requires no Codex model credentials or Internet connection. Package
installation is a separate setup step. No exporter or automatic tokenizer download
exists; see [telemetry](telemetry.md) and [tokenizer assumptions](tool-metrics.md).
