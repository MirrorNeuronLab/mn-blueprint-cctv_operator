# CCTV co-worker

The CCTV workspace follows the working sample at
`spark:/home/homer/Sandbox/rt_vlm`. NVIDIA `vss-rt-vlm` 3.3.0 owns DeepStream
video decoding, window sampling and Cosmos3 Edge inference. The co-worker saves
completed streaming captions and supplies separate, read-only live previews.
Version 6.3 monitors up to four cameras from one co-worker and labels observations
and snapshots with their camera.

## Start

In **Camera streams** during first-run setup, choose **Camera count**, enter an
approved RTSP or RTSPS URL for each selected camera, then choose **Start monitoring**.
Use **Configure** to save up to five **Monitoring goals** for the next run.
Enter one visible condition per line, such as “People without safety helmets”
or “Loading door left open”. Every goal applies to every selected camera.
Leave the field blank to monitor general activity. Enter stream addresses
that both the NVIDIA container and the preview service can reach. Keep
credentials in the secure URL fields.

```bash
mn blueprint run ./cctv_operator --node mirror_neuron@10.0.4.32 --web-ui \
  --set video_source.uri=rtsp://camera.example/approved-stream
```

For a four-camera test, a local publisher can serve sample clips at
`rtsp://127.0.0.1:8554/stream/1` through `rtsp://127.0.0.1:8554/stream/4`.
Use the publisher address reachable from the selected runtime and container for
each URL. `127.0.0.1` refers to the connecting process's own network namespace.

```bash
mn blueprint run ./cctv_operator --web-ui \
  --set video_source.count=4 \
  --set video_source.uri=rtsp://camera.example:8554/stream/1 \
  --set video_source.camera_2.uri=rtsp://camera.example:8554/stream/2 \
  --set video_source.camera_3.uri=rtsp://camera.example:8554/stream/3 \
  --set video_source.camera_4.uri=rtsp://camera.example:8554/stream/4
```

For manual runs from this checkout, the same settings can go in
`config/overwrite.json`. This example uses the four local sample URLs. Adjust
the host before running on a separate computer or in a container.

```json
{
  "video_source": {
    "count": 4,
    "uri": "rtsp://127.0.0.1:8554/stream/1",
    "camera_2": { "uri": "rtsp://127.0.0.1:8554/stream/2" },
    "camera_3": { "uri": "rtsp://127.0.0.1:8554/stream/3" },
    "camera_4": { "uri": "rtsp://127.0.0.1:8554/stream/4" }
  }
}
```

Refresh the prepared Job when it is idle, then start a new run to use this version. Existing runs retain
their original bundles. The NVIDIA computer needs Docker Compose, the NVIDIA
Container Toolkit, camera connectivity, 48 GiB GPU/unified memory and 25 GB free
disk. The digest in `payloads/vss/compose.yaml` is the sample's ARM64/SBSA image,
targeting DGX Spark. Other hardware requires a matching image and qualification.

## Runtime

Core's native DockerCompose runner prepares and supervises the required NVIDIA
container. Loopback port **8019** is an explicit resource reservation: one CCTV
VSS stack per node. It does not replace the sample on port 8018. Model caches
are external named Docker volumes retained after stop. Initialize them once on
the NVIDIA host before the first hire:

```bash
docker volume create otterdesk-cctv-hf-cache
docker volume create otterdesk-cctv-model-cache
```

The CPU operator runs in Core's prepared Python 3.12 environment through
HostLocal. NVIDIA joins the private runtime network at `otterdesk-cctv-vlm:8000`;
its host-loopback port is reserved for native Compose health checks. MCP and the
workspace use Core-assigned internal ports. The workspace registration advertises
Core's private container interface so the separate UI proxy can reach it.
Camera credentials never enter
Compose. The operator has no container-management capability.

The pinned NVIDIA image contains serialized compilation artifacts that fail
PyTorch's metrics-context check on Spark. The recipe uses vLLM's supported
`VLLM_DISABLE_COMPILE_CACHE=1` setting to compile fresh at startup while keeping
GPU inference and CUDA graphs enabled. Model weights remain cached. See
[vLLM's compilation documentation](https://docs.vllm.ai/en/v0.17.1/design/debug_vllm_compile/).

The SDK `mn.blocks.monitored_service@1` owns the Python operator's lifecycle,
health and checkpoints. Domain hooks own listeners, the streaming request,
preview and publication. First startup can download/compile the model; readiness
waits up to 20 minutes. Use main SDK 1.4.1.dev44 or newer on both submitter and owner for durable inline
Compose activation. Core owns pause/resume/stop and removes only the run's
owned Compose project. No runtime reset is required.

Core's current delivery-v2 contract fences an interrupted long-running invocation
as `invocation_outcome_unconfirmed`. Pausing releases this stack, but resuming that
interrupted run is not qualified; the live test reproduced the fence. Use a new
run after stopping. This rewrite does not bypass Core's uncertain-effect guard.

The direct protocol discovers one shared model. Each camera has a stable NVIDIA
stream ID that the operator saves before registering it. A lost reply leaves
an ID the operator can use to clean up. NVIDIA rejects duplicate registrations
with that ID. The dedicated NVIDIA container opens the camera through its
caption pipeline without a separate discovery connection during registration.
Stop lets in-flight registration settle, cancels the caption request and
deletes its stream. Failed cleanup retains the durable lease.
Every outstanding lease must be reconciled before starting another run, even
after reducing the camera count. For a legacy pending registration with no
stream ID, verify that the owning NVIDIA service has stopped before clearing
the pending record. Only resource-in-use stream deletion is retried.
After a VSS restart, NVIDIA's exact `BadParameter`/HTTP 400 receipt naming the
missing stream reconciles its saved lease. Other errors still require verified
cleanup before another registration.
If NVIDIA reports the exact saved caption request is no longer active, cleanup
still deletes its stream registration before clearing the lease. A stream still
in use or any mismatched error retains the fence.

## Observations and controls

Defaults analyze eight frames per four-second window at 608×320, with 192 output
tokens, temperature 0.2, reasoning and audio disabled. Each camera's CPU/PyAV
preview updates up to four times per second. The cameras share one NVIDIA model,
so inference latency depends on the combined load. Preview health and completed
analysis are reported per camera.

**Everything** shows the newest completed window first. **Goal matches** shows
only windows with an explicit match for at least one current goal, including
matches older than the most recent routine windows. **Cameras at a glance** uses
the shared web report template, with summary cards for connected previews,
cameras needing review, completed observations in this run and possible matches
for the current goals. Connection health is separate from analysis status.
Review the original video before acting on possible matches.

The camera cards show all configured sources, with the name, preview health and
analysis status on each card. Use **Preview camera** or a card's expand button
to focus on one feed; **All cameras** restores the grid. Switching previews does
not filter the observation timeline or restart the streams. The shared timeline
scrolls and labels each observation with its camera. In a side panel, the cameras
stay above the timeline; in a full window, they stay on the left with observations
on the right. The summary condenses in narrow panels and hides in short panels
to preserve space for video and observations. Light and dark appearances use the
unchanged shared template tokens.

Select the target icon beside the camera selector to show or hide the current
monitoring goals. Both observation views show saved frames. Select a frame to
inspect it with any image-grounded highlight. Timings
and indexing coverage remain available through Chat and **Export**.
**Show earlier** pages through all retained entries for this run, 300 at
a time. **Back to latest** resumes following new windows.

Chat records the first observation for each camera and set of goals. Each
possible sighting starts an alert naming the newly matched goals. Continuing
sightings share that alert until a clear sample shows the condition has ended.
Use **Change monitoring goals** in Chat to replace the list for the current run.
**Restore saved goals** restores the list the run started with. A failed feed
is marked **Needs review** while other feeds continue.

To forward these alerts, open the co-worker’s **Integration** tab in OtterDesk,
connect Slack, and link an approved public channel. New possible matches appear
as text posts in the channel while OtterDesk is running and Slack is active.
Saved frames are available in Chat and the CCTV workspace.

The NVIDIA stream supplies caption intervals. The co-worker independently
buffers preview JPEGs and saves the one received nearest the midpoint, only
if its receipt time falls inside the interval. The thumbnail is labeled with
that time. A box is shown only when a second assessment of those exact JPEG
bytes locates a target. An observation can have no snapshot or no box.

## Search saved footage

Ask **“Did you find anyone wearing a red coat in the past hour?”** Chat searches
the configured cameras across runs of this Job. Search results name the camera
and include index coverage.
A background task indexes the caption and available
original JPEG as distinct Membrane source units. Earlier 6.0 observations are
indexed from their captions. Their images were never saved.

The blueprint's CPU operator loads Google's pinned EmbeddingGemma 2 weights
with Sentence Transformers. First use needs access to download the model or an
existing Hugging Face cache. Image, document, and query vectors share a
768-dimensional space. [Google's image encoder guide](https://ai.google.dev/gemma/docs/embeddinggemma/multimodal-embeddinggemma-with-sentence-transformers).

Membrane acknowledges the vectors before a window
counts as indexed. It ranks images by semantic similarity and captions by
hybrid search inside the requested capture interval. The existing NVIDIA
service reviews up to four candidates. Chat shows capture times, citations,
index coverage and the best reviewed snapshot when available, including uncertain or negative results with their verdict. Sampled observations
can miss activity.

## Saved state

Use **Save report** in the live workspace to download the latest camera assessment. Shutdown also saves `report.html`. It cites up to 50 completed windows from this run, their cameras, capture times and individual records. Earlier windows are counted in coverage.

SDK run storage is authoritative; `~/Downloads/cctv-operator` is an additional
runtime-delivered host copy. Outputs are `captions/*.json`, available `snapshots/*.jpg`, `cctv_report.json/md`,
`monitoring_state.json`, `final_artifact.json`, complete
`context_sources/outputs/*.md` accounts and `operator_activity.sqlite3`.
Published caption/report/status files use mode 0644 so the runtime's host sync
process can replicate container-root writes. Camera credentials and cleanup leases
remain outside those published accounts in Job state.

The declared Job state resource owns `realtime_vlm/captions.sqlite3`, source-scoped
history, command receipts and cleanup leases. History survives runs for each camera
in the same Job. A process lock prevents two operators owning one Job. The 10,000
caption capacity is shared across the Job. Review/export retention
before continuing. Reports/workspace/export show the latest 300 current-run
captions with omission counts; `get_video_history` returns up to twelve accounts,
optionally filtered by timezone-qualified capture bounds. It never reruns vision.

Other domain tools read status, completed activity and NVIDIA timings, or replace
the set of monitoring goals. The SDK owns public Job controls and operation wrapping.
Service checkpoints are bounded to 64 MiB/1,000,000 five-second
health cycles; rotate explicitly before capacity exhaustion.

## Verification

```bash
python -m pytest tests/test_cctv_realtime_*.py tests/test_mcp_cctv_operator.py -q
python -m pytest tests/test_manifest_contracts.py tests/test_catalog_native_blocks.py -q
node tests/e2e/cctv-workspace.cjs /tmp/cctv-workspace-review
git diff --check
```

The offline browser gate uses the sibling desktop checkout's declared Playwright
dependency (or `OTTERDESK_APP_ROOT`). It checks one through four camera sources,
summary counts, preview selection without restarting streams, filtering,
pagination, image expansion, text escaping, scroll anchoring, empty/error states,
goal disclosure, timeline-only scrolling and resizing between narrow and wide
layouts in light and dark appearances.

To repeat the native index and retrieval gate, set `CCTV_TEST_MEMBRANE_BINARY`
to a built Membrane engine and run `tests/test_cctv_realtime_history.py` with
the operator's encoder dependencies installed. The test starts an isolated
temporary corpus. It uses real model weights and synthetic clothing images.

The opt-in Spark gate exercises the same compiled SDK hooks with an explicitly
supplied camera, real captions, preview, goal changes, saved reports, browser
resizing and resource cleanup. See [VALIDATION.md](VALIDATION.md) for results,
[SPEC.md](SPEC.md) for the contract, and
[NVIDIA's guide](https://docs.nvidia.com/vss/system-components/vision-microservices/real-time-vlm)
for the upstream service.
