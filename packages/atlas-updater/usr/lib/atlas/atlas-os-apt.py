#!/usr/bin/env python3
"""Privileged helper for Atlas APT / OS package updates.

Invoked via systemd-run from Command Centre (ProtectSystem=false), same pattern
as atlas-apply-update.py. Does not expose a network listener.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from os_updater import (  # noqa: E402
    OsUpdateError,
    apply_os_updates,
    check_os_updates,
    enable_local_source,
    os_update_status,
)


RESULT = Path("/srv/atlas/updates/staging/.os-apply-result.json")


def _write(body: dict) -> None:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(body), encoding="utf-8")
    print(json.dumps(body))


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        body = {
            "ok": False,
            "error": "usage: atlas-os-apt.py status|check|apply|enable-source [args]",
        }
        _write(body)
        return 2

    cmd = argv[0]
    try:
        if cmd == "status":
            body = os_update_status().to_dict()
            _write(body)
            return 0 if body.get("ok", True) else 1
        if cmd == "check":
            body = check_os_updates(atlas_only=True, refresh=True)
            _write(body)
            return 0 if body.get("ok") else 1
        if cmd == "apply":
            full = "--full" in argv
            confirmed = "--owner-confirmed" in argv
            dry = "--dry-run" in argv
            body = apply_os_updates(
                atlas_only=not full,
                full_system=full,
                owner_confirmed=confirmed,
                dry_run=dry,
            )
            _write(body)
            return 0 if body.get("ok") else 1
        if cmd == "enable-source":
            if len(argv) < 2:
                body = {"ok": False, "error": "usage: enable-source REPO_PATH"}
                _write(body)
                return 2
            body = enable_local_source(Path(argv[1]), write_sources=True)
            _write(body)
            return 0
        body = {"ok": False, "error": f"unknown_command:{cmd}"}
        _write(body)
        return 2
    except OsUpdateError as e:
        body = {"ok": False, "error": str(e)}
        _write(body)
        return 1
    except Exception as e:
        body = {"ok": False, "error": str(e)}
        _write(body)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
