#!/usr/bin/env python3
"""Atlas Model Router — profiles, hardware probe, Ollama OpenAI-compatible facade helper."""
from __future__ import annotations

import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from gpu_detect import probe_gpu
except ImportError:
    probe_gpu = None  # type: ignore

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
    nvidia_driver_ok: bool = False
    gpu_warning: str | None = None


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

    gpu = "none"
    vram_gb = 0.0
    nvidia_ok = False
    warning = None
    if probe_gpu is not None:
        report = probe_gpu()
        gpu = report.gpu_name
        vram_gb = report.vram_gb
        nvidia_ok = report.nvidia_driver_ok
        if report.severity in {"warn", "critical"}:
            warning = report.message
            # Don't advertise VRAM for profile gating if drivers are missing
            if report.has_nvidia_pci and not report.nvidia_driver_ok:
                vram_gb = 0.0

    return Hardware(
        ram_gb=ram_gb,
        vram_gb=vram_gb,
        gpu=gpu,
        nvidia_driver_ok=nvidia_ok,
        gpu_warning=warning,
    )


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


def recommendation_bundle() -> dict[str, Any]:
    hw = probe_hardware()
    profile = recommend(hw)
    out: dict[str, Any] = {
        "ram_gb": hw.ram_gb,
        "vram_gb": hw.vram_gb,
        "gpu": hw.gpu,
        "nvidia_driver_ok": hw.nvidia_driver_ok,
        "profile": profile,
        "profile_reason": (
            "CPU-safe profile because GPU drivers are missing or VRAM is unavailable"
            if hw.gpu_warning and hw.vram_gb <= 0
            else "Best profile matching RAM and VRAM"
        ),
    }
    if hw.gpu_warning:
        out["warning"] = hw.gpu_warning
        out["setup_command"] = "atlas-gpu-setup --guide"
        out["install_command"] = "sudo atlas-gpu-setup --install-nvidia"
    if probe_gpu is not None:
        out["gpu_report"] = __import__("gpu_detect").as_api_dict()
    return out


def ollama_tags(host: str = "http://127.0.0.1:11434") -> list[str]:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def chat_completion_url(host: str = "http://127.0.0.1:11434") -> str:
    return host.rstrip("/") + "/v1/chat/completions"


def model_for_profile(profile: str | None = None) -> str:
    """Resolve Ollama model tag for a profile. No-GPU VMs use tiny/light (vram=0)."""
    if profile is None:
        profile = recommend(probe_hardware())
    # Prefer CPU-safe profiles when VRAM is unavailable
    hw = probe_hardware()
    if profile in PROFILES and not is_compatible(profile, hw):
        profile = recommend(hw)
    return PROFILES.get(profile, PROFILES["tiny"])["model"]


def chat(
    messages: list[dict[str, str]],
    profile: str | None = None,
    host: str = "http://127.0.0.1:11434",
    timeout: float = 120.0,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Call Ollama OpenAI-compatible chat completions.
    Returns {"content": str, "model": str, "profile": str} or raises RuntimeError.
    """
    resolved_profile = profile or recommend(probe_hardware())
    tag = model or model_for_profile(resolved_profile)
    url = chat_completion_url(host)
    body = json.dumps(
        {
            "model": tag,
            "messages": messages,
            "stream": False,
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"ollama_chat_failed: {e}") from e

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("ollama_chat_failed: empty choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    return {
        "content": content.strip(),
        "model": data.get("model", tag),
        "profile": resolved_profile,
        "raw": data,
    }


if __name__ == "__main__":
    print(json.dumps(recommendation_bundle(), indent=2))
