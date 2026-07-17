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


def test_ready_even_if_over_ram_recommendation():
    """A finished pull must unlock Chat even when RAM is below the catalogue min."""
    from model_catalog import model_setup_status
    import model_catalog as mc

    orig_hw = mc.probe_hardware
    orig_tags = mc.installed_models
    orig_reach = mc.ollama_reachable
    try:
        mc.probe_hardware = lambda: Hardware(ram_gb=4.0, vram_gb=0.0, gpu="none")
        mc.ollama_reachable = lambda host="http://127.0.0.1:11434": True
        mc.installed_models = lambda host="http://127.0.0.1:11434": ["qwen3:4b"]
        st = model_setup_status()
        assert st["ready"] is True
        assert st["ollama_reachable"] is True
    finally:
        mc.probe_hardware = orig_hw
        mc.installed_models = orig_tags
        mc.ollama_reachable = orig_reach


def test_resolve_uses_installed_starter():
    from model_router import resolve_chat_model
    import model_router as mr

    orig = mr.ollama_tags
    try:
        mr.ollama_tags = lambda host="http://127.0.0.1:11434": ["qwen2.5:1.5b"]
        tag, profile = resolve_chat_model(profile="light")
        assert tag == "qwen2.5:1.5b", tag
        assert profile  # still returns a profile
    finally:
        mr.ollama_tags = orig


def test_extract_text_and_empty_openai_falls_back():
    from model_router import _extract_text, chat
    import model_router as mr

    assert _extract_text({"choices": [{"message": {"content": "  hi  "}}]}) == "hi"
    assert _extract_text({"message": {"content": "", "thinking": "reason"}}) == "reason"
    assert _extract_text({"response": "plain"}) == "plain"

    calls: list[str] = []

    def fake_http(url, body, timeout):
        calls.append(url)
        if url.endswith("/v1/chat/completions"):
            return {"choices": [{"message": {"content": ""}}], "model": body["model"]}
        if url.endswith("/api/chat"):
            return {"message": {"content": "Hello from native"}, "model": body["model"]}
        raise AssertionError(url)

    orig_http = mr._http_json
    orig_tags = mr.ollama_tags
    orig_resolve = mr.resolve_chat_model
    try:
        mr._http_json = fake_http
        mr.ollama_tags = lambda host="http://127.0.0.1:11434": ["qwen2.5:1.5b"]
        mr.resolve_chat_model = lambda profile=None, host="http://127.0.0.1:11434", model=None: (
            "qwen2.5:1.5b",
            "tiny",
        )
        out = chat(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Tool results: []"},
            ],
            profile="tiny",
        )
        assert out["content"] == "Hello from native"
        assert any(u.endswith("/v1/chat/completions") for u in calls)
        assert any(u.endswith("/api/chat") for u in calls)
    finally:
        mr._http_json = orig_http
        mr.ollama_tags = orig_tags
        mr.resolve_chat_model = orig_resolve


if __name__ == "__main__":
    test_cpu_vm_recommends_beginner()
    test_low_ram_gets_starter()
    test_pull_rejects_unknown_tag()
    test_installed_marks_ready_tag()
    test_ready_even_if_over_ram_recommendation()
    test_resolve_uses_installed_starter()
    test_extract_text_and_empty_openai_falls_back()
    print("OK test_model_catalog")
