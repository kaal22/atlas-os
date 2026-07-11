# GPU & AI acceleration setup (Atlas OS)

Local AI (Ollama) works on CPU without drivers, but it will feel slow on larger models.
If your PC has an NVIDIA GPU, install proprietary drivers so Ollama can use the GPU.

## Quick check

```bash
atlas-gpu-setup --check
```

Healthy NVIDIA looks like `"nvidia_driver_ok": true` and a non-zero `vram_gb`.

## NVIDIA (recommended path on Atlas / Debian)

1. Connect to the internet once (driver packages are large).
2. Run:

```bash
sudo atlas-gpu-setup --install-nvidia
```

3. Reboot.
4. Confirm:

```bash
nvidia-smi
atlas-gpu-setup --check
sudo systemctl restart ollama
```

5. In Command Centre → Setup / Models, pick a profile that matches your VRAM
   (Advanced / Code / Vision need dedicated GPU memory).

### Manual Debian packages (same result)

Enable `contrib`, `non-free`, and `non-free-firmware` in APT, then:

```bash
sudo apt update
sudo apt install linux-headers-amd64 nvidia-detect nvidia-driver nvidia-smi
sudo reboot
```

`nvidia-detect` prints which driver series fits your card.

## If you stay on CPU

That is fine. In first-run / AI profile, choose:

- **Tiny** or **Light** for 8–16 GB RAM systems without a GPU
- Avoid Advanced / Vision until a GPU is working

## AMD GPUs

ROCm support varies by card and Debian release. Atlas detects AMD and warns, then
defaults to CPU-safe profiles until acceleration is verified. Prefer Light/Balanced
first; see Ollama’s AMD docs for ROCm setup on your specific GPU.

## Intel-only laptops

Use Tiny/Light profiles. Integrated graphics may help some workloads, but Atlas
treats these systems as CPU-first for reliable recommendations.

## Secure Boot note

Some machines with Secure Boot need NVIDIA’s MOK enrollment after install.
If the driver fails to load after reboot, temporarily enroll the key when prompted,
or install with Secure Boot disabled, then re-enable if required by policy.

## What Atlas does automatically

- Detects NVIDIA / AMD / Intel during Setup and System health
- Warns when an NVIDIA GPU is present but drivers are missing
- Recommends AI profiles that won’t freeze your machine
- Ships this guide offline at `/usr/share/atlas/docs/GPU_SETUP.md`

Atlas does **not** silently install proprietary drivers without your approval.
