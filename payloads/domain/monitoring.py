"""Coordinate camera sessions and the shared monitoring goal for one run."""

import asyncio

from .analysis import reconcile_request, request_key
from .camera_sources import MAX_CAMERAS
from .errors import CameraStateError
from .realtime_client import safe_error
from .settings import DEFAULT_PROMPT


class Monitoring:
    def __init__(self, client, store, cameras, save_status):
        self.client, self.store, self.cameras = client, store, cameras
        self.save_status = save_status
        self.lock = asyncio.Lock()
        self.model = None
        self.closing = False
        self.configured_prompt = cameras[1].settings.prompt
        self.goal_key = "goal:" + store.run_id
        self.goal = store.state(self.goal_key) or {"instruction": self.configured_prompt, "revision": 0}

    @property
    def ready(self):
        return any(camera.state["status"] == "running" for camera in self.cameras.values())

    @property
    def finished(self):
        return all(camera.task and camera.task.done() for camera in self.cameras.values())

    def session(self):
        cameras = [dict(camera.state) for camera in self.cameras.values()]
        states = {camera["status"] for camera in cameras}
        if len(states) == 1:
            status = states.pop()
        elif "running" in states and "error" in states:
            status = "degraded"
        elif "starting" in states or "running" in states or "ready" in states:
            status = "starting"
        elif "stopping" in states:
            status = "stopping"
        else:
            status = "error"
        return {
            **(cameras[0] if len(cameras) == 1 else {}),
            "status": status,
            "error": next((camera["error"] for camera in cameras if camera["error"]), None) if status == "error" else None,
            "model": self.model,
            "instruction": self.goal["instruction"],
            "instruction_revision": self.goal["revision"],
            "total_captions": sum(camera["total_captions"] for camera in cameras),
        }

    def snapshot(self):
        windows = self.store.history(current_run=True)
        matches = self.store.history(current_run=True, goal_revision=self.goal["revision"])
        return {
            "session": self.session(),
            "cameras": [
                {**camera.state, "preview": camera.preview.status()}
                for camera in self.cameras.values()
            ],
            "captions": windows["observations"],
            "goal_matches": matches["observations"],
            "match_count": matches["total_count"],
            "omitted_count": windows["omitted_count"],
            "has_target": self.goal["instruction"] != DEFAULT_PROMPT,
        }

    def publish_status(self):
        self.save_status({**self.session(), "cameras": [dict(camera.state) for camera in self.cameras.values()]})

    async def start(self, model):
        async with self.lock:
            # Removed cameras can still have leases. Reconcile the entire Job
            # before opening any session, even when the camera count decreased.
            results = await asyncio.gather(*(
                reconcile_request(self.client, self.store, request_key(slot))
                for slot in range(1, MAX_CAMERAS + 1)
            ), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            self.model = model
            await self._start_cameras()

    async def _start_cameras(self):
        for camera in self.cameras.values():
            await camera.start(self.model, instruction=self.goal["instruction"], revision=self.goal["revision"])

    async def _stop_cameras(self):
        results = await asyncio.gather(*(camera.stop() for camera in self.cameras.values()), return_exceptions=True)
        for slot, result in zip(self.cameras, results, strict=True):
            if isinstance(result, BaseException):
                raise CameraStateError(f"Couldn't release the NVIDIA request for camera {slot}. Check its analysis status.")

    async def close(self):
        self.closing = True
        async with self.lock:
            await self._stop_cameras()

    async def change_goal(self, identity, instruction, clear=False):
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
            raise ValueError("A request ID of 1–128 characters is required.")
        if not isinstance(instruction, str) or len(instruction) > 4000 or (not clear and not instruction.strip()):
            raise ValueError("Enter a visible condition to monitor.")
        # Closing a caller's connection must not interrupt owned stream cleanup.
        return await asyncio.shield(self._change_goal(identity, instruction, clear))

    async def _change_goal(self, identity, instruction, clear):
        request = {"run_id": self.store.run_id, "instruction": instruction, "clear": clear}
        async with self.lock:
            previous = self.store.command(identity, request)
            if previous:
                return previous
            if self.closing or not self.ready:
                raise CameraStateError("Start camera analysis before changing the monitoring goal.")
            selected = self.configured_prompt if clear else instruction.strip()
            revision = self.goal["revision"] + 1
            receipt = {"state": "accepted", "accepted": True, "command_id": identity,
                       "operation_id": identity, "instruction_revision": revision,
                       "summary": "Monitoring change accepted. Waiting for the previous camera requests to stop."}
            self.store.command(identity, request, receipt)
            try:
                for slot, camera in self.cameras.items():
                    if (camera.task is None or camera.task.done()) and self.store.state(camera.lease_key):
                        raise CameraStateError(f"Camera {slot} has an outstanding NVIDIA request. Check its analysis status.")
                await self._stop_cameras()
                if self.closing:
                    raise CameraStateError("Camera analysis stopped before the monitoring goal changed.")
                self.goal = {"instruction": selected, "revision": revision}
                self.store.set_state(self.goal_key, self.goal)
                await self._start_cameras()
                receipt.update(state="completed", instruction=selected, analysis_ready=False,
                               summary="Monitoring goal applied. Future video windows will use it.")
            except Exception as error:
                receipt.update(state="failed", summary=safe_error(error))
            return self.store.command(identity, request, receipt)
