#!/usr/bin/env python3
"""First-boot must not embed static production secrets in the repo/ISO tree."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PATTERNS = [
    "MYSQL_ROOT_PASSWORD=root",
    "PASSWORD=password",
    "API_KEY=sk-",
]


def test_no_hardcoded_secrets_in_includes():
    includes = ROOT / "config" / "includes.chroot"
    hits = []
    for p in includes.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in FORBIDDEN_PATTERNS:
            if pat in text:
                hits.append((str(p), pat))
    assert hits == [], hits


def test_firstboot_script_generates_secrets():
    script = ROOT / "packages" / "atlas-firstboot" / "usr" / "lib" / "atlas" / "atlas-firstboot.sh"
    text = script.read_text(encoding="utf-8")
    assert "openssl rand" in text
    assert "/etc/atlas/secrets" in text


if __name__ == "__main__":
    test_no_hardcoded_secrets_in_includes()
    test_firstboot_script_generates_secrets()
    print("OK test_firstboot_secrets")
