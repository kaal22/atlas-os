#!/usr/bin/env python3
"""Model catalogue picks CPU-safe beginner options and blocks GPU-only wrongly."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-model-manager" / "usr" / "lib" / "atlas"))

from model_router import Hardware  # noqa: E402
from model_catalog import (  # noqa: E402
    ALLOWED_TAGS,
    catalogue_for_hardware,
    pick_recommended,
    start_pull,
)


def test_cpu_vm_recommends_beginner():
    hw = Hardware(ram_gb=8.0, vram_gb=0.0, gpu="none")
    cat = catalogue_for_hardware(hw, installed=[])
    rec = pick_recommended(cat, "light")
    assert rec is not None
    assert rec["cpu_ok"] is True
    assert rec["compatible"] is True
    assert rec["tag"] in ALLOWED_TAGS
    # Advanced GPU entry not compatible
    adv = next(c for c in cat if c["id"] == "gpu-advanced")
    assert adv["compatible"] is False
    assert adv["blockers"]


def test_low_ram_gets_starter():
    hw = Hardware(ram_gb=4.0, vram_gb=0.0, gpu="none")
    cat = catalogue_for_hardware(hw, installed=[])
    rec = pick_recommended(cat, "tiny")
    assert rec["tag"] == "qwen2.5:1.5b"


def test_pull_rejects_unknown_tag():
    try:
        start_pull("evil/model:latest")
        assert False, "should reject"
    except ValueError as e:
        assert "catalogue" in str(e)


def test_installed_marks_ready_tag():
    hw = Hardware(ram_gb=16.0, vram_gb=0.0, gpu="none")
    cat = catalogue_for_hardware(hw, installed=["qwen3:4b"])
    rec = pick_recommended(cat, "balanced")
    assert rec["tag"] == "qwen3:4b"
    assert next(c for c in cat if c["tag"] == "qwen3:4b")["installed"] is True


if __name__ == "__main__":
    test_cpu_vm_recommends_beginner()
    test_low_ram_gets_starter()
    test_pull_rejects_unknown_tag()
    test_installed_marks_ready_tag()
    print("OK test_model_catalog")
