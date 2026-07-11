#!/usr/bin/env python3
"""Collect redacted diagnostic bundle metadata."""
from __future__ import annotations

import json
import time
from pathlib import Path


REDACT = ("password", "token", "secret", "authorization", "api_key")


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if any(r in k.lower() for r in REDACT) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def create_bundle(atlas_root: Path, out: Path) -> Path:
    payload = {
        "created": int(time.time()),
        "os_release": (Path("/etc/atlas/os-release").read_text() if Path("/etc/atlas/os-release").exists() else "dev"),
        "health": {"command_centre": True},
        "sample_config": redact({"ATLAS_MODE": "appliance", "db_password": "should-hide"}),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    p = create_bundle(Path("/srv/atlas"), Path("/tmp/atlas-diag.json"))
    print(p.read_text())
