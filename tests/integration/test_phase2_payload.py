#!/usr/bin/env python3
"""Static checks for Phase 2 offline core payload wiring."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_loopback_only():
    raw = (ROOT / "containers/compose/atlas-core.yml").read_text(encoding="utf-8")
    # Strip comments before asserting no socket mount.
    text = "\n".join(
        ln for ln in raw.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "/var/run/docker.sock" not in text
    assert "docker.sock" not in text
    ports = re.findall(r'-\s*"([^"]+)"', text)
    published = [p for p in ports if re.search(r":\d+:\d+", p) or re.match(r"\d+:\d+", p)]
    for p in published:
        assert p.startswith("127.0.0.1:"), f"non-loopback publish: {p}"
    assert "ghcr.io/crosstalk-solutions/project-nomad:v1.33.0" in text
    assert "ghcr.io/atlas-os/atlas-nomad-core" not in text


def test_purge_removes_home_desktop_icons():
    script = (
        ROOT
        / "config/includes.chroot/usr/share/calamares/helpers/atlas-purge-live-packages"
    ).read_text(encoding="utf-8")
    assert "/home/*/Desktop" in script
    assert "install-atlas-os.desktop" in script


def test_docker_packages_listed():
    pkgs = (ROOT / "config/package-lists/atlas.list.chroot").read_text(encoding="utf-8")
    for name in ("docker.io", "docker-compose", "containerd"):
        assert name in pkgs, name


def test_firstboot_fail_closed():
    fb = (ROOT / "packages/atlas-firstboot/usr/lib/atlas/atlas-firstboot.sh").read_text(
        encoding="utf-8"
    )
    imp = (ROOT / "packages/atlas-firstboot/usr/lib/atlas/import-payload.sh").read_text(
        encoding="utf-8"
    )
    assert "|| true" not in fb.split("import-payload")[-1] or "fail" in fb
    assert "import-payload.sh || true" not in fb
    assert "fail closed" in imp.lower() or "payload-enabled" in imp
    assert "docker load" in imp
    assert "|| true" not in [ln for ln in imp.splitlines() if "docker load" in ln][0]


def test_phase2_iso_script_exists():
    assert (ROOT / "scripts/phase2-iso.sh").is_file()
    assert (ROOT / "scripts/collect-phase2-evidence.sh").is_file()


def test_launcher_health():
    assert (ROOT / "packages/atlas-shell/usr/bin/atlas-health").is_file()
    html = (ROOT / "packages/atlas-shell/usr/share/atlas/launcher/index.html").read_text(
        encoding="utf-8"
    )
    assert "127.0.0.1:8080" in html
    assert "127.0.0.1:11434" in html
    launcher = (ROOT / "packages/atlas-shell/usr/bin/atlas-launcher").read_text(
        encoding="utf-8"
    )
    assert "8791" in launcher or "atlas-health" in launcher
    imp = (ROOT / "packages/atlas-firstboot/usr/lib/atlas/import-payload.sh").read_text(
        encoding="utf-8"
    )
    assert "/srv/atlas/tmp" in imp
    assert "exec > >(tee" not in imp


def test_firstboot_not_armed_in_image_hooks():
    hook = (ROOT / "config/hooks/normal/9010-atlas-firstboot-marker.hook.chroot").read_text(
        encoding="utf-8"
    )
    assert "touch /etc/atlas/firstboot-pending" not in hook
    assert "rm -f /etc/atlas/firstboot-pending" in hook
    purge = (
        ROOT
        / "config/includes.chroot/usr/share/calamares/helpers/atlas-purge-live-packages"
    ).read_text(encoding="utf-8")
    assert 'touch "$CHROOT/etc/atlas/firstboot-pending"' in purge
    unit = (
        ROOT / "packages/atlas-firstboot/lib/systemd/system/atlas-firstboot.service"
    ).read_text(encoding="utf-8")
    assert "ConditionKernelCommandLine=!boot=live" in unit


if __name__ == "__main__":
    test_compose_loopback_only()
    test_purge_removes_home_desktop_icons()
    test_docker_packages_listed()
    test_firstboot_fail_closed()
    test_phase2_iso_script_exists()
    test_launcher_health()
    test_firstboot_not_armed_in_image_hooks()
    print("OK test_phase2_payload")
