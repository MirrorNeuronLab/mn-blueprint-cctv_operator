"""One camera's NVIDIA caption request and durable window evidence."""

import asyncio
import hashlib
import json
import math
import uuid

import httpx

from .caption_store import now, timestamp
from .errors import CameraStateError
from .realtime_client import safe_error, sse_data
from .settings import DEFAULT_PROMPT
from .window_evidence import assessment, box_coordinates


def request_key(slot):
    # Retain the original key so a 6.1 lease still requires reconciliation.
    return "active_request" if slot == 1 else f"active_request:{slot}"


async def reconcile_request(client, store, key):
    lease = store.state(key)
    if not lease:
        return
    if not lease.get("stream_id"):
        raise CameraStateError("A previous camera registration has an unknown outcome. Reconcile it in NVIDIA before starting again.")
    if lease.get("origin") != client.base_url:
        raise CameraStateError("An outstanding camera request belongs to another NVIDIA service. Reconcile it before changing the endpoint.")
    await client.cleanup(lease["stream_id"], lease.get("request_id"))
    store.set_state(key, None)


class Analysis:
    def __init__(self, client, settings, store, publish, save_status, preview=None):
        self.client, self.settings, self.store = client, settings, store
        self.publish, self.save_status = publish, save_status
        self.preview = preview
        self.lease_key = request_key(settings.slot)
        # Reuse this ID after a timeout, so even a late registration cannot
        # create a second NVIDIA asset for the same Job and camera slot.
        self.stream_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"otterdesk:cctv:{store.job_id}:{settings.slot}"))
        self.task = None
        self.seen = set()
        self.revision = 0
        self.releasing = False
        self.state = {"status": "ready", "total_captions": 0, "error": None,
                      "camera": settings.name, "slot": settings.slot,
                      "source_id": store.source_id, "instruction": settings.prompt, "instruction_revision": 0}

    def update(self, **values):
        self.state.update(values)
        self.save_status(dict(self.state))

    async def start(self, model=None, *, instruction=None, revision=0):
        if self.task and not self.task.done():
            raise ValueError("Camera analysis is already running.")
        await reconcile_request(self.client, self.store, self.lease_key)
        model = model if model is not None else await self.client.model()
        if instruction is not None:
            self.settings = self.settings.model_copy(update={"prompt": instruction})
        self.revision = revision
        self.seen.clear()
        self.session_id = uuid.uuid4().hex
        self.update(status="starting", model=model, started_at=now(), error=None,
                    instruction=self.settings.prompt, instruction_revision=self.revision,
                    last_caption_at=None, inference_ms=None,
                    total_captions=self.store.history(current_run=True)["total_count"])
        for caption in self.store.pending():
            self.publish(caption)
            self.store.published(caption["id"])
        self.task = asyncio.create_task(self._run(model))

    async def stop(self):
        if self.task and not self.task.done():
            if not self.releasing:
                self.update(status="stopping")
                self.task.cancel()
            try:
                await asyncio.shield(self.task)
            except asyncio.CancelledError:
                if not self.task.cancelled():
                    raise
                # A stop before _run's first instruction cannot own a stream.
                self.update(status="stopped", stopped_at=now())
        if self.store.state(self.lease_key):
            raise CameraStateError("The NVIDIA camera request was not fully released. Check analysis status before retrying.")

    async def _run(self, model):
        stream_id = self.stream_id
        try:
            # Commit the requested identity before sending anything to NVIDIA.
            self.store.set_state(self.lease_key, {"stream_id": stream_id, "request_id": None,
                                                  "origin": self.client.base_url})
            registration = asyncio.create_task(self.client.add_stream(self.settings, stream_id))
            try:
                await asyncio.shield(registration)
            except asyncio.CancelledError:
                # Let the in-flight registration settle before deleting it.
                await registration
                raise
            payload = self.client.caption_payload(stream_id, model, self.settings)
            async with self.client.http.stream(
                "POST", "v1/generate_captions", json=payload,
                timeout=httpx.Timeout(15, read=self.settings.caption_timeout_seconds),
            ) as response:
                response.raise_for_status()
                self._request_id(stream_id, response.headers.get("x-request-id"))
                self.update(status="running")
                records = sse_data(response.aiter_lines())
                while True:
                    try:
                        data = await asyncio.wait_for(anext(records), self.settings.caption_timeout_seconds)
                    except StopAsyncIteration:
                        raise ValueError("The live caption stream ended unexpectedly.") from None
                    if data.strip() == "[DONE]":
                        raise ValueError("The live caption stream ended unexpectedly.")
                    result = json.loads(data)
                    if not isinstance(result, dict) or result.get("error"):
                        raise ValueError("NVIDIA reported an inference error.")
                    if result.get("request_id"):
                        self._request_id(stream_id, result["request_id"])
                    chunks = result.get("chunk_responses", [])
                    if not isinstance(chunks, list) or len(chunks) > 64:
                        raise ValueError("Unexpected NVIDIA caption response.")
                    for chunk in chunks:
                        await self.caption(chunk)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.update(status="error", error=safe_error(error))
        finally:
            self.releasing = True
            try:
                try:
                    await reconcile_request(self.client, self.store, self.lease_key)
                except Exception:
                    message = "Couldn't release the NVIDIA camera request. Check the VLM service before starting again."
                    if self.state["error"]:
                        message = self.state["error"] + " NVIDIA camera cleanup is pending."
                    self.update(status="error", error=message)
                self.update(status="error" if self.state["status"] == "error" else "stopped", stopped_at=now())
            finally:
                self.releasing = False

    def _request_id(self, stream_id, request_id):
        if request_id is not None and (not isinstance(request_id, str) or not request_id or len(request_id) > 256):
            raise ValueError("Invalid NVIDIA request identity.")
        lease = self.store.state(self.lease_key) or {}
        self.store.set_state(self.lease_key, {"stream_id": stream_id, "request_id": request_id or lease.get("request_id"),
                                                "origin": self.client.base_url})

    async def caption(self, chunk):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("content"), str):
            raise ValueError("Unexpected NVIDIA caption content.")
        content = chunk["content"].strip()
        if not content:
            return
        if len(content) > 8192 or "<think>" in content.lower() or chunk.get("finish_reason") not in {None, "stop"}:
            raise ValueError("Incomplete or private NVIDIA caption content.")
        start, end = timestamp(chunk.get("start_time")), timestamp(chunk.get("end_time"))
        if start > end:
            raise ValueError("Caption times are out of order.")
        key = hashlib.sha256(json.dumps([chunk.get("chunk_id"), start, end], sort_keys=True).encode()).hexdigest()
        if key in self.seen:
            return
        latencies = {}
        for field in ("vlm_latency_ms", "chunk_latency_ms"):
            value = chunk.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError("Invalid NVIDIA timing.")
            latencies[field] = value
        verdict, content, _ = assessment(content)
        caption = {"id": self.session_id + ":" + key, "run_id": self.store.run_id,
                   "camera": self.settings.name, "camera_slot": self.settings.slot, "source_id": self.store.source_id,
                   "content": content, "summary": content, "scene_understanding": content,
                   "start_time": start, "end_time": end, "received_at": now(),
                   "instruction": self.settings.prompt, "instruction_revision": self.revision,
                   "goal_match": verdict if self.settings.prompt != DEFAULT_PROMPT else "no_target",
                   "model": self.state["model"], "evidence_kind": "nvidia_video_window_caption",
                   "source_refs": ["captions/" + self.session_id + "-" + key + ".json"],
                   **latencies}
        interrupted = False
        saved = self.store.saved(caption["id"])
        if saved:
            if any(caption[k] != saved.get(k) for k in ("content", "start_time", "end_time", "instruction_revision", "model")):
                raise ValueError("A caption identity was reused with different content.")
            caption = saved
        else:
            jpeg = None
            frame = self.preview.window_frame(start, end) if self.preview else None
            if frame:
                received, jpeg = frame
                reference = f"snapshots/{self.session_id}-{key}.jpg"
                snapshot = {"received_at": received, "sha256": hashlib.sha256(jpeg).hexdigest(), "source_ref": reference}
                caption["source_refs"].append(reference)
                if caption["goal_match"] == "matched":
                    # Only a localization of these exact JPEG bytes may be drawn on them.
                    try:
                        async with asyncio.timeout(min(2, self.settings.chunk_duration / 2)):
                            decision, _, box = await self.client.review(caption["model"], self.settings.prompt, jpeg=jpeg)
                        if decision == "matched" and (coords := box_coordinates(box)):
                            snapshot["bbox_2d"] = coords
                    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                        pass  # A completed window and its original snapshot still stand on their own.
                    except asyncio.CancelledError:
                        interrupted = True
                caption["snapshot"] = snapshot
            self.store.append(caption, jpeg)
        # Publication follows the durable source, never acceptance of an SSE packet.
        self.publish(caption)
        self.store.published(caption["id"])
        self.seen.add(key)
        if len(self.seen) > 600:
            self.seen = {key}
        self.update(total_captions=self.store.history(current_run=True)["total_count"],
                    last_caption_at=caption["received_at"], inference_ms=caption["vlm_latency_ms"])
        if interrupted:
            raise asyncio.CancelledError()
