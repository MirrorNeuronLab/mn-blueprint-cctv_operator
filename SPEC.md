# CCTV co-worker 6.2.0

## Product and compatibility

One to four approved RTSP/RTSPS cameras per Job. Describe visible activity in
sampled video windows and preserve each camera's timestamps, source references,
live preview and saved observations. One supervised monitoring goal applies to
all selected cameras. The original `video_source.uri` config still selects a
single camera. `video_source.count` activates the corresponding additional
secure stream URL fields. Duplicate camera locators are invalid.
This replaces the previous implementation using Spark's rt_vlm sample. Previous
graphs, detector policies, model recipes and private databases are retired.

## Execution

The required NVIDIA vss-rt-vlm 3.3.0 container owns analysis decode/sampling and
Cosmos3 Edge inference. Pin the sample's ARM64/SBSA digest. Defaults: four-second
windows, eight frames, 608×320 input, 192 tokens, temperature 0.2, no reasoning
or audio. Discover the model from /v1/models after /v1/ready; an empty model list
cannot establish readiness. No person gate, semantic decision model or alternate
inference provider exists.

Core owns native Compose preparation, selected-node placement, health and project
cleanup. Reserve loopback port 8019 and hard-require NVIDIA CUDA with 49,152 MB
GPU/unified memory. One VSS stack per node; pre-provisioned external model-cache
volumes persist independently of Compose cleanup. The Python 3.12 HostLocal
operator connects through the private runtime network; native Compose health
checks use the host-loopback endpoint. Internal MCP/workspace listeners use
Core-assigned ports. Recompile vLLM graphs at startup because the pinned image's
serialized compilation cache fails PyTorch's metrics-context check on Spark;
model weights remain cached and GPU inference stays compiled.
SDK monitored-service hooks supervise the operator's
listeners, streaming task, preview and publication. Startup is bounded to 1,200
seconds; health checkpoints to 64 MiB/1,000,000 cycles, five seconds apart.

Current platform limitation: delivery-v2 pause interrupts the long-running native
invocations. Core fences their replay as `invocation_outcome_unconfirmed`; automatic
resume is not supported by this qualification. Preserve that guard. Stop releases
the project; an explicitly new run can continue using the Job's saved captions.

Record a stable stream ID for the Job and camera slot before calling NVIDIA.
Reuse it across registrations so NVIDIA rejects a duplicate even if an earlier
registration reply was lost. Require the registration receipt to confirm that
ID before captioning. The managed NVIDIA service registers without a separate
GStreamer discovery connection; the caption pipeline opens and decodes the
actual RTSP feed. Consume /v1/generate_captions SSE, cancel the caption request
using its request ID when available, then delete the stream. Only 409 stream
deletion receives five bounded attempts. Each camera owns one caption request on the shared model.
Stop and goal changes await the cleanup of every request before replacement.
Retain unverifiable cleanup separately for each camera slot.
At startup reconcile all saved leases, including removed slots, before registering
any camera. A failed feed leaves other feeds running and reports the error on its
own tile. A run with no remaining analysis sessions reports a service failure.
The pinned NVIDIA AssetManager reports an absent resource with HTTP 400,
`BadParameter`, and an exact resource-specific message. Its `No such resource
<stream-id>` and `<stream-id> already deleted because of age out policy` receipts
prove a saved stream is gone after restart/expiry and complete cleanup. Other
400 responses, wrong identities, and transport failures retain the cleanup
record. A legacy registration with no saved stream ID cannot be reconciled by
ID. Clear its pending record only after confirming the owning NVIDIA process
has exited and its live stream registrations are gone.
An exact `InvalidParameterValue`/400 receipt naming both the saved request and
stream as having no active caption request permits continuing to stream deletion.
It does not prove the stream is absent. Stream deletion must independently
succeed or attest that exact stream is gone before clearing the saved lease;
409 exhaustion, other failures, mismatched IDs and missing request IDs preserve it.

## Evidence and persistence

Validate camera input without echoing credentials. URI data never enters public
state, captions, reports or Chat. Bind storage to Job identity and history to a
credential-free camera locator hash. A process lock enforces one Job owner.

Require bounded nonempty captions, chronological timezone-qualified capture
bounds, valid optional finite non-negative latency and complete output. Reject
private reasoning. Deduplicate session/window identities. Save complete source
accounts before final SDK activity publication. Model errors, unexpected EOF,
invalid records and cleanup failures remain visible. Preview health is separate.

Save immutable caption JSON, complete source Markdown, cumulative JSON/Markdown
reports, monitoring state and the standard final artifact. Reports/export/workspace
are bounded to 300 current-run accounts with omissions. Source-scoped Job history
stops at its explicit 10,000-account capacity without automatic deletion. A chronological history read returns up to twelve accounts and omissions. The separate
question tool searches acknowledged Membrane text and image units for the configured
cameras across runs of this Job, constrained by the requested capture interval. It resolves relative intervals
once at dispatch and preserves them through polling and retries. Old caption-only
accounts remain searchable. Report pending indexing and sampled coverage.

NVIDIA's caption protocol does not return selected image evidence. Preview and
window snapshots use the independently decoded preview. Save only a JPEG received inside
the window. A localization must come from a separate review of that exact JPEG. Captions remain
fallible sampled descriptions. Do not infer exhaustive coverage, unique people,
identity, compliance, calibrated confidence, verified incidents or safety. No
external messaging or physical action occurs. A human reviews original video.

## Supervision

Use standard Job MCP supervision. Domain tools read per-camera status, final
activity, saved history and retained NVIDIA timing, or set the shared monitoring prompt. Durable caller
IDs reject conflicting reuse. Preserve arbitrary visible subject/condition/negation.
An applied prompt is separate from a later completed window; clear restores the
configured goal. Chat shows the first completed window per camera and goal
revision and the start of each possible sighting. The read-only workspace has up
to four live previews and newest-first event and goal timelines with
camera-labeled saved images. Compose its dashboard with the shared web report
template, vendored unchanged, and blueprint-owned presentation styles. Summary
cards report connected previews, cameras with preview/analysis errors, completed
observations in the current run and positive matches for the current goal. These
counts do not imply incidents, acknowledged findings or exhaustive coverage.
Keep the previews above the timeline in narrow windows and to its left in wide
windows. Each camera card shows its name, preview health and analysis status
separately. A camera selector and per-card focus control expand one preview;
returning to all cameras restores the grid. Selection and resizing reuse each
camera's existing stream and leave the all-camera timeline unchanged. Remove
obsolete camera tiles when the configured set changes. Only the event stream
scrolls in the default view; condense summary cards in narrow panels and hide
them in short panels. The shared monitoring goal starts collapsed and opens
from the target icon beside the camera selector. Preview labels and tooltips
preserve camera identity. Routine diagnostics remain available
through Chat and export. History answers preserve the camera, verdict and any
image-grounded box of a reviewed still. A positive structured verdict is required
for the goal view. SDK/Core retain lifecycle controls, public authentication and
envelopes.

The read-only workspace polls saved state every two seconds and restores after
reload. Render model text as text. Keep credentials, action endpoints and raw
NVIDIA APIs out of the browser. Preserve capture/receipt time distinctions and
prevent horizontal overflow through narrow/wide resizing.

## Acceptance

Offline tests cover real compiled bindings, protocol parsing, source isolation,
persistence, cancellation/cleanup fencing, goal receipts, read-only HTTP, text
escaping, layout and native lifecycle. Live acceptance needs consecutive NVIDIA
captions from each selected camera, goal replacement, previews, durable history and
proven release of owned requests/streams. Prior sample results are not acceptance
for this implementation. Measure model/window timing separately from loading,
startup and end-to-end incident latency. Site accuracy needs labeled footage.
