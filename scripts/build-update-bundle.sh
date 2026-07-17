#!/usr/bin/env bash
# Build sample offline update bundles (good + broken-for-rollback).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/updates"
ISO_UPDATES="$ROOT/config/includes.chroot/usr/share/atlas/updates"
PKG_UPDATES="$ROOT/packages/atlas-updater/usr/share/atlas/updates"

mkdir -p "$OUT" "$ISO_UPDATES" "$PKG_UPDATES"
export ATLAS_ALLOW_UNSIGNED=1
export ATLAS_ROOT="$ROOT"

python3 - <<'PY'
import json, os, shutil, sys
from pathlib import Path

ROOT = Path(os.environ["ATLAS_ROOT"])
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))
from updater import build_update_bundle

OUT = ROOT / "dist" / "updates"
ISO = ROOT / "config" / "includes.chroot" / "usr" / "share" / "atlas" / "updates"
PKG = ROOT / "packages" / "atlas-updater" / "usr" / "share" / "atlas" / "updates"
os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"


def make(name: str, *, force_fail: bool, version: str, content: str) -> Path:
    stage = OUT / f"staging-{name}"
    if stage.exists():
        shutil.rmtree(stage)
    payload = stage / "payload" / "srv" / "atlas" / "update-demo"
    payload.mkdir(parents=True)
    (payload / "update-marker.txt").write_text(content, encoding="utf-8")
    if force_fail:
        (stage / "payload" / ".force-health-fail").write_text("1", encoding="utf-8")
    manifest = {
        "schema": "atlas.update/v1",
        "from_version": "0.1.0",
        "to_version": version,
        "publisher": "atlas-os",
        "digest": "sha256:" + "0" * 64,
        "reboot_required": False,
        "health_urls": ["http://127.0.0.1:8787/"],
        "force_health_fail": force_fail,
    }
    (stage / "update.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    notes = "Broken update for rollback demo.\n" if force_fail else "Good stub update (marker only).\n"
    (stage / "RELEASE_NOTES.txt").write_text(notes, encoding="utf-8")
    out = OUT / f"{name}.atlas-update"
    digest = build_update_bundle(stage, out)
    print("Wrote", out, digest)
    return out


good = make("atlas-update-0.1.0-to-0.1.1", force_fail=False, version="0.1.1", content="update-ok")
bad = make("atlas-update-broken-rollback", force_fail=True, version="0.1.1-broken", content="update-bad")
for p in (good, bad):
    shutil.copy2(p, ISO / p.name)
    shutil.copy2(p, PKG / p.name)
print("Staged to", ISO, "and", PKG)
PY
