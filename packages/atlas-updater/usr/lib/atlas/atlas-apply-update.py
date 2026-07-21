#!/usr/bin/env python3
"""Apply an Atlas update bundle outside the Command Centre sandbox."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from updater import apply_update  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        body = {"ok": False, "error": "usage: atlas-apply-update.py BUNDLE"}
        _write_result(body)
        return 2
    bundle = Path(sys.argv[1])
    if not bundle.is_file():
        body = {"ok": False, "error": "bundle_not_found"}
        _write_result(body)
        return 1
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    data = Path("/srv/atlas")
    try:
        result = apply_update(bundle, atlas_data=data, dry_run=False)
    except Exception as e:
        body = {"ok": False, "error": str(e)}
        _write_result(body)
        return 1
    body = result.to_dict()
    if not result.ok:
        body["error"] = result.detail
    _write_result(body)
    print(json.dumps(body))
    return 0 if result.ok else 1


def _write_result(body: dict) -> None:
    out = Path("/srv/atlas/updates/staging/.apply-result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
