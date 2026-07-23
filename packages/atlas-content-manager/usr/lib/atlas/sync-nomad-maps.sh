#!/usr/bin/env bash
# Publish Atlas country PMTiles into NOMAD's MapLibre storage layout.
# Atlas:  /srv/atlas/maps/<cc>/<cc>.pmtiles (+ countries.json)
# NOMAD:  /srv/atlas/nomad-storage/maps/pmtiles/<cc>.pmtiles
set -euo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-/srv/atlas}"
MAPS_ROOT="${ATLAS_MAPS_ROOT:-$ATLAS_ROOT/maps}"
NOMAD_STORAGE="${NOMAD_STORAGE_PATH:-$ATLAS_ROOT/nomad-storage}"
PMTILES_DIR="$NOMAD_STORAGE/maps/pmtiles"
VIEWER_SRC="${ATLAS_MAPS_VIEWER_SRC:-/usr/share/atlas/maps-viewer}"
ASSETS_TAR="${ATLAS_NOMAD_MAP_ASSETS:-/usr/share/atlas/nomad-map-assets/base-assets.tar.gz}"

mkdir -p "$PMTILES_DIR" "$NOMAD_STORAGE/maps"

seed_base_assets() {
  local maps_dir="$NOMAD_STORAGE/maps"
  if [[ -f "$maps_dir/nomad-base-styles.json" && -d "$maps_dir/basemaps-assets" ]]; then
    return 0
  fi
  if [[ ! -f "$ASSETS_TAR" ]]; then
    echo "sync-nomad-maps: base assets tar missing ($ASSETS_TAR); NOMAD /maps needs online download once" >&2
    return 0
  fi
  local tmp
  tmp="$(mktemp -d)"
  # Tar root is tozip/; strip so basemaps-assets/ and nomad-base-styles.json land in maps/
  # --no-same-owner: ISO/chroot and some sandboxes cannot chown to upstream UIDs
  tar -xzf "$ASSETS_TAR" -C "$tmp" --strip-components=1 --no-same-owner || {
    echo "sync-nomad-maps: failed to extract base assets" >&2
    rm -rf "$tmp"
    return 0
  }
  mkdir -p "$maps_dir"
  if [[ -d "$tmp/basemaps-assets" ]]; then
    rm -rf "$maps_dir/basemaps-assets"
    mv "$tmp/basemaps-assets" "$maps_dir/basemaps-assets"
  fi
  if [[ -f "$tmp/nomad-base-styles.json" ]]; then
    cp -f "$tmp/nomad-base-styles.json" "$maps_dir/nomad-base-styles.json"
  fi
  rm -rf "$tmp"
  echo "sync-nomad-maps: seeded NOMAD base map assets"
}

publish_viewer() {
  if [[ ! -d "$VIEWER_SRC" ]]; then
    return 0
  fi
  mkdir -p "$NOMAD_STORAGE/maps/viewer"
  # Keep lib/ + index under storage/maps/viewer → served at http://127.0.0.1:8090/viewer/
  cp -a "$VIEWER_SRC/." "$NOMAD_STORAGE/maps/viewer/"
}

link_country_tiles() {
  local linked=0
  local cc dir tile dest
  shopt -s nullglob
  for dir in "$MAPS_ROOT"/*/; do
    [[ -d "$dir" ]] || continue
    cc="$(basename "$dir")"
    [[ "$cc" =~ ^[a-z]{2}$ ]] || continue
    tile="$dir${cc}.pmtiles"
    if [[ ! -f "$tile" ]]; then
      # accept any single .pmtiles in country dir
      local candidates=("$dir"*.pmtiles)
      if [[ ${#candidates[@]} -eq 1 && -f "${candidates[0]}" ]]; then
        tile="${candidates[0]}"
      else
        continue
      fi
    fi
    # Skip tiny stubs (< 64 KiB) — not usable basemaps
    local sz
    sz="$(stat -c%s "$tile" 2>/dev/null || echo 0)"
    if [[ "$sz" -lt 65536 ]]; then
      echo "sync-nomad-maps: skip $cc (tile ${sz}B looks like stub)"
      continue
    fi
    dest="$PMTILES_DIR/${cc}.pmtiles"
    ln -sfn "$tile" "$dest"
    linked=$((linked + 1))
    echo "sync-nomad-maps: linked $cc → $dest"
  done
  shopt -u nullglob

  if [[ -f "$MAPS_ROOT/countries.json" ]]; then
    cp -f "$MAPS_ROOT/countries.json" "$NOMAD_STORAGE/maps/countries.json"
  fi
  echo "sync-nomad-maps: linked $linked country tile(s)"
}

seed_base_assets
publish_viewer
link_country_tiles
