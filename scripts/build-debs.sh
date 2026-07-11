#!/usr/bin/env bash
# Build Atlas .deb packages. Prefers dpkg-buildpackage; falls back to simple ar packs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist/debs}"
mkdir -p "$OUT"

build_simple_deb() {
  local name="$1"
  local version="0.1.0-1"
  local pkgdir="$ROOT/packages/$name"
  local stage
  stage="$(mktemp -d)"
  local control_dir="$stage/DEBIAN"
  mkdir -p "$control_dir"

  # Copy payload
  if [[ -d "$pkgdir/usr" ]]; then
    mkdir -p "$stage/usr"
    cp -a "$pkgdir/usr/." "$stage/usr/"
  fi
  if [[ -d "$pkgdir/lib" ]]; then
    mkdir -p "$stage/lib"
    cp -a "$pkgdir/lib/." "$stage/lib/"
  fi
  if [[ -d "$pkgdir/etc" ]]; then
    mkdir -p "$stage/etc"
    cp -a "$pkgdir/etc/." "$stage/etc/"
  fi

  # Python libs without usr/ tree yet — skip empty packages
  if [[ ! -d "$stage/usr" && ! -d "$stage/lib" && "$name" != "atlas-branding" ]]; then
    echo "SKIP empty package tree: $name"
    rm -rf "$stage"
    return 0
  fi

  # Branding special-case: include calamares tree
  if [[ "$name" == "atlas-branding" ]]; then
    mkdir -p "$stage/usr/share/atlas"
    cp -a "$ROOT/calamares" "$stage/usr/share/atlas/"
    mkdir -p "$stage/usr/share/pixmaps" "$stage/usr/share/atlas/branding"
    if [[ -f "$ROOT/config/includes.chroot/usr/share/pixmaps/atlas.png" ]]; then
      cp "$ROOT/config/includes.chroot/usr/share/pixmaps/atlas.png" "$stage/usr/share/pixmaps/" || true
    fi
  fi

  local size
  size="$(du -sk "$stage" | awk '{print $1}')"
  local depends="xdg-utils"
  case "$name" in
    atlas-branding) depends="" ;;
    atlas-shell) depends="xdg-utils, atlas-branding" ;;
    atlas-firstboot) depends="openssl" ;;
  esac

  cat > "$control_dir/control" <<EOF
Package: $name
Version: $version
Section: misc
Priority: optional
Architecture: all
Maintainer: Atlas OS Builders <builders@atlas-os.local>
Installed-Size: $size
Depends: $depends
Description: Atlas OS package $name
EOF

  # Fix permissions for scripts
  find "$stage" -type f -name '*.sh' -exec chmod 755 {} \;
  find "$stage/usr/bin" -type f -exec chmod 755 {} \; 2>/dev/null || true

  local deb="$OUT/${name}_${version}_all.deb"
  if command -v dpkg-deb >/dev/null; then
    dpkg-deb --root-owner-group --build "$stage" "$deb"
  else
    # Minimal .deb via ar
    local tmp
    tmp="$(mktemp -d)"
    (cd "$stage" && tar --owner=0 --group=0 -czf "$tmp/data.tar.gz" .)
    (
      cd "$control_dir"
      tar --owner=0 --group=0 -czf "$tmp/control.tar.gz" .
    )
    echo "2.0" > "$tmp/debian-binary"
    (cd "$tmp" && ar r "$deb" debian-binary control.tar.gz data.tar.gz)
    rm -rf "$tmp"
  fi
  rm -rf "$stage"
  echo "Built $deb"
}

# Ensure branding placeholders exist
bash "$ROOT/scripts/generate-branding-placeholders.sh" || true

PACKAGES=(
  atlas-branding
  atlas-shell
  atlas-firstboot
  atlas-system-daemon
  atlas-auth
  atlas-policy-gateway
  atlas-agent-runtime
  atlas-model-manager
  atlas-knowledge
  atlas-content-manager
  atlas-backup
  atlas-updater
  atlas-command-centre
)

for p in "${PACKAGES[@]}"; do
  if [[ -d "$ROOT/packages/$p" ]]; then
    build_simple_deb "$p"
  fi
done

echo "All packages in $OUT"
ls -la "$OUT"
