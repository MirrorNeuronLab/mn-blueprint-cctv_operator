#!/usr/bin/env python3
"""Validate configuration without contacting a camera or printing its address."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from domain.camera_sources import camera_sources


def main():
    try:
        config = json.loads(os.environ.get('MN_BLUEPRINT_CONFIG_JSON', '{}'))
    except ValueError:
        config = None
    try:
        if not isinstance(config, dict):
            raise ValueError("Review the camera settings.")
        camera_sources(config)
    except ValueError as error:
        print(json.dumps({"ok": False, "issues": [{"code": "camera_configuration", "message": str(error)}]}))
        return 1
    print(json.dumps({"ok": True, "issues": [], "message": "Camera configuration is valid. The NVIDIA computer checks the connections at startup."}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
