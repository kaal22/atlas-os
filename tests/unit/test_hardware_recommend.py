#!/usr/bin/env python3
"""Hardware-aware model profile recommendations (product §20)."""

PROFILES = {
    "tiny": {"min_ram_gb": 4, "min_vram_gb": 0},
    "light": {"min_ram_gb": 8, "min_vram_gb": 0},
    "balanced": {"min_ram_gb": 16, "min_vram_gb": 0},
    "advanced": {"min_ram_gb": 24, "min_vram_gb": 6},
    "code": {"min_ram_gb": 16, "min_vram_gb": 8},
    "vision": {"min_ram_gb": 24, "min_vram_gb": 8},
}


def recommend(ram_gb: float, vram_gb: float = 0.0) -> str:
    order = ["vision", "code", "advanced", "balanced", "light", "tiny"]
    for name in reversed(order):
        req = PROFILES[name]
        if ram_gb >= req["min_ram_gb"] and vram_gb >= req["min_vram_gb"]:
            best = name
    # pick highest that fits
    best = "tiny"
    for name in ["tiny", "light", "balanced", "advanced", "code", "vision"]:
        req = PROFILES[name]
        if ram_gb >= req["min_ram_gb"] and vram_gb >= req["min_vram_gb"]:
            best = name
    return best


def is_compatible(profile: str, ram_gb: float, vram_gb: float = 0.0) -> bool:
    req = PROFILES[profile]
    return ram_gb >= req["min_ram_gb"] and vram_gb >= req["min_vram_gb"]


def test_low_ram_gets_tiny():
    assert recommend(4, 0) == "tiny"


def test_16gb_balanced():
    assert recommend(16, 0) == "balanced"


def test_blocks_advanced_without_vram():
    assert not is_compatible("advanced", 32, 0)
    assert is_compatible("advanced", 32, 8)


if __name__ == "__main__":
    test_low_ram_gets_tiny()
    test_16gb_balanced()
    test_blocks_advanced_without_vram()
    print("OK test_hardware_recommend")
