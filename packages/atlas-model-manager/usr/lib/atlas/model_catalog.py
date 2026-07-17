#!/usr/bin/env python3
"""Beginner-facing model catalogue, status, and Ollama pull jobs."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from model_router import (
    PROFILES,
    Hardware,
    ollama_tags,
    probe_hardware,
    recommend,
    recommendation_bundle,
)

# Curated allowlist — CC will only pull these tags (beginner safety).
CATALOGUE: list[dict[str, Any]] = [
    {
        "id": "starter-cpu",
        "tag": "qwen2.5:1.5b",
        "title": "Starter (CPU)",
        "blurb": "Smallest chat model. Best for low-RAM VMs and slow machines.",
        "size_gb": 1.0,
        "min_ram_gb": 4,
        "min_vram_gb": 0,
        "cpu_ok": True,
        "beginner": True,
        "profiles": ["tiny"],
    },
    {
        "id": "recommended-cpu",
        "tag": "qwen3:4b",
        "title": "Recommended (CPU)",
        "blurb": "Default Atlas Guide model. Good balance for most PCs without a GPU.",
        "size_gb": 2.5,
        "min_ram_gb": 8,
        "min_vram_gb": 0,
        "cpu_ok": True,
        "beginner": True,
        "profiles": ["light", "balanced", "tiny"],
    },
    {
        "id": "embed",
        "tag": "nomic-embed-text",
        "title": "Embeddings",
        "blurb": "For document search later. Optional now; needed for knowledge packs.",
        "size_gb": 0.3,
        "min_ram_gb": 4,
        "min_vram_gb": 0,
        "cpu_ok": True,
        "beginner": True,
        "profiles": ["tiny", "light", "balanced"],
        "kind": "embed",
    },
    {
        "id": "gpu-advanced",
        "tag": "qwen3:14b",
        "title": "Advanced (GPU)",
        "blurb": "Larger model. Needs a working NVIDIA GPU with enough VRAM.",
        "size_gb": 9.0,
        "min_ram_gb": 16,
        "min_vram_gb": 8,
        "cpu_ok": False,
        "beginner": False,
        "profiles": ["advanced", "code"],
    },
]

ALLOWED_TAGS = {c["tag"] for c in CATALOGUE}

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def ollama_reachable(host: str = "http://127.0.0.1:11434") -> bool:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def installed_models(host: str = "http://127.0.0.1:11434") -> list[str]:
    return [t for t in ollama_tags(host) if t]


def _tag_installed(tag: str, installed: list[str]) -> bool:
    # Ollama may report "qwen3:4b" or "qwen3:4b-..." variants
    base = tag.split(":")[0]
    for t in installed:
        if t == tag or t.startswith(tag) or (tag in t):
            return True
        if t.split(":")[0] == base and ":" in tag and tag.split(":", 1)[1] in t:
            return True
    return tag in installed or any(t.startswith(tag) for t in installed)


def catalogue_for_hardware(hw: Hardware, installed: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in CATALOGUE:
        ok = hw.ram_gb >= item["min_ram_gb"] and hw.vram_gb >= item["min_vram_gb"]
        reasons: list[str] = []
        if hw.ram_gb < item["min_ram_gb"]:
            reasons.append(f"Needs at least {item['min_ram_gb']} GB RAM (you have {hw.ram_gb})")
        if item["min_vram_gb"] > 0 and hw.vram_gb < item["min_vram_gb"]:
            reasons.append(
                f"Needs about {item['min_vram_gb']} GB GPU memory"
                + (" — install NVIDIA drivers first" if not hw.nvidia_driver_ok else "")
            )
        entry = {
            **item,
            "compatible": ok,
            "installed": _tag_installed(item["tag"], installed),
            "blockers": reasons,
        }
        out.append(entry)
    return out


def pick_recommended(catalogue: list[dict[str, Any]], profile: str) -> dict[str, Any] | None:
    # Prefer compatible beginner chat models matching profile, not yet installed
    chat = [c for c in catalogue if c.get("kind") != "embed" and c["compatible"] and c["beginner"]]
    if not chat:
        chat = [c for c in catalogue if c.get("kind") != "embed" and c["compatible"]]
    # Prefer ones listed for this profile
    ranked = sorted(
        chat,
        key=lambda c: (
            0 if profile in c.get("profiles", []) else 1,
            0 if not c["installed"] else 1,
            c["size_gb"],
        ),
    )
    return ranked[0] if ranked else None


def model_setup_status(host: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    hw = probe_hardware()
    profile = recommend(hw)
    reachable = ollama_reachable(host)
    installed = installed_models(host) if reachable else []
    catalogue = catalogue_for_hardware(hw, installed)
    recommended = pick_recommended(catalogue, profile)
    # Installed chat models count as ready even if over recommended RAM —
    # beginners should not be stuck on "download model" after a successful pull.
    chat_ready = any(
        c["installed"] and c.get("kind") != "embed" for c in catalogue
    )
    profile_tag = PROFILES.get(profile, PROFILES["tiny"])["model"]
    if _tag_installed(profile_tag, installed):
        chat_ready = True
    if not chat_ready and installed:
        chat_ready = any(
            not str(t).startswith("nomic-embed") for t in installed
        )

    bundle = recommendation_bundle()
    embed_ready = any(
        c["installed"] and c.get("kind") == "embed" for c in catalogue
    ) or _tag_installed("nomic-embed-text", installed)
    return {
        "ollama_reachable": reachable,
        "ready": bool(reachable and chat_ready),
        "embed_ready": bool(reachable and embed_ready),
        "profile": profile,
        "hardware": {
            "ram_gb": hw.ram_gb,
            "vram_gb": hw.vram_gb,
            "gpu": hw.gpu,
            "nvidia_driver_ok": hw.nvidia_driver_ok,
        },
        "installed": installed,
        "recommended": recommended,
        "catalogue": catalogue,
        "needs_network_to_download": True,
        "hint": (
            "Download the recommended model once (needs internet). After that, Atlas works offline."
            if not chat_ready
            else "A chat model is installed. You can ask Atlas Guide."
        ),
        "embed_hint": (
            None
            if embed_ready
            else "Download nomic-embed-text for semantic Knowledge search."
        ),
        "gpu_warning": bundle.get("warning"),
        "pull_jobs": list_jobs(),
    }


def list_jobs() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(j) for j in _JOBS.values()]


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def _set_job(job_id: str, **fields: Any) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def _pull_worker(job_id: str, tag: str, host: str) -> None:
    _set_job(job_id, status="running", message=f"Downloading {tag}…", progress=0)
    url = host.rstrip("/") + "/api/pull"
    body = json.dumps({"name": tag, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                status = ev.get("status") or ""
                total = ev.get("total") or 0
                completed = ev.get("completed") or 0
                pct = int(completed * 100 / total) if total else None
                if pct is None and status:
                    # Ollama often omits totals early — show activity anyway
                    low = status.lower()
                    if "success" in low:
                        pct = 100
                    elif "pulling" in low or "downloading" in low or "verifying" in low:
                        with _LOCK:
                            prev = _JOBS.get(job_id, {}).get("progress") or 5
                        pct = min(prev + 2, 95) if prev < 95 else prev
                _set_job(
                    job_id,
                    status="running",
                    message=status or f"Downloading {tag}",
                    progress=pct if pct is not None else _JOBS.get(job_id, {}).get("progress", 5),
                    last_event=status,
                )
        # Verify install
        time.sleep(0.5)
        installed = installed_models(host)
        if _tag_installed(tag, installed):
            _set_job(job_id, status="completed", progress=100, message=f"{tag} ready")
        else:
            _set_job(job_id, status="completed", progress=100, message=f"Pull finished for {tag}")
    except urllib.error.HTTPError as e:
        _set_job(job_id, status="failed", message=f"Download failed HTTP {e.code}: {e.reason}")
    except Exception as e:
        _set_job(
            job_id,
            status="failed",
            message=f"Download failed: {e}. Check internet and that Ollama is running.",
        )


def start_pull(tag: str, host: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    if tag not in ALLOWED_TAGS:
        raise ValueError(f"model_not_in_catalogue: {tag}")
    if not ollama_reachable(host):
        raise RuntimeError("ollama_unreachable")
    # Idempotent if already installed
    if _tag_installed(tag, installed_models(host)):
        job_id = str(uuid.uuid4())
        with _LOCK:
            _JOBS[job_id] = {
                "id": job_id,
                "tag": tag,
                "status": "completed",
                "progress": 100,
                "message": f"{tag} already installed",
                "started": int(time.time()),
            }
        return get_job(job_id)  # type: ignore[return-value]

    # Avoid duplicate running pulls for same tag
    with _LOCK:
        for j in _JOBS.values():
            if j.get("tag") == tag and j.get("status") in {"queued", "running"}:
                return dict(j)

    job_id = str(uuid.uuid4())
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "tag": tag,
            "status": "queued",
            "progress": 0,
            "message": "Starting download…",
            "started": int(time.time()),
        }
    t = threading.Thread(target=_pull_worker, args=(job_id, tag, host), daemon=True)
    t.start()
    return get_job(job_id)  # type: ignore[return-value]


def persist_jobs(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jobs": list_jobs()}, indent=2), encoding="utf-8")
