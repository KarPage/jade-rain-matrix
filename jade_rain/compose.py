"""Build a scene from resolved settings. The editor and the renderer share this."""

from __future__ import annotations

from pathlib import Path

from jade_rain.config import Settings
from jade_rain.logo import prepare_logo
from jade_rain.scene import Scene, build_scene
from jade_rain.theme import parse_hex, resolve_palette


def allow_light_field(settings: Settings, background: str) -> bool:
    if settings.display_mode == "light" or settings.color_preset == "paper":
        return True
    if not background.strip():
        return False
    try:
        return float(parse_hex(background).max()) > 140.0
    except ValueError:
        return False


def scene_from_settings(
    settings: Settings,
    *,
    width: int,
    height: int,
    frames: int,
    words: list[str],
    source_phrases: list[str],
    theme_file: Path | None,
    accent: str = "",
    background: str = "",
    density: float | None = None,
) -> Scene:
    chosen_accent = accent if accent else settings.accent
    chosen_background = background if background else settings.background_color
    palette = resolve_palette(
        accent_override=chosen_accent,
        accent_source_label="cli" if accent else ("config" if chosen_accent else ""),
        background_override=chosen_background,
        theme_file=theme_file,
        highlight=settings.highlight,
        allow_light=allow_light_field(settings, chosen_background),
    )
    logo = prepare_logo(settings.logo) if settings.logo else ""
    return build_scene(
        width=width,
        height=height,
        frames=frames,
        palette=palette,
        words=words,
        logo_path=logo,
        logo_size=settings.logo_size,
        word_scale=settings.word_scale,
        density=settings.density if density is None else density,
        text_phrases=source_phrases,
        text_mode=settings.text_mode,
        text_density=settings.text_density,
        cycles=settings.speed,
        glyph_set=settings.glyph_set,
        glyphs=settings.glyphs,
        logo_opacity=settings.logo_opacity,
        logo_style=settings.logo_style,
        phrase_mix=settings.phrase_mix,
    )
