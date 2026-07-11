#!/usr/bin/env python3
"""Atlas Model Router — profiles, hardware probe, Ollama OpenAI-compatible facade helper."""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any

PROFILES = {
    "tiny": {"min_ram_gb": 4, "min_vram_gb": 0, "model": "qwen3:4b"},
    "light": {"min_ram_gb": 8, "min_vram_gb": 0, "model": "qwen3:4b"},
    "balanced": {"min_ram_gb": 16, "min_vram_gb": 0, "model": "qwen3:4b"},
    "advanced": {"min_ram_gb": 24, "min_vram_gb": 6, "model": "qwen3:4b"},
    "code": {"min_ram_gb": 16, "min_vram_gb": 8, "model": "qwen3:4b"},
    "vision": {"min_ram_gb": 24, "min_vram_gb": 8, "model": "qwen3:4b"},
}


@dataclass
class Hardware:
    ram_gb: float
    vram_gb: float = 0.0
    gpu: str = "none"


def probe_hardware() -> Hardware:
    ram_gb = 8.0
    try:
        mem = open("/proc/meminfo", encoding="utf-8").read()
        for line in mem.splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                ram_gb = round(kb / 1024 / 1024, 1)
                break
    except OSError:
        pass
    return Hardware(ram_gb=ram_gb)


def recommend(hw: Hardware) -> str:
    best = "tiny"
    for name in ["tiny", "light", "balanced", "advanced", "code", "vision"]:
        req = PROFILES[name]
        if hw.ram_gb >= req["min_ram_gb"] and hw.vram_gb >= req["min_vram_gb"]:
            best = name
    return best


def is_compatible(profile: str, hw: Hardware) -> bool:
    req = PROFILES[profile]
    return hw.ram_gb >= req["min_ram_gb"] and hw.vram_gb >= req["min_vram_gb"]


def ollama_tags(host: str = "http://127.0.0.1:11434") -> list[str]:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def chat_completion_url(host: str = "http://127.0.0.1:11434") -> str:
    return host.rstrip("/") + "/v1/chat/completions"


if __name__ == "__main__":
    hw = probe_hardware()
    print({"hardware": hw, "recommend": recommend(hw), "tags": ollama_tags()})
