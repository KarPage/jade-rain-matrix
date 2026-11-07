"""Thin logo outline from a PNG mark.

The outline follows the opaque mark. It never strokes the image rectangle.
A file with a real alpha channel is traced from that alpha, cropped to the
mark first. RGB is ignored: a white logo often stores white in the transparent
pixels, and a luminance read of those pixels would be a solid box.

A PNG with no transparency, or with a fully opaque alpha, is a light mark on
a dark field. Pixels at or above half luminance become the mark. A dark mark
on a white field is not detected.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

from jade_rain.config import state_dir

# Far outline relative to logo_size. 250 * 0.84 = 210 at the reference frame.
FAR_RATIO = 210 / 250
REFERENCE_HEIGHT = 1800


def mark_heights(logo_size: int, frame_height: int) -> tuple[int, int]:
    """Near and far outline heights for this frame, in pixels."""
    scale = frame_height / REFERENCE_HEIGHT
    near = max(8, round(logo_size * scale))
    far = max(8, round(logo_size * FAR_RATIO * scale))
    return near, far


def mark_mask(path: Path) -> tuple[Image.Image, str]:
    """Binary mask of the mark, cropped to the mark. Second value is the source."""
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened)
        rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    low, high = alpha.getextrema()
    if low < 250 and high > 8:
        source = "alpha"
        raw = alpha
    else:
        source = "luminance"
        raw = rgba.convert("L")
    mask = raw.point(lambda value: 255 if value >= 128 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        raise ValueError(f"no mark in {path} ({source})")
    return mask.crop(bbox), source


def outline(path: Path, height: int) -> np.ndarray:
    """Soft 1-pixel edge of the mark, shaped (height+pad, width+pad), float 0..1."""
    mask, _source = mark_mask(path)
    if mask.height < 1 or mask.width < 1:
        raise ValueError(f"empty mark in {path}")
    width = max(1, round(mask.width * height / mask.height))
    resized = mask.resize((width, height), Image.Resampling.LANCZOS)
    binary = resized.point(lambda value: 255 if value > 128 else 0)
    padded = ImageOps.expand(binary, border=6, fill=0)
    edge = ImageChops.subtract(padded.filter(ImageFilter.MaxFilter(3)), padded.filter(ImageFilter.MinFilter(3)))
    soft = edge.filter(ImageFilter.GaussianBlur(0.9))
    array = np.asarray(soft, np.float32) / 255.0
    array[array < 0.04] = 0
    return array


def prepare_logo(path: str) -> str:
    """Return a PNG path. SVG is rasterized with a tool already on the machine."""
    if not path:
        return ""
    file = Path(path).expanduser()
    if not file.is_file() or file.is_symlink():
        raise FileNotFoundError(f"logo not found: {file}")
    if file.stat().st_size > 8_000_000:
        raise ValueError("logo is larger than 8 MB")
    suffix = file.suffix.lower()
    if suffix == ".png":
        return str(file)
    if suffix == ".svg":
        return str(_rasterize_svg(file))
    raise ValueError("logo must be a PNG or SVG")


def _rasterize_svg(path: Path) -> Path:
    cache = state_dir() / "logo-cache"
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / f"{path.stem[:40]}.png"
    rsvg = shutil.which("rsvg-convert")
    magick = shutil.which("magick") or shutil.which("convert")
    if rsvg:
        command = [rsvg, "-h", "512", "-o", str(dest), str(path)]
    elif magick:
        command = [magick, "-background", "none", str(path), str(dest)]
    else:
        raise ValueError(
            "SVG logos need rsvg-convert or ImageMagick. Omarchy ships ImageMagick. Use a PNG until one of those is on PATH."
        )
    subprocess.run(command, check=True, timeout=20, stdin=subprocess.DEVNULL)
    if not dest.is_file():
        raise RuntimeError("SVG rasterize produced no PNG")
    return dest
