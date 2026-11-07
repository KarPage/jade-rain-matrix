"""Accent ramps and the dark field behind the rain.

Head, body, tail, and glow stay on the accent's hue. A light theme background
is pulled down so the glyphs still read; the field is a wallpaper, not a wash.
"""

from __future__ import annotations

import colorsys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FALLBACK_ACCENT = "#3fe0a4"
FALLBACK_BACKGROUND = (13.0, 2.0, 4.0)

# primary, highlight, background. "theme" is not listed: it follows colors.toml.
COLOR_PRESETS: dict[str, tuple[str, str, str]] = {
    "jade": ("#3fe0a4", "#e9fff6", "#0d0204"),
    "matrix": ("#39ff14", "#d8ffd0", "#031205"),
    "ink": ("#7aa2f7", "#c0caf5", "#0e0e14"),
    "paper": ("#1b4d38", "#0e2e22", "#f3efe4"),
}

# Preferred colors.toml keys, then the legacy names Omarchy still accepts.
_BACKGROUND_KEYS = (
    "darker_background",
    "darker_bg",
    "dark_background",
    "dark_bg",
    "background",
    "bg",
)
_ACCENT_KEYS = ("accent", "color4", "blue")


@dataclass(frozen=True)
class Palette:
    accent_hex: str
    accent_source: str
    background_source: str
    ramp: np.ndarray  # (5, 3) float32, 0..255
    glow: np.ndarray  # (3,) float32, the bright stop
    logo: np.ndarray  # (3,) float32, the body stop
    background: np.ndarray  # (3,) float32


def parse_hex(value: str) -> np.ndarray:
    text = value.strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in text):
        raise ValueError(f"not a hex color: {value!r}")
    channels = [int(text[i : i + 2], 16) for i in (0, 2, 4)]
    return np.array(channels, np.float32)


def format_hex(rgb: np.ndarray) -> str:
    channels = [int(round(float(channel))) for channel in rgb]
    clamped = [min(255, max(0, channel)) for channel in channels]
    return "#{:02x}{:02x}{:02x}".format(*clamped)


def _hsv(h: float, s: float, v: float) -> np.ndarray:
    red, green, blue = colorsys.hsv_to_rgb(h % 1.0, min(1.0, max(0.0, s)), min(1.0, max(0.0, v)))
    return np.array((red * 255.0, green * 255.0, blue * 255.0), np.float32)


def ramp_from_accent(accent: np.ndarray) -> np.ndarray:
    """Five stops: head, bright, body, tail, end. Hue follows the accent."""
    red, green, blue = (float(channel) / 255.0 for channel in accent)
    hue, sat, val = colorsys.rgb_to_hsv(red, green, blue)
    body_v = min(1.0, max(val, 0.78))
    stops = (
        _hsv(hue, sat * 0.06, 1.0),
        _hsv(hue, min(1.0, sat * 0.75 + 0.05), 1.0),
        _hsv(hue, sat, body_v),
        _hsv(hue, min(1.0, sat * 1.05), max(0.20, val * 0.55)),
        _hsv(hue, sat * 0.9, max(0.05, val * 0.18)),
    )
    return np.stack(stops).astype(np.float32)


def sample_ramp(ramp: np.ndarray, fraction: float) -> np.ndarray:
    scaled = fraction * (len(ramp) - 1)
    index = min(int(scaled), len(ramp) - 2)
    blend = scaled - index
    return ramp[index] * (1.0 - blend) + ramp[index + 1] * blend


def _load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a color table")
    return data


def _string(table: dict[str, object], key: str) -> str | None:
    value = table.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_theme_colors(path: Path | None) -> tuple[str | None, str | None]:
    """Return (accent, background) hex strings from an Omarchy colors.toml."""
    if path is None or not path.is_file():
        return None, None
    table = _load_toml(path)
    accent = None
    for key in _ACCENT_KEYS:
        accent = _string(table, key)
        if accent:
            break
    background = None
    for key in _BACKGROUND_KEYS:
        background = _string(table, key)
        if background:
            break
    return accent, background


def _field(theme_background: np.ndarray, accent: np.ndarray) -> np.ndarray:
    field = theme_background.astype(np.float32)
    peak = float(field.max())
    if peak > 48.0:
        field = field * (32.0 / peak)
    return field * 0.97 + accent * 0.03


def _dark_ramp(accent: np.ndarray) -> np.ndarray:
    """Glyphs that stay readable on a light field. Hue still follows the accent."""
    red, green, blue = (float(channel) / 255.0 for channel in accent)
    hue, sat, _val = colorsys.rgb_to_hsv(red, green, blue)
    sat = max(sat, 0.35)
    stops = (
        _hsv(hue, sat * 0.12, 0.20),
        _hsv(hue, sat * 0.40, 0.30),
        _hsv(hue, sat, 0.36),
        _hsv(hue, sat, 0.22),
        _hsv(hue, sat * 0.75, 0.12),
    )
    return np.stack(stops).astype(np.float32)


def resolve_palette(
    *,
    accent_override: str,
    accent_source_label: str,
    background_override: str,
    theme_file: Path | None,
    highlight: str = "",
    allow_light: bool = False,
) -> Palette:
    theme_accent, theme_background = read_theme_colors(theme_file)
    if accent_override:
        accent = parse_hex(accent_override)
        accent_source = accent_source_label or "override"
    elif theme_accent:
        accent = parse_hex(theme_accent)
        accent_source = str(theme_file)
    else:
        accent = parse_hex(FALLBACK_ACCENT)
        accent_source = "fallback"
    ramp = ramp_from_accent(accent)
    if background_override:
        background = parse_hex(background_override)
        background_source = "override"
    elif theme_background:
        parsed = parse_hex(theme_background)
        if allow_light:
            background = parsed
        else:
            background = _field(parsed, ramp[2])
        background_source = str(theme_file)
    else:
        background = np.array(FALLBACK_BACKGROUND, np.float32)
        background_source = "fallback"
    if allow_light and float(background.max()) > 140.0:
        ramp = _dark_ramp(accent)
    if highlight.strip():
        head = parse_hex(highlight)
        ramp = ramp.copy()
        ramp[0] = head
        glow = head
    else:
        glow = ramp[1].copy()
    return Palette(
        accent_hex=format_hex(accent),
        accent_source=accent_source,
        background_source=background_source,
        ramp=ramp,
        glow=glow,
        logo=ramp[2].copy(),
        background=background.astype(np.float32),
    )
