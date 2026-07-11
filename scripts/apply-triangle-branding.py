#!/usr/bin/env python3
"""Derive Atlas Calamares branding assets from the glowing-triangle master art."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_CANDIDATES = [
    Path(
        "/mnt/c/Users/Kaal/.cursor/projects/c-Users-Kaal-Desktop-Atlas-OS/assets/"
        "c__Users_Kaal_AppData_Roaming_Cursor_User_workspaceStorage_empty-window_images_"
        "IMG_8601-cd55cf99-d285-430f-af63-555c1c020ca7.png"
    ),
    Path(
        r"C:\Users\Kaal\.cursor\projects\c-Users-Kaal-Desktop-Atlas-OS\assets"
    ),
    ROOT.parent / "assets",
]

SRC = None
for cand in SRC_CANDIDATES:
    if cand.is_file() and cand.suffix.lower() == ".png":
        SRC = cand
        break
    if cand.is_dir():
        hits = sorted(cand.glob("*IMG_8601*.png")) + sorted(cand.glob("*8601*.png"))
        if hits:
            SRC = hits[0]
            break
if SRC is None:
    raise SystemExit("source triangle art not found under assets/")

OUT_BRAND = ROOT / "calamares" / "branding" / "atlas"
OUT_MASTER = ROOT / "config" / "includes.chroot" / "usr" / "share" / "atlas" / "branding"
OUT_PIX = ROOT / "config" / "includes.chroot" / "usr" / "share" / "pixmaps"
OUT_WALL = ROOT / "config" / "includes.chroot" / "usr" / "share" / "backgrounds" / "atlas"
OUT_PLASMA = (
    ROOT
    / "config"
    / "includes.chroot"
    / "usr"
    / "share"
    / "wallpapers"
    / "Atlas"
    / "contents"
    / "images"
)

for d in (OUT_BRAND, OUT_MASTER, OUT_PIX, OUT_WALL, OUT_PLASMA):
    d.mkdir(parents=True, exist_ok=True)


def content_bbox(im: Image.Image, threshold: int = 18) -> tuple[int, int, int, int]:
    """Bounding box of non-black pixels (glow + stroke)."""
    gray = im.convert("L")
    mask = gray.point(lambda p: 255 if p > threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return (0, 0, im.width, im.height)
    return bbox


def square_crop(im: Image.Image, padding_ratio: float = 0.22) -> Image.Image:
    """Crop to a square around the glowing triangle with black padding."""
    left, top, right, bottom = content_bbox(im)
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    side = max(right - left, bottom - top)
    side = int(side * (1 + padding_ratio))
    half = side / 2
    box = (
        int(cx - half),
        int(cy - half),
        int(cx + half),
        int(cy + half),
    )
    # Paste onto black canvas so out-of-bounds stays black
    canvas = Image.new("RGB", (side, side), (0, 0, 0))
    region = im.convert("RGB")
    # Compute paste offset for the intersection
    src_box = (
        max(0, box[0]),
        max(0, box[1]),
        min(im.width, box[2]),
        min(im.height, box[3]),
    )
    paste_at = (src_box[0] - box[0], src_box[1] - box[1])
    canvas.paste(region.crop(src_box), paste_at)
    return canvas


def fit_canvas(im: Image.Image, size: tuple[int, int], scale: float = 0.62) -> Image.Image:
    """Place logo on a black canvas of exact size, scaled to scale*min dimension."""
    w, h = size
    canvas = Image.new("RGB", (w, h), (0, 0, 0))
    sq = square_crop(im)
    target = int(min(w, h) * scale)
    sq = sq.resize((target, target), Image.Resampling.LANCZOS)
    canvas.paste(sq, ((w - target) // 2, (h - target) // 2))
    return canvas


def main() -> None:
    master = Image.open(SRC).convert("RGB")
    # Keep master copy
    master.save(OUT_MASTER / "triangle-glow-master.png", optimize=True)
    master.save(OUT_BRAND / "triangle-glow-master.png", optimize=True)

    logo = square_crop(master).resize((320, 320), Image.Resampling.LANCZOS)
    logo.save(OUT_BRAND / "logo.png", optimize=True)
    logo.resize((256, 256), Image.Resampling.LANCZOS).save(OUT_PIX / "atlas.png", optimize=True)
    logo.resize((256, 256), Image.Resampling.LANCZOS).save(OUT_MASTER / "logo.png", optimize=True)

    welcome = fit_canvas(master, (640, 300), scale=0.78)
    welcome.save(OUT_BRAND / "welcome.png", optimize=True)

    # Optional banner strip
    banner = fit_canvas(master, (920, 128), scale=0.85)
    banner.save(OUT_BRAND / "banner.png", optimize=True)

    # Desktop / live wallpaper: keep the original composition (widescreen triangle)
    import shutil

    wall_original = OUT_WALL / "atlas-wallpaper.png"
    shutil.copy2(SRC, wall_original)
    # Also write common display sizes for lighter live ISOs / HiDPI
    master.resize((1920, 1080), Image.Resampling.LANCZOS).save(
        OUT_WALL / "atlas-wallpaper-1080p.png", optimize=True
    )
    master.resize((2560, 1440), Image.Resampling.LANCZOS).save(
        OUT_WALL / "atlas-wallpaper-1440p.png", optimize=True
    )
    # Compatibility alias used by older hooks
    shutil.copy2(wall_original, OUT_WALL / "atlas-default.png")

    # Plasma wallpaper plugin images
    master.resize((1920, 1080), Image.Resampling.LANCZOS).save(
        OUT_PLASMA / "1920x1080.png", optimize=True
    )
    master.resize((2560, 1440), Image.Resampling.LANCZOS).save(
        OUT_PLASMA / "2560x1440.png", optimize=True
    )
    shutil.copy2(wall_original, OUT_PLASMA / "1024x576.png")

    # Icon for slideshow / about
    logo.resize((160, 160), Image.Resampling.LANCZOS).save(OUT_BRAND / "productIcon.png", optimize=True)

    print("Branding assets written from", SRC)
    for p in sorted(OUT_BRAND.glob("*.png")):
        im = Image.open(p)
        print(f"  {p.name}: {im.size[0]}x{im.size[1]}")
    for p in sorted(OUT_WALL.glob("*.png")):
        im = Image.open(p)
        print(f"  wallpaper/{p.name}: {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
