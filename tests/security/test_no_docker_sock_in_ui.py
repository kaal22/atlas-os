#!/usr/bin/env python3
"""Ensure UI/compose defs do not mount docker.sock into browser-facing services."""
from pathlib import Path

ROOT = Path(__file__).resolve().hosts if False else Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "containers" / "compose"


def iter_compose_text():
    if not COMPOSE.exists():
        return
    for p in COMPOSE.rglob("*.yml"):
        yield p, p.read_text(encoding="utf-8")
    for p in COMPOSE.rglob("*.yaml"):
        yield p, p.read_text(encoding="utf-8")


FORBIDDEN_SERVICES = {"command-centre", "atlas-command-centre", "ui", "portal"}


def test_no_socket_on_ui_services():
    for path, text in iter_compose_text():
        lower = text.lower()
        if "docker.sock" not in lower and "/var/run/docker.sock" not in text:
            continue
        # If socket appears, ensure it is not under a UI service block naively
        for svc in FORBIDDEN_SERVICES:
            # crude: if service name and docker.sock within 40 lines of each other
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if svc in line.lower() and line.strip().endswith(":"):
                    window = "\n".join(lines[i : i + 40])
                    assert "docker.sock" not in window, f"{path} mounts docker.sock on {svc}"


if __name__ == "__main__":
    test_no_socket_on_ui_services()
    print("OK test_no_docker_sock_in_ui")
