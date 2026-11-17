"""Interpret explicit model assessments and render only boxes grounded on the saved image."""

import base64
import io
import json
import re

from PIL import Image, ImageDraw

from .monitoring_goals import DEFAULT_PROMPT, monitoring_goals


def window_prompt(instruction):
    goals = monitoring_goals(instruction)
    if not goals:
        return DEFAULT_PROMPT
    guidance = (
        "Describe the visible scene even when a condition is absent. Assess each exact condition independently, "
        "including negation. Use matched only when the requested condition is visible, not_matched for clear "
        "absence, and uncertain for obscured details. To report a missing item, its wearer or location must be visible. "
    )
    if len(goals) == 1:
        return (guidance + 'Return only one JSON object {"verdict":"matched|not_matched|uncertain",'
                '"summary":"one concise sentence"}. Monitoring goal: ' + goals[0])
    numbered = "\n".join(f"{index}. {goal}" for index, goal in enumerate(goals, start=1))
    return (guidance + 'Return only one JSON object with "summary" (one concise sentence) and "verdicts" '
            f'(exactly {len(goals)} verdict strings in the order of the numbered goals). '
            'Use the strings "matched", "not_matched", or "uncertain". Mention visible matches in the summary.\n'
            + numbered)


def assessment_json(content):
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    try:
        result = json.loads(fenced[1] if fenced else text)
    except ValueError:
        return None
    if isinstance(result, dict) and isinstance(result.get("summary"), str) and result["summary"].strip():
        return result
    return None


def visible_verdict(value):
    return value if value in ("matched", "not_matched", "uncertain") else "uncertain"


def observation_text(content):
    # Free prose and legacy bbox snippets are never affirmative verdicts.
    prose = content.split("```", 1)[0].strip()
    return prose if prose and not prose.startswith(("{", "[")) else "The model did not return a readable observation."


def assessment(content):
    result = assessment_json(content)
    if result is not None:
        return visible_verdict(result.get("verdict")), result["summary"].strip(), result.get("bbox_2d")
    return "uncertain", observation_text(content), None


def window_assessment(content, goals):
    result = assessment_json(content)
    summary = result["summary"].strip() if result is not None else observation_text(content)
    if not goals:
        return summary, []
    if len(goals) == 1:
        verdicts = [result.get("verdict")] if result is not None else [None]
    else:
        verdicts = result.get("verdicts") if result is not None else None
        if not isinstance(verdicts, list) or len(verdicts) != len(goals):
            verdicts = [None] * len(goals)
    return summary, [{"goal": goal, "verdict": visible_verdict(verdict)}
                     for goal, verdict in zip(goals, verdicts, strict=True)]


def box_coordinates(value):
    if (isinstance(value, list) and len(value) == 4 and all(type(n) is int for n in value)
            and 0 <= value[0] < value[2] <= 1000 and 0 <= value[1] < value[3] <= 1000
            and value != [0, 0, 1000, 1000]):
        return value
    return None


def display_frame(jpeg, box, *, thumbnail=False):
    if not box and not thumbnail:
        return jpeg
    with Image.open(io.BytesIO(jpeg)) as image:
        if box:
            size = (image.width - 1, image.height - 1) * 2
            ImageDraw.Draw(image).rectangle([round(n * scale / 1000) for n, scale in zip(box, size)],
                                            outline="#ffd34d", width=max(2, image.width // 160))
        if thumbnail:
            image.thumbnail((480, 320))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=72)
        return out.getvalue()


def chat_frame(caption, jpeg, box=None):
    thumbnail = display_frame(jpeg, box, thumbnail=True)
    if len(thumbnail) <= 75 * 1024:
        return {"run_id": caption["run_id"], "mime_type": "image/jpeg",
                "data": base64.b64encode(thumbnail).decode("ascii"), "title": "Window snapshot",
                "alt": f"{caption.get('camera', 'Camera')} preview received during the video window",
                "caption": f"Preview received {caption['snapshot']['received_at']} during this window."
                           + (" Box estimated on this image." if box else "")}
