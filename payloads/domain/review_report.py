"""Render an evidence-bounded snapshot of the current run's camera windows."""

from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk_common.files import atomic_write_text


def render(store, phase):
    from mn_web_report_skill import render_report_html

    history = store.history(current_run=True, limit=50)
    windows = history["observations"]
    matched = sum(window.get("goal_match") == "matched" for window in windows)
    uncertain = sum(window.get("goal_match") == "uncertain" for window in windows)
    assessment = (f"Possible goal matches in {matched} of the {len(windows)} displayed windows. "
                  f"Uncertain verdicts in {uncertain}. Check the original video at the recorded time before acting."
                  if windows else "No completed video windows were recorded for this run. Activity is unknown.")
    rows = [[w.get("camera") or "Camera label unavailable", w["start_time"] + " to " + w["end_time"], w.get("content", ""),
             w.get("goal_match") or "No goal verdict", w["source_refs"][0]] for w in reversed(windows)]
    evidence = ({"type": "table", "columns": ["Camera", "Capture interval", "Observation", "Goal verdict", "Saved record"],
                 "rows": rows} if rows else {"type": "paragraph", "text": "There are no saved window records to cite."})
    return render_report_html({"title": "Camera observation report", "identity": "Monitoring status · " + phase,
        "sections": [
            {"id": "assessment", "title": "Assessment", "blocks": [{"type": "paragraph", "text": assessment}]},
            {"id": "evidence", "title": "Window evidence", "blocks": [evidence]},
            {"id": "coverage", "title": "Coverage", "blocks": [{"type": "paragraph", "text":
                f"This review includes the latest {len(windows)} of {history['total_count']} completed windows in this run. "
                "Each saved record includes the instructions in effect for its capture interval. "
                "A sampled model description can miss or misdescribe activity."}]},
        ]})


def save(block, operator):
    page = render(operator.store, operator.phase)
    for root in dict.fromkeys((block.store.run_dir, block.output_directory)):
        atomic_write_text(CommittedJsonStore(root).path("report.html"), page, mode=0o644)
