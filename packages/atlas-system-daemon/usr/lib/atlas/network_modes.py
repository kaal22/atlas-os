#!/usr/bin/env python3
"""Atlas network mode controller — ufw helpers (product §23)."""
from __future__ import annotations

import subprocess
from typing import Literal

Mode = Literal["private_device", "trusted_lan", "private_hotspot", "offline_isolation"]


def apply_mode(mode: Mode, dry_run: bool = True) -> list[str]:
    commands: list[str] = []
    if mode == "private_device":
        commands = [
            "ufw --force reset",
            "ufw default deny incoming",
            "ufw default allow outgoing",
            "ufw allow in on lo",
            "ufw --force enable",
        ]
    elif mode == "trusted_lan":
        commands = [
            "ufw default deny incoming",
            "ufw default allow outgoing",
            "ufw allow in on lo",
            "ufw allow from 10.0.0.0/8 to any port 8787 proto tcp",
            "ufw allow from 192.168.0.0/16 to any port 8787 proto tcp",
            "ufw allow from 172.16.0.0/12 to any port 8787 proto tcp",
            "ufw --force enable",
        ]
    elif mode == "private_hotspot":
        commands = [
            "ufw default deny incoming",
            "ufw allow in on lo",
            "ufw allow in on atlas0 to any port 8787 proto tcp",
            "ufw --force enable",
        ]
    elif mode == "offline_isolation":
        commands = [
            "ufw --force reset",
            "ufw default deny incoming",
            "ufw default deny outgoing",
            "ufw allow in on lo",
            "ufw allow out on lo",
            "ufw --force enable",
        ]
    else:
        raise ValueError(mode)

    if dry_run:
        return commands
    for cmd in commands:
        subprocess.check_call(cmd.split())
    return commands


if __name__ == "__main__":
    for m in ("private_device", "trusted_lan", "private_hotspot", "offline_isolation"):
        print(m, apply_mode(m))  # type: ignore[arg-type]
