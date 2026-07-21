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
        print(json.dumps({"ok": False, "error": "usage: atlas-apply-update.py BUNDLE"}))
        return 2
    bundle = Path(sys.argv[1])
    if not bundle.is_file():
        print(json.dumps({"ok": False, "error": "bundle_not_found"}))
        return 1
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    data = Path("/srv/atlas")
    try:
        result = apply_update(bundle, atlas_data=data, dry_run=False)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    body = result.to_dict()
    if not result.ok:
        body["error"] = result.detail
    print(json.dumps(body))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
