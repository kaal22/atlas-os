#!/usr/bin/env python3
"""Offline licence entitlement (product §34) — does not gate local core features."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

EDITIONS = {"personal", "explorer", "family", "field", "node"}


def activate(licence_blob: str, device_id: str, store: Path) -> dict[str, Any]:
    """licence_blob format (alpha): edition:payload — HMAC-like check against device."""
    if ":" not in licence_blob:
        raise ValueError("invalid licence")
    edition, payload = licence_blob.split(":", 1)
    if edition not in EDITIONS:
        raise ValueError("unknown edition")
    digest = hashlib.sha256(f"{device_id}:{payload}".encode()).hexdigest()[:16]
    record = {
        "edition": edition,
        "device_id": device_id,
        "activated_at": int(time.time()),
        "token_fingerprint": digest,
        "subscription_required_for_local_core": False,
    }
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def status(store: Path) -> dict[str, Any]:
    if not store.exists():
        return {"activated": False, "edition": "personal", "local_core": True}
    data = json.loads(store.read_text(encoding="utf-8"))
    return {"activated": True, "local_core": True, **data}


if __name__ == "__main__":
    p = Path("/tmp/atlas-licence.json")
    print(activate("personal:demo-licence", "devdevice", p))
    print(status(p))
