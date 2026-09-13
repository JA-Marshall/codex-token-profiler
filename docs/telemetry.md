# Supplemental telemetry decision

Decision, 13 September 2026: leave telemetry disabled. There is no collector,
exporter, telemetry dependency, or user-config change in this release.

The [official observability documentation](https://learn.chatgpt.com/docs/config-file/config-advanced#observability-and-telemetry)
describes tool-result duration, success and snippets, and stream completion usage.
It identifies conversation metadata but does not establish a native call-ID contract
for these log events. Its duration and token histograms cannot identify individual
responses or invocations. This is insufficient evidence for a safe additive source.

Local inspection found no configured OTel exporter or retained OTLP payloads to
verify against this installation. Existing call/completion/projection correlation
already supplies 8,867 explicit durations at the M4 watermark. Older missing timings
remain unknown. Potential future timing improvement is plausible, but neither an
installed-version payload nor reliable invocation correlation has been demonstrated.
Enabling collection cannot recover missing historical timings.

The [App Server event interface](https://learn.chatgpt.com/docs/app-server) is a
separate integration. Launching a server is not established as a passive subscription
to every running desktop thread; no test model turn was launched to probe it.

A future adapter requires a versioned payload with explicit thread/call/response
identifiers, local-only transport, bounded parsing, snippet removal, duplicate and
reorder tests, and evidence of fields absent from current sources. It must remain
supplemental until correlation is proven. Any proposed configuration must be reviewed
before activation, target loopback, disable prompt content and external export, and
include exact rollback steps. There is no configuration diff to approve or roll back
now, and unrelated Codex analytics settings were not changed.
