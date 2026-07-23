#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "containers" / "compose" / "atlas-core.yml"


def test_compose_exists_and_pins_services():
    assert COMPOSE.exists(), "atlas-core.yml missing"
    text = COMPOSE.read_text(encoding="utf-8")
    for svc in ("mysql", "redis", "qdrant", "kiwix", "kolibri"):
        assert svc in text
    assert "127.0.0.1:8080" in text  # Kiwix Serve (Library)
    assert "127.0.0.1:8083" in text  # Kolibri (Education)
    assert "latest" not in text.replace("sidecar", "")  # soft check; lock handles digests
    assert "127.0.0.1" in text or "localhost" in text


if __name__ == "__main__":
    test_compose_exists_and_pins_services()
    print("OK test_compose_schema")
