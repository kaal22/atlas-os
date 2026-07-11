#!/usr/bin/env python3
"""Content pack manifest schema checks (product §26)."""
import json

REQUIRED = {
    "schema",
    "id",
    "version",
    "type",
    "name",
    "description",
    "size_bytes",
    "minimum_os_version",
    "architectures",
    "mount_target",
    "licences",
    "sources",
    "dependencies",
    "conflicts",
    "digest",
}

VALID_TYPES = {
    "atlas.content.knowledge",
    "atlas.content.map",
    "atlas.content.education",
    "atlas.content.model",
    "atlas.content.agent",
    "atlas.content.workflow",
    "atlas.content.language",
    "atlas.content.media",
}


def validate_manifest(m: dict) -> list[str]:
    errors = []
    missing = REQUIRED - set(m)
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    if m.get("schema") != "atlas.pack/v1":
        errors.append("schema must be atlas.pack/v1")
    if m.get("type") not in VALID_TYPES:
        errors.append(f"invalid type: {m.get('type')}")
    digest = m.get("digest", "")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        errors.append("digest must be sha256:...")
    return errors


SAMPLE = {
    "schema": "atlas.pack/v1",
    "id": "atlas.maps.uk",
    "version": "2026.07",
    "type": "atlas.content.map",
    "name": "United Kingdom Offline Maps",
    "description": "Regional offline maps and search index.",
    "size_bytes": 0,
    "minimum_os_version": "1.0.0",
    "architectures": ["all"],
    "mount_target": "/srv/atlas/maps/uk",
    "licences": [],
    "sources": [],
    "dependencies": [],
    "conflicts": [],
    "post_install_workflow": "maps.reindex",
    "digest": "sha256:deadbeef",
}


def test_sample_ok():
    assert validate_manifest(SAMPLE) == []


def test_rejects_bad_type():
    bad = dict(SAMPLE, type="not.a.type")
    assert any("invalid type" in e for e in validate_manifest(bad))


def test_rejects_missing_digest_prefix():
    bad = dict(SAMPLE, digest="abc")
    assert any("digest" in e for e in validate_manifest(bad))


if __name__ == "__main__":
    test_sample_ok()
    test_rejects_bad_type()
    test_rejects_missing_digest_prefix()
    print("OK test_pack_manifest")
    print(json.dumps(SAMPLE, indent=2)[:80], "...")
