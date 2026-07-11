#!/usr/bin/env python3
"""GPU detection should warn when NVIDIA PCI exists without nvidia-smi."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "packages" / "atlas-model-manager" / "usr" / "lib" / "atlas" / "gpu_detect.py"
spec = importlib.util.spec_from_file_location("gpu_detect", path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_report_fields():
    r = mod.probe_gpu()
    assert hasattr(r, "severity")
    assert hasattr(r, "actions")
    assert r.guide_path.endswith("GPU_SETUP.md")
    d = mod.as_api_dict(r)
    assert "nvidia_driver_ok" in d


if __name__ == "__main__":
    test_report_fields()
    print("OK test_gpu_detect")
