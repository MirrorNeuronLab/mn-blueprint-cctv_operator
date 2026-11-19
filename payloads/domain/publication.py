"""Durable NVIDIA window accounts and restrained completed Chat activity."""

from pathlib import Path

from mn_sdk_common.files import atomic_write_bytes, atomic_write_json, atomic_write_text

from .monitoring_goals import DEFAULT_PROMPT
from .window_evidence import chat_frame


class Publisher:
    def __init__(self, run_dir, store, exchange):
        self.run_dir, self.store, self.exchange = Path(run_dir), store, exchange

    def caption(self, caption):
        reference = caption["source_refs"][0]
        snapshot = caption.get("snapshot")
        jpeg = self.store.frame(caption["id"]) if snapshot else None
        # Published outputs must be readable by the host's synchronization user.
        # Credentials and cleanup leases remain in private Job state.
        if snapshot:
            atomic_write_bytes(self.run_dir / snapshot["source_ref"], jpeg, create_parents=True, mode=0o644)
        atomic_write_json(self.run_dir / reference, caption, mode=0o644)
        snapshot_note = (f"Window snapshot: {snapshot['source_ref']} (preview received {snapshot['received_at']}).\n\n"
                         if snapshot else "")
        markdown = (
            f"# {caption['camera']} — video observation\n\n"
            f"Capture interval: {caption['start_time']} to {caption['end_time']}\n\n"
            f"Analysis received: {caption['received_at']}\n\n"
            f"Monitoring instructions: {caption['instruction']}\n\n"
            f"{caption['content']}\n\n"
            f"{snapshot_note}"
            f"Source: {reference}\n\n"
            "This is a model description of a sampled video window. It can miss or misdescribe activity. "
            "It does not establish identity, unique-person counts, compliance or safety. "
            "The separate preview is current video, not the exact analyzed evidence.\n"
        )
        atomic_write_text(self.run_dir / "context_sources/outputs" / (Path(reference).stem + ".md"), markdown,
                          mode=0o644, create_parents=True)
        self.report()
        self.publish_activity(caption, jpeg)

    def publish_activity(self, caption, jpeg):
        # The legacy first observation marker also keeps interpretation of the
        # original one-camera run on replay. Each additional feed owns its own.
        marker = f"activity:{self.store.run_id}:{caption['instruction_revision']}"
        if caption.get("camera_slot", 1) > 1:
            marker += ":" + caption["source_id"]
        previous = self.store.state(marker)
        assessments = caption.get("goal_assessments")
        if assessments is None:
            assessments = ([{"goal": caption["instruction"], "verdict": caption.get("goal_match")}]
                           if caption["instruction"] != DEFAULT_PROMPT else [])
        active = set((previous or {}).get("active", [])) if isinstance(previous, dict) else set()
        if isinstance(previous, dict) and previous.get("matched") and len(assessments) == 1:
            active.add(0)
        new_matches = []
        for index, item in enumerate(assessments):
            if item["verdict"] == "matched":
                if index not in active:
                    new_matches.append(item["goal"])
                active.add(index)
            elif item["verdict"] == "not_matched":
                active.discard(index)
        # One notice per window, with a separate sighting state for each goal.
        if not previous or new_matches:
            snapshot = caption.get("snapshot")
            activity = {"schema_version": "mn.mcp.job_activity.v1", "event_id": caption["id"],
                        "title": "Possible goal match" if new_matches else "Video observation", "message": caption["content"],
                        "occurred_at": caption["end_time"],
                        "source": "cctv_operator.goal_match" if new_matches else "cctv_operator",
                        "requires_review": False,
                        "details": [{"label": "Capture interval", "value": f"{caption['start_time']} to {caption['end_time']}"},
                                    {"label": "Camera", "value": caption["camera"]},
                                    *({"label": "Matched goal", "value": goal} for goal in new_matches)]}
            if len(self.store.source_ids) > 1:
                activity["message"] = f"{caption['camera']} · {caption['content']}"
            if jpeg and (image := chat_frame(caption, jpeg, snapshot.get("bbox_2d"))):
                activity["image"] = image
            self.exchange.publish_result(caption["id"], activity, stage="live_activity",
                                         summary=caption["content"][:2000], publication_state="final",
                                         idempotency_key="caption:" + caption["id"])
        self.store.set_state(marker, {"active": sorted(active)})

    def status(self, state):
        atomic_write_json(self.run_dir / "monitoring_state.json", state, mode=0o644)
        self.report(state)

    def report(self, state=None):
        history = self.store.history(current_run=True)
        observations = history["observations"]
        report = {"schema_version": "otterdesk.cctv.report.v6", "run_id": self.store.run_id,
                  "source_ids": list(self.store.source_ids), "observations": observations,
                  "total_count": history["total_count"], "omitted_count": history["omitted_count"]}
        if self.store.source_id:
            report["source_id"] = self.store.source_id
        if state:
            report["session"] = state
        atomic_write_json(self.run_dir / "cctv_report.json", report, mode=0o644)
        matched = sum(item.get("goal_match") == "matched" for item in observations)
        uncertain = sum(item.get("goal_match") == "uncertain" for item in observations)
        coverage = (f"{len(observations)} of {history['total_count']} completed video windows appear below. "
                    f"{matched} shown windows have a possible goal match and {uncertain} have an uncertain verdict. "
                    "Verdicts apply to the instructions in effect for each window.")
        entries = [f"## {item['camera']} · {item['start_time']} to {item['end_time']}\n\n{item['content']}\n\nSource: {item['source_refs'][0]}"
                   for item in observations]
        atomic_write_text(self.run_dir / "cctv_report.md", "# CCTV observations\n\n"
                    + "## Assessment\n\n" + coverage + "\n\n"
                    + "Check the camera and capture interval of a possible match against the original video. "
                    + "Missing captions leave activity unknown.\n\n## Window evidence\n\n"
                    + ("\n\n".join(entries) if entries else "No completed video observations yet.")
                    + f"\n\nEarlier observations omitted from this report: {history['omitted_count']}.\n", mode=0o644)
        summary = observations[-1]["content"] if observations else "No completed video observations yet."
        atomic_write_json(self.run_dir / "final_artifact.json", {
            "type": "cctv_observations", "executive_summary": summary,
            "recommended_action": "Review the recorded video interval before acting.",
            "confidence": "Uncalibrated model description", "evidence": observations[-1:],
            "next_steps": ["Review the source video and any uncertainty."],
            "source_refs": ["cctv_report.json", "cctv_report.md"],
        }, mode=0o644)
