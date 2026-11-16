"""RTSP source validation shared by setup and the operator."""

import hashlib
from urllib.parse import urlsplit, urlunsplit

MAX_CAMERAS = 4


def camera_address(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Enter a valid RTSP or RTSPS URL.")
    value = value.strip()
    try:
        parts = urlsplit(value)
        if (not 8 <= len(value) <= 2048 or parts.scheme not in {"rtsp", "rtsps"}
                or not parts.hostname or parts.fragment or any(c.isspace() for c in parts.netloc)):
            raise ValueError()
        parts.port
    except ValueError:
        raise ValueError("Enter a valid RTSP or RTSPS URL.") from None
    return value


def source_identity(uri):
    parts = urlsplit(uri)
    # A query can select a different camera. Keep the locator private and
    # preserve identity when credentials in userinfo change.
    locator = urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, parts.query, ""))
    return hashlib.sha256(locator.encode()).hexdigest()


def camera_sources(config):
    source = config.get("video_source", {})
    if not isinstance(source, dict):
        raise ValueError("Review the camera settings.")
    count = source.get("count", 1)
    if type(count) is not int or not 1 <= count <= MAX_CAMERAS:
        raise ValueError("Choose between 1 and 4 cameras.")
    sources, seen = [], set()
    for slot in range(1, count + 1):
        entry = source if slot == 1 else source.get(f"camera_{slot}", {})
        if not isinstance(entry, dict):
            raise ValueError(f"Review the settings for camera {slot}.")
        try:
            uri = camera_address(entry.get("uri", ""))
        except ValueError:
            raise ValueError(f"Enter an approved RTSP or RTSPS URL for camera {slot}.") from None
        name = entry.get("name", "Camera" if slot == 1 and count == 1 else f"Camera {slot}")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or "\x00" in name:
            raise ValueError(f"Enter a valid name for camera {slot}.")
        identity = source_identity(uri)
        if identity in seen:
            raise ValueError(f"Camera {slot} needs a different stream URL.")
        seen.add(identity)
        sources.append((slot, uri, name.strip()))
    return sources
