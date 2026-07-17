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
    "tiny": {"min_ram_gb": 4, "min_vram_gb": 0, "model": "qwen2.5:1.5b"},
    "light": {"min_ram_gb": 8, "min_vram_gb": 0, "model": "qwen3:4b"},
    "balanced": {"min_ram_gb": 16, "min_vram_gb": 0, "model": "qwen3:4b"},
    "advanced": {"min_ram_gb": 24, "min_vram_gb": 6, "model": "qwen3:4b"},
    "code": {"min_ram_gb": 16, "min_vram_gb": 8, "model": "qwen3:4b"},
    "vision": {"min_ram_gb": 24, "min_vram_gb": 8, "model": "qwen3:4b"},
}

# Prefer these when the profile tag is not installed (e.g. user downloaded Starter).
CHAT_FALLBACK_ORDER = (
    "qwen3:4b",
    "qwen2.5:1.5b",
    "qwen2.5:3b",
    "llama3.2:3b",
    "llama3.2:1b",
    "phi3:mini",
)


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


def _match_installed(tag: str, installed: list[str]) -> str | None:
    """Return the concrete Ollama name for tag, or None."""
    if not tag:
        return None
    for t in installed:
        if t == tag or t.startswith(tag + "-") or t.startswith(tag + ":"):
            return t
        if tag in t:
            return t
        base = tag.split(":")[0]
        if t.split(":")[0] == base and ":" in tag and tag.split(":", 1)[1] in t:
            return t
    return None


def resolve_chat_model(
    profile: str | None = None,
    host: str = "http://127.0.0.1:11434",
    model: str | None = None,
) -> tuple[str, str]:
    """
    Pick an Ollama tag that is actually installed.
    Returns (tag, resolved_profile).
    """
    resolved_profile = profile or recommend(probe_hardware())
    hw = probe_hardware()
    if resolved_profile in PROFILES and not is_compatible(resolved_profile, hw):
        resolved_profile = recommend(hw)
    preferred = model or PROFILES.get(resolved_profile, PROFILES["tiny"])["model"]
    installed = [t for t in ollama_tags(host) if t]
    if not installed:
        return preferred, resolved_profile
    hit = _match_installed(preferred, installed)
    if hit:
        return hit, resolved_profile
    for cand in CHAT_FALLBACK_ORDER:
        hit = _match_installed(cand, installed)
        if hit:
            return hit, resolved_profile
    for t in installed:
        if "embed" not in t.lower():
            return t, resolved_profile
    return preferred, resolved_profile


def model_for_profile(profile: str | None = None) -> str:
    """Resolve Ollama model tag for a profile. Prefers an installed model."""
    tag, _ = resolve_chat_model(profile=profile)
    return tag


def _http_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    import urllib.error

    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            detail = str(e.reason)
        raise RuntimeError(f"HTTP {e.code}: {detail or e.reason}") from e


def _extract_text(payload: dict[str, Any] | None) -> str:
    """Pull assistant text from OpenAI or native Ollama message shapes."""
    if not payload:
        return ""
    # Direct string fields
    for key in ("content", "response", "thinking", "reasoning"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    # OpenAI-style nested message
    msg = payload.get("message")
    if isinstance(msg, dict):
        for key in ("content", "thinking", "reasoning"):
            val = msg.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # content as list of parts
        parts = msg.get("content")
        if isinstance(parts, list):
            bits = []
            for p in parts:
                if isinstance(p, str) and p.strip():
                    bits.append(p.strip())
                elif isinstance(p, dict):
                    t = p.get("text") or p.get("content") or ""
                    if isinstance(t, str) and t.strip():
                        bits.append(t.strip())
            if bits:
                return "\n".join(bits)
    # choices[0]
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        return _extract_text(choices[0] if isinstance(choices[0], dict) else {})
    return ""


def chat(
    messages: list[dict[str, str]],
    profile: str | None = None,
    host: str = "http://127.0.0.1:11434",
    timeout: float = 300.0,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Call Ollama for chat. Prefers OpenAI-compatible API, falls back to /api/chat.
    Returns {"content": str, "model": str, "profile": str} or raises RuntimeError.
    """
    tag, resolved_profile = resolve_chat_model(profile=profile, host=host, model=model)
    host = host.rstrip("/")
    errors: list[str] = []

    # Normalize: never end on an assistant turn (small models often emit empty then).
    clean_msgs: list[dict[str, str]] = []
    for m in messages:
        role = (m.get("role") or "user").strip()
        content = m.get("content")
        if content is None:
            continue
        text = str(content).strip()
        if not text:
            continue
        if role not in ("system", "user", "assistant"):
            role = "user"
        clean_msgs.append({"role": role, "content": text})
    if not clean_msgs:
        raise RuntimeError("ollama_chat_failed: no messages")
    if clean_msgs[-1]["role"] == "assistant":
        clean_msgs.append(
            {
                "role": "user",
                "content": "Please continue and answer the user based on the context above.",
            }
        )

    # 1) OpenAI-compatible
    try:
        data = _http_json(
            host + "/v1/chat/completions",
            {
                "model": tag,
                "messages": clean_msgs,
                "stream": False,
                "temperature": 0.2,
            },
            timeout,
        )
        content = _extract_text(data)
        if not content:
            raise RuntimeError("empty content from /v1/chat/completions")
        return {
            "content": content,
            "model": data.get("model", tag),
            "profile": resolved_profile,
            "raw": data,
        }
    except Exception as e:
        errors.append(f"openai_compat: {e}")

    # 2) Native Ollama chat API
    try:
        data = _http_json(
            host + "/api/chat",
            {
                "model": tag,
                "messages": clean_msgs,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout,
        )
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        content = _extract_text(data)
        if not content:
            raise RuntimeError("empty content from /api/chat")
        return {
            "content": content,
            "model": data.get("model", tag),
            "profile": resolved_profile,
            "raw": data,
        }
    except Exception as e:
        errors.append(f"native_chat: {e}")

    # 3) Last resort: /api/generate with a flat prompt
    try:
        flat = []
        for m in clean_msgs:
            flat.append(f"{m['role'].upper()}: {m['content']}")
        flat.append("ASSISTANT:")
        data = _http_json(
            host + "/api/generate",
            {
                "model": tag,
                "prompt": "\n".join(flat),
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout,
        )
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        content = _extract_text(data) or str(data.get("response") or "").strip()
        if not content:
            raise RuntimeError("empty content from /api/generate")
        return {
            "content": content,
            "model": data.get("model", tag),
            "profile": resolved_profile,
            "raw": data,
        }
    except Exception as e:
        errors.append(f"generate: {e}")

    installed = ollama_tags(host)
    raise RuntimeError(
        f"ollama_chat_failed model={tag} installed={installed or '[]'}; "
        + "; ".join(errors)
    )


if __name__ == "__main__":
    print(json.dumps(recommendation_bundle(), indent=2))
