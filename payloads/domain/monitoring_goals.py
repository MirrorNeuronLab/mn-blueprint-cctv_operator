"""Validate the shared set of visible conditions."""

MAX_GOALS = 5
MAX_INSTRUCTION_LENGTH = 4000
DEFAULT_PROMPT = (
    "Describe the visible scene and actions in 1–2 concise sentences. "
    "Focus on people, vehicles, movement, and changes. "
    "Only describe what is clearly visible; say when something is uncertain."
)


def validate_goals(values):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_GOALS:
        raise ValueError("Enter up to five monitoring goals, one per line.")
    if any(not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\x00")
           for value in values):
        raise ValueError("Enter one nonempty condition per monitoring goal.")
    goals = tuple(value.strip() for value in values)
    if len("\n".join(goals)) > MAX_INSTRUCTION_LENGTH:
        raise ValueError("Monitoring goals must fit within 4,000 characters in total.")
    if len(set(goals)) != len(goals):
        raise ValueError("Enter a different condition for each monitoring goal.")
    return goals


def monitoring_goals(instruction):
    if not isinstance(instruction, str) or "\x00" in instruction:
        raise ValueError("Enter monitoring goals as text.")
    if instruction.strip() == DEFAULT_PROMPT:
        return ()
    return validate_goals([line.strip() for line in instruction.split("\n") if line.strip()])


def configured_goals(config):
    instruction = config.get("inputs", {}).get("payload", {}).get("monitoring_goal")
    return monitoring_goals("" if instruction is None else instruction)
