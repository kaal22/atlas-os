# Atlas OS hardware targets (Phase 0)

## Minimum supported tier

- CPU: x86-64, 4 cores recommended
- RAM: 8 GiB (16 GiB preferred for Balanced AI profile)
- Storage: 128 GiB SSD (256 GiB+ for content packs)
- GPU: optional; CPU inference supported for Tiny/Light profiles
- Firmware: UEFI

## Recommended personal tier

- 16–32 GiB RAM
- NVIDIA or AMD discrete GPU with ≥6 GiB VRAM for Advanced profiles
- 512 GiB+ NVMe

## Initial certification candidates

- Generic QEMU/KVM UEFI reference (CI)
- Mini PC class: Intel N100 / N305 systems
- Laptop class: recent Dell/Lenovo Ubuntu-certified equivalents

Compatibility results are recorded in `docs/hardware/compatibility.json` as tests land.
