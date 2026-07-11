#!/usr/bin/env python3
"""Detect GPU hardware and driver readiness for local AI (Ollama)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GpuReport:
    has_nvidia_pci: bool = False
    has_amd_pci: bool = False
    has_intel_pci: bool = False
    nvidia_driver_ok: bool = False
    nvidia_smi: str | None = None
    gpu_name: str = "none"
    vram_gb: float = 0.0
    ollama_reachable: bool = False
    ollama_likely_gpu: bool | None = None
    severity: str = "info"  # info | warn | critical
    title: str = "GPU status"
    message: str = ""
    actions: list[str] = field(default_factory=list)
    guide_path: str = "/usr/share/atlas/docs/GPU_SETUP.md"


def _run(cmd: list[str], timeout: float = 3.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 127, ""


def _lspci() -> str:
    code, out = _run(["lspci"])
    if code != 0:
        code, out = _run(["lspci", "-nn"])
    return out.lower()


def probe_gpu() -> GpuReport:
    report = GpuReport()
    pci = _lspci()
    report.has_nvidia_pci = "nvidia" in pci and (
        "vga" in pci or "3d" in pci or "display" in pci or "nvrm" in pci or True
    )
    # More precise NVIDIA VGA/3D lines
    report.has_nvidia_pci = bool(re.search(r"nvidia.*(vga|3d|display)", pci)) or (
        "nvidia corporation" in pci and ("vga compatible" in pci or "3d controller" in pci)
    )
    if not report.has_nvidia_pci and "nvidia" in pci:
        # Fallback: any NVIDIA display-ish device
        for line in pci.splitlines():
            if "nvidia" in line and any(k in line for k in ("vga", "3d", "display", "nvswitch")):
                report.has_nvidia_pci = True
                break

    report.has_amd_pci = bool(re.search(r"(amd/ati|advanced micro devices).*?(vga|3d|display)", pci))
    report.has_intel_pci = bool(re.search(r"intel.*?(vga|3d|display|graphics)", pci))

    if shutil.which("nvidia-smi"):
        code, out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
        if code == 0 and out.strip():
            report.nvidia_driver_ok = True
            line = out.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if parts:
                report.gpu_name = parts[0]
            if len(parts) > 1:
                try:
                    # memory.total is MiB
                    report.vram_gb = round(float(parts[1]) / 1024.0, 1)
                except ValueError:
                    pass
            report.nvidia_smi = out.strip()

    # Ollama reachability
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as resp:
            report.ollama_reachable = resp.status == 200
    except Exception:
        report.ollama_reachable = False

    # Heuristic: if NVIDIA present but no driver, Ollama will be CPU-only
    if report.has_nvidia_pci and not report.nvidia_driver_ok:
        report.severity = "critical"
        report.title = "NVIDIA GPU detected — drivers missing"
        report.message = (
            "This computer has an NVIDIA GPU, but proprietary drivers are not active. "
            "Ollama will run on CPU only, which is much slower. Install drivers to unlock GPU AI."
        )
        report.actions = [
            "Open System → GPU & AI setup in Command Centre",
            "Or run: atlas-gpu-setup --guide",
            "Read /usr/share/atlas/docs/GPU_SETUP.md",
        ]
        report.gpu_name = report.gpu_name if report.gpu_name != "none" else "NVIDIA (driver missing)"
        report.ollama_likely_gpu = False
    elif report.has_nvidia_pci and report.nvidia_driver_ok:
        report.severity = "info"
        report.title = "NVIDIA GPU ready"
        report.message = (
            f"NVIDIA drivers look healthy ({report.gpu_name}, ~{report.vram_gb} GiB VRAM). "
            "Ollama can use the GPU for faster local models."
        )
        report.actions = ["Verify with: nvidia-smi", "Then: ollama run qwen3:4b"]
        report.ollama_likely_gpu = True
    elif report.has_amd_pci:
        report.severity = "warn"
        report.title = "AMD GPU detected"
        report.message = (
            "AMD GPUs can work with Ollama on Linux, but support varies by card and ROCm stack. "
            "Atlas will recommend CPU-safe profiles until AMD acceleration is confirmed."
        )
        report.actions = ["See GPU_SETUP.md AMD section", "Prefer Light/Balanced profiles first"]
        report.gpu_name = "AMD"
        report.ollama_likely_gpu = None
    elif report.has_intel_pci:
        report.severity = "info"
        report.title = "Intel graphics only"
        report.message = (
            "No discrete NVIDIA/AMD GPU detected. Local AI will use CPU (and possibly Intel iGPU). "
            "Choose Tiny or Light model profiles for best responsiveness."
        )
        report.actions = ["Use Tiny/Light AI profile in Setup"]
        report.gpu_name = "Intel"
        report.ollama_likely_gpu = False
    else:
        report.severity = "info"
        report.title = "No discrete GPU detected"
        report.message = "Atlas will use CPU inference. Prefer Tiny or Light profiles."
        report.actions = ["Use Tiny/Light AI profile in Setup"]

    return report


def as_api_dict(report: GpuReport | None = None) -> dict[str, Any]:
    r = report or probe_gpu()
    return asdict(r)


if __name__ == "__main__":
    print(json.dumps(as_api_dict(), indent=2))
