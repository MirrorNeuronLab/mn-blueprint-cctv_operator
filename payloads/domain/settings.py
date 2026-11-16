"""Validated camera and NVIDIA streaming settings; credentials stay private."""

from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .camera_sources import MAX_CAMERAS, camera_address, camera_sources, source_identity

DEFAULT_PROMPT = (
    "Describe the visible scene and actions in 1–2 concise sentences. "
    "Focus on people, vehicles, movement, and changes. "
    "Only describe what is clearly visible; say when something is uncertain."
)


class CameraSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    slot: int = Field(default=1, ge=1, le=MAX_CAMERAS)
    uri: str = Field(min_length=8, max_length=2048, repr=False, exclude=True)
    name: str = Field(default="Camera", min_length=1, max_length=120)
    prompt: str = Field(default=DEFAULT_PROMPT, min_length=1, max_length=4000)
    chunk_duration: int = Field(default=4, ge=2, le=30)
    frames_per_chunk: int = Field(default=8, ge=2, le=16)
    max_tokens: int = Field(default=192, ge=64, le=512)
    caption_timeout_seconds: int = Field(default=120, ge=30, le=600)

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, value):
        return camera_address(value)

    @field_validator("prompt", "name")
    @classmethod
    def visible_text(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Enter nonempty text without null characters.")
        return value.strip()

    @property
    def source_id(self):
        return source_identity(self.uri)


def camera_settings(config):
    sources = camera_sources(config)
    analysis = config.get("analysis") or {}
    try:
        prompt = config.get("inputs", {}).get("payload", {}).get("monitoring_goal") or DEFAULT_PROMPT
        return tuple(CameraSettings(slot=slot, uri=uri, name=name, prompt=prompt, **analysis)
                     for slot, uri, name in sources)
    except (TypeError, ValueError):
        # Pydantic errors contain their input. Never propagate a camera credential.
        raise ValueError("Couldn't configure camera analysis. Check the monitoring goal and analysis settings.") from None


def service_url(value):
    try:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or parts.path not in {"", "/"}
                or any(ord(char) < 33 for char in value)):
            raise ValueError()
        parts.port
        return value.rstrip("/")
    except (TypeError, ValueError):
        raise ValueError("Configure an HTTP(S) NVIDIA VLM origin without credentials or a path.") from None
