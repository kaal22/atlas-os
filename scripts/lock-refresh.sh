#!/usr/bin/env bash
# Internet-connected lock refresh: resolve digests, download OCI + Ollama + NOMAD source.
set -euo pipefail

RELEASE="${1:?release dir}"
CACHE="${2:?cache dir}"
CATALOG="$RELEASE/sources.catalog.yaml"
LOCK="$RELEASE/sources.lock.yaml"
mkdir -p "$CACHE"/{oci,source,ollama,models,licences,sbom}

if ! command -v python3 >/dev/null; then
  echo "python3 required" >&2
  exit 1
fi

if ! command -v skopeo >/dev/null; then
  echo "ERROR: skopeo required for lock-refresh" >&2
  exit 1
fi

python3 - "$CATALOG" "$LOCK" "$CACHE" <<'PY'
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from shutil import which

catalog, lock_path, cache = map(Path, sys.argv[1:])
assets = []

def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Phase 2 core images (no large ZIM/models)
images = [
    "mysql:8.0",
    "redis:7-alpine",
    "ghcr.io/kiwix/kiwix-serve:3.8.2",
    "qdrant/qdrant:v1.16",
    "treehouses/kolibri:0.12.8",
    "ghcr.io/gchq/cyberchef:10.24",
    "dullage/flatnotes:v5.5.4",
    "ghcr.io/crosstalk-solutions/project-nomad:v1.33.0",
]

def skopeo_digest(ref: str):
    try:
        out = subprocess.check_output(
            ["skopeo", "inspect", "--override-os", "linux", "--override-arch", "amd64", f"docker://{ref}"],
            text=True,
            stderr=subprocess.PIPE,
        )
        data = json.loads(out)
        return data.get("Digest")
    except Exception as e:
        print(f"WARN: inspect failed for {ref}: {e}", file=sys.stderr)
        return None

def archive_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

for ref in images:
    digest = skopeo_digest(ref)
    safe = ref.replace("/", "_").replace(":", "_").replace("@", "_")
    dest = cache / "oci" / f"{safe}.tar"
    entry = {
        "type": "oci",
        "ref": ref,
        "digest": digest,
        "archive": str(dest.relative_to(cache)) if dest.exists() or digest else f"oci/{safe}.tar",
        "status": "pending",
    }
    if digest:
        if not dest.exists() or dest.stat().st_size < 1000:
            print(f"Copying {ref}@{digest} -> {dest}")
            try:
                # Omit :ref — refs with colons break docker-archive parsing and
                # produce archives with empty RepoTags (breaks firstboot inspect).
                subprocess.check_call([
                    "skopeo", "copy",
                    "--override-os", "linux", "--override-arch", "amd64",
                    f"docker://{ref}",
                    f"docker-archive:{dest}",
                ])
            except Exception as e:
                entry["copy_error"] = str(e)
                entry["status"] = "copy_failed"
                assets.append(entry)
                continue
        entry["archive_sha256"] = archive_sha256(dest)
        entry["archive_bytes"] = dest.stat().st_size
        entry["status"] = "resolved"
    else:
        entry["status"] = "pending_network"
    assets.append(entry)

# Host-native Ollama
ollama_ver = "0.31.2"
ollama_url = f"https://github.com/ollama/ollama/releases/download/v{ollama_ver}/ollama-linux-amd64.tar.zst"
ollama_sha = "2c88f0f31a959bac5a3cad4cc5296ec568551d4aa79f548f554adb2b575b3133"
ollama_path = cache / "ollama" / f"ollama-linux-amd64-{ollama_ver}.tar.zst"
ollama_entry = {
    "type": "file",
    "id": "ollama-linux-amd64",
    "version": ollama_ver,
    "url": ollama_url,
    "sha256": ollama_sha,
    "path": str(ollama_path.relative_to(cache)),
    "status": "pending",
}
if not ollama_path.exists():
    print(f"Downloading Ollama {ollama_ver}...")
    try:
        urllib.request.urlretrieve(ollama_url, ollama_path)
    except Exception as e:
        ollama_entry["download_error"] = str(e)
        assets.append(ollama_entry)
        ollama_path = None
if ollama_path and ollama_path.exists():
    got = archive_sha256(ollama_path)
    ollama_entry["archive_sha256"] = got
    ollama_entry["archive_bytes"] = ollama_path.stat().st_size
    if got.lower() == ollama_sha.lower():
        ollama_entry["status"] = "resolved"
    else:
        ollama_entry["status"] = "hash_mismatch"
        ollama_entry["got_sha256"] = got
assets.append(ollama_entry)

# NOMAD source archive
nomad_url = "https://github.com/Crosstalk-Solutions/project-nomad/archive/refs/tags/v1.33.0.tar.gz"
nomad_path = cache / "source" / "project-nomad-v1.33.0.tar.gz"
nomad_entry = {
    "type": "source",
    "id": "project-nomad",
    "version": "v1.33.0",
    "url": nomad_url,
    "path": str(nomad_path.relative_to(cache)),
    "status": "pending",
}
if not nomad_path.exists():
    print("Downloading Project N.O.M.A.D. v1.33.0 source...")
    try:
        urllib.request.urlretrieve(nomad_url, nomad_path)
    except Exception as e:
        nomad_entry["download_error"] = str(e)
if nomad_path.exists():
    nomad_entry["archive_sha256"] = archive_sha256(nomad_path)
    nomad_entry["archive_bytes"] = nomad_path.stat().st_size
    nomad_entry["status"] = "resolved"
    # Record commit if we can read from github API — optional
    commit_file = cache / "source" / "project-nomad-v1.33.0.commit"
    if not commit_file.exists():
        try:
            api = "https://api.github.com/repos/Crosstalk-Solutions/project-nomad/git/refs/tags/v1.33.0"
            with urllib.request.urlopen(api, timeout=30) as resp:
                meta = json.loads(resp.read().decode())
            obj = meta.get("object", {})
            sha = obj.get("sha")
            if obj.get("type") == "tag":
                # peel annotated tag
                with urllib.request.urlopen(obj["url"], timeout=30) as resp:
                    tag = json.loads(resp.read().decode())
                sha = tag.get("object", {}).get("sha", sha)
            if sha:
                commit_file.write_text(sha + "\n", encoding="utf-8")
                nomad_entry["commit"] = sha
        except Exception as e:
            nomad_entry["commit_error"] = str(e)
    else:
        nomad_entry["commit"] = commit_file.read_text(encoding="utf-8").strip()
assets.append(nomad_entry)

failed = [a for a in assets if a.get("status") not in ("resolved",)]
status = "locked" if not failed else "development"

lock_path.write_text(
    "# Generated by scripts/lock-refresh.sh — review before release\n"
    "schema: atlas.sources.lock/v1\n"
    'atlas_version: "0.1.0-alpha"\n'
    f'locked_at: "{utcnow_iso()}"\n'
    f"status: {status}\n"
    "notes: >\n"
    "  Phase 2 core developer payload. No Wikipedia ZIM or starter models.\n"
    "assets_json: |\n"
    + "\n".join("  " + line for line in json.dumps(assets, indent=2).splitlines())
    + "\n",
    encoding="utf-8",
)
print(f"Wrote {lock_path} status={status} assets={len(assets)} failed={len(failed)}")
if failed:
    for a in failed:
        print(f"  FAIL {a.get('ref') or a.get('id')}: {a.get('status')} {a.get('copy_error') or a.get('download_error') or ''}")
    sys.exit(1)
PY
