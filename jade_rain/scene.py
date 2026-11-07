"""Digital rain: depth layers, woven words, and a drifting outline.

The loop is `frames` long. Frame `frames` (the frame a player shows after the
last stored frame) matches frame 0. Stored frames are 0 .. frames-1.

Name phrases are two words from words.txt. They are mixed case, split by the
occasional katakana cell, about 45% brighter than the tail, and they do not
flicker. Source phrases repeat down the column at that same brightness and
do not flicker, so a book stays readable. Other words.txt phrases flicker.
An empty word list is pure rain.
"""

from __future__ import annotations

import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from jade_rain.config import LAYER_SPECS, REFERENCE_WIDTH, WORD_SIZE_STEPS
from jade_rain.logo import mark_heights, outline
from jade_rain.theme import Palette, sample_ramp

RAIN_CHARS = [chr(code) for code in range(0xFF66, 0xFF9E)] + list("0123456789Z:.=*+-<>|¦")
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)
WORD_LAYERS = (1, 2)
NAME_BRIGHTNESS = 1.45
WORD_BRIGHTNESS = 1.3


@dataclass(frozen=True)
class Glyph:
    char: str
    scale: int
    name: bool
    steady: bool = False


@dataclass
class Stream:
    layer: int
    x: int
    cell: int
    rows: int
    tail: int
    period: int
    phase: float
    seed: int
    change: int
    gain: float
    words: dict[int, Glyph]


@dataclass
class LogoMark:
    mask: np.ndarray
    x: int
    travel: int
    phase: float
    color: np.ndarray


@dataclass
class Scene:
    width: int
    height: int
    frames: int
    background: np.ndarray
    ramp: np.ndarray
    glow_color: np.ndarray
    rain: list[tuple[list[np.ndarray], int]]
    word_sprites: list[list[tuple[dict[str, np.ndarray], int]]]
    glows: list[np.ndarray]
    streams: list[Stream]
    logos: list[LogoMark]
    logo_mark_heights: tuple[int, int]
    word_font_px: tuple[int, ...]
    cycles: int = 1
    logo_sprite: tuple[np.ndarray, np.ndarray] | None = None

    def frame(self, t: int) -> np.ndarray:
        width, height = self.width, self.height
        frames = self.frames
        buf = np.zeros((height, width, 3), np.float32)
        cycle = (t / frames) * self.cycles
        for logo in self.logos:
            y = int(round(((logo.phase + cycle) % 1.0) * logo.travel)) - logo.mask.shape[0]
            _blit(buf, logo.mask, logo.x, y, logo.color, width, height)
        ramp = self.ramp
        glow_color = self.glow_color
        for stream in self.streams:
            sprites, pad = self.rain[stream.layer]
            word_sets = self.word_sprites[stream.layer]
            glow = self.glows[stream.layer]
            head = (stream.phase + stream.period * cycle) % stream.period
            head_row = int(head)
            frac = head - head_row
            span = stream.tail + 1
            glow_half = glow.shape[0] // 2
            cell = stream.cell
            origin = stream.x
            for depth in range(span):
                row = head_row - depth
                if row < 0 or row >= stream.rows:
                    continue
                fraction = (depth + frac) / span
                if depth == 0:
                    color = ramp[0] * (0.45 + 0.55 * frac)
                elif depth == 1:
                    color = ramp[0] * (1.0 - frac) + sample_ramp(ramp, fraction) * frac
                else:
                    color = sample_ramp(ramp, fraction) * ((1.0 - fraction) ** 0.6)
                color = color * stream.gain
                step = (t * stream.change + _mix(stream.seed, row)) // frames
                turn = step % stream.change
                glyph = stream.words.get(row)
                steady = glyph is not None and (glyph.name or glyph.steady)
                if glyph is not None and not steady and _mix(stream.seed, row, turn, 3) % 11 == 0:
                    glyph = None
                if glyph is not None and depth > 1:
                    lead = 0.45 if steady else 0.6
                    power = 0.5 if steady else 0.6
                    bright = NAME_BRIGHTNESS if steady else WORD_BRIGHTNESS
                    along = fraction * lead
                    color = sample_ramp(ramp, along) * ((1.0 - along) ** power) * stream.gain * bright
                if glyph is not None:
                    table, word_pad = word_sets[glyph.scale]
                    sprite = table.get(glyph.char)
                    if sprite is None:
                        sprite = sprites[_mix(stream.seed, row, turn) % len(sprites)]
                        _blit(buf, sprite, origin - pad, row * cell - pad, color, width, height)
                    else:
                        _blit(buf, sprite, origin - word_pad, row * cell - word_pad, color, width, height)
                else:
                    sprite = sprites[_mix(stream.seed, row, turn) % len(sprites)]
                    _blit(buf, sprite, origin - pad, row * cell - pad, color, width, height)
                if depth <= 1:
                    weight = (frac if depth == 0 else 1.0 - frac) * 0.4 * stream.gain
                    _blit(
                        buf,
                        glow,
                        origin + cell // 2 - glow_half,
                        row * cell + cell // 2 - glow_half,
                        glow_color * weight,
                        width,
                        height,
                    )
            if self.logo_sprite is not None and stream.seed % 11 == 0:
                mask, sprite_color = self.logo_sprite
                _blit(
                    buf,
                    mask,
                    origin - mask.shape[1] // 2,
                    head_row * cell - mask.shape[0] // 2,
                    sprite_color,
                    width,
                    height,
                )
        if float(self.background.max()) > 140.0:
            # The rain is additive, which only reads on a dark field. On a light
            # field the same mask is ink: stronger glyphs go toward the dark body.
            coverage = np.clip(buf.max(axis=2, keepdims=True) / 18.0, 0.0, 1.0)
            ink = self.ramp[2].reshape(1, 1, 3)
            picture = self.background * (1.0 - coverage) + ink * coverage
            return np.clip(picture, 0, 255).astype(np.uint8)
        return np.clip(buf + self.background, 0, 255).astype(np.uint8)


def rain_characters(glyph_set: str = "katakana", custom: str = "") -> list[str]:
    """Rain glyphs. katakana is the original set, same order."""
    if glyph_set == "latin":
        return list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    if glyph_set == "digits":
        return list("0123456789")
    if glyph_set == "custom":
        seen: list[str] = []
        for char in custom:
            if char.isspace() or char in seen:
                continue
            seen.append(char)
            if len(seen) == 64:
                break
        return seen or RAIN_CHARS
    return RAIN_CHARS


def find_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    try:
        matched = subprocess.check_output(
            ["fc-match", "-f", "%{file}", ":family=Noto Sans CJK JP"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        matched = ""
    lowered = matched.lower()
    if matched and Path(matched).is_file() and ("cjk" in lowered or "noto" in lowered):
        return matched
    raise FileNotFoundError(
        "Noto Sans CJK is required. On Omarchy: omarchy pkg add noto-fonts-cjk"
    )


def build_scene(
    *,
    width: int,
    height: int,
    frames: int,
    palette: Palette,
    words: list[str],
    logo_path: str,
    logo_size: int,
    word_scale: float,
    density: float = 1.0,
    font_path: str | None = None,
    text_phrases: list[str] | None = None,
    text_mode: str = "off",
    text_density: float = 0.35,
    cycles: int = 1,
    glyph_set: str = "katakana",
    glyphs: str = "",
    logo_opacity: float | None = None,
    logo_style: str = "watermark",
    phrase_mix: float | None = None,
) -> Scene:
    if frames < 1:
        raise ValueError("frames must be at least 1")
    if density <= 0:
        raise ValueError("density must be positive")
    if text_mode not in {"off", "mix", "replace"}:
        raise ValueError("text_mode must be off, mix, or replace")
    if isinstance(text_density, bool) or not 0 <= float(text_density) <= 1:
        raise ValueError("text_density must be between 0 and 1")
    if isinstance(cycles, bool) or not 1 <= int(cycles) <= 4:
        raise ValueError("speed must be 1, 2, 3, or 4 cycles per loop")
    if glyph_set not in {"katakana", "latin", "digits", "custom"}:
        raise ValueError("glyph_set must be katakana, latin, digits, or custom")
    if logo_style not in {"watermark", "sprite"}:
        raise ValueError("logo_style must be watermark or sprite")
    if phrase_mix is not None and (isinstance(phrase_mix, bool) or not 0 <= float(phrase_mix) <= 1):
        raise ValueError("mix must be between 0 and 1")
    if logo_opacity is not None and (isinstance(logo_opacity, bool) or not 0 <= float(logo_opacity) <= 1):
        raise ValueError("logo_opacity must be between 0 and 1")
    phrases = list(text_phrases or [])
    phrase_density = float(text_density)
    font_file = font_path or find_font()
    height_scale = height / 1800
    width_scale = width / REFERENCE_WIDTH
    layers: list[tuple[int, float, float, int, tuple[int, int]]] = []
    for size, blur, gain, columns, tails in LAYER_SPECS:
        layers.append(
            (
                max(8, round(size * height_scale)),
                blur * height_scale,
                gain,
                max(1, round(columns * width_scale * density)),
                tails,
            )
        )
    rain_rng = random.Random(7)
    word_rng = random.Random(99)
    text_rng = random.Random(1729)
    streams: list[Stream] = []
    names = [phrase for phrase in words if len(phrase.split()) == 2]
    others = [phrase for phrase in words if len(phrase.split()) != 2]
    name_cursor = 0
    other_cursor = 0
    text_cursor = 0
    for layer_index, (size, _blur, gain, columns, tails) in enumerate(layers):
        cell = max(1, int(size * 1.15))
        rows = height // cell + 2
        for _column in range(columns):
            tail = rain_rng.randint(tails[0], tails[1])
            period = rows + tail + rain_rng.randint(0, rows // 3)
            stream = Stream(
                layer=layer_index,
                x=rain_rng.randrange(-size // 2, max(1, width)),
                cell=cell,
                rows=rows,
                tail=tail,
                period=max(1, period),
                phase=rain_rng.random() * period,
                seed=rain_rng.randrange(1 << 30),
                change=rain_rng.choice((2, 3, 4, 5)),
                gain=gain * rain_rng.uniform(0.7, 1.0),
                words={},
            )
            prob = 0.32 if layer_index == 1 else 0.24
            if phrase_mix is None:
                word_prob = prob
            else:
                word_prob = min(1.0, prob * (float(phrase_mix) / 0.32))
            if text_mode != "replace" and words and layer_index in WORD_LAYERS and word_rng.random() < word_prob:
                _weave(stream, names, others, word_rng, name_cursor, other_cursor)
                if stream.words and _is_name_stream(stream):
                    name_cursor += 1
                else:
                    other_cursor += 1
            if (
                text_mode != "off"
                and phrases
                and phrase_density > 0
                and layer_index in WORD_LAYERS
                and not stream.words
                and text_rng.random() < phrase_density
            ):
                _weave_source(stream, phrases, text_rng, text_cursor)
                text_cursor += 1
            streams.append(stream)
    shown = list(words)
    if text_mode == "replace":
        shown = []
    if text_mode != "off":
        shown.extend(phrases)
    charset = _word_charset(shown)
    characters = rain_characters(glyph_set, glyphs)
    rain: list[tuple[list[np.ndarray], int]] = []
    word_sprites: list[list[tuple[dict[str, np.ndarray], int]]] = []
    glows: list[np.ndarray] = []
    font_px: list[int] = []
    for layer_index, (size, blur, _gain, _columns, _tails) in enumerate(layers):
        sprites, pad = _sprites(font_file, size, blur, characters, mirror=True)
        rain.append((sprites, pad))
        glows.append(_glow(max(2.0, size * 0.45)))
        scales: list[tuple[dict[str, np.ndarray], int]] = []
        if charset and layer_index in WORD_LAYERS:
            for step in WORD_SIZE_STEPS:
                px = max(6, int(size * step * word_scale))
                font_px.append(px)
                table, word_pad = _sprites(font_file, px, blur, sorted(charset), mirror=False)
                scales.append((table, word_pad))
        else:
            scales = [({}, 0), ({}, 0), ({}, 0)]
        word_sprites.append(scales)
    if logo_style == "sprite":
        logos: list[LogoMark] = []
        heights = mark_heights(logo_size, height)
        logo_sprite = _logo_sprite(logo_path, logo_size, height, palette, logo_opacity)
    else:
        logos, heights = _logos(width, height, logo_path, logo_size, palette, streams, logo_opacity)
        logo_sprite = None
    return Scene(
        width=width,
        height=height,
        frames=frames,
        background=palette.background.astype(np.float32),
        ramp=palette.ramp,
        glow_color=palette.glow.astype(np.float32),
        rain=rain,
        word_sprites=word_sprites,
        glows=glows,
        streams=streams,
        logos=logos,
        logo_mark_heights=heights,
        word_font_px=tuple(font_px),
        cycles=int(cycles),
        logo_sprite=logo_sprite,
    )


def _weave(
    stream: Stream,
    names: list[str],
    others: list[str],
    rng: random.Random,
    name_cursor: int,
    other_cursor: int,
) -> None:
    use_name = bool(names) and (not others or rng.random() < 0.66)
    if use_name:
        phrase = names[name_cursor % len(names)]
        sequence = _name_sequence(phrase, rng)
        row = rng.randint(0, 6)
        while row + len(sequence) <= stream.rows:
            for offset, glyph in enumerate(sequence):
                if glyph is not None:
                    stream.words[row + offset] = glyph
            row += len(sequence) + rng.randint(5, 9)
        stream.tail = max(stream.tail, 24)
    elif others or names:
        phrase = others[other_cursor % len(others)] if others else names[name_cursor % len(names)]
        sequence = _plain_sequence(phrase, rng, name=not others and bool(names))
        start = rng.randrange(0, max(1, stream.rows - len(sequence)))
        for offset, glyph in enumerate(sequence):
            if start + offset < stream.rows and glyph is not None:
                stream.words[start + offset] = glyph
        stream.tail = max(stream.tail, len(sequence) + 4)
    else:
        return
    stream.period = max(stream.period, stream.rows + stream.tail + 2)
    stream.phase = stream.phase % stream.period


def _weave_source(stream: Stream, phrases: list[str], rng: random.Random, cursor: int) -> None:
    """Repeat a book phrase down the column, letters kept together."""
    phrase = phrases[cursor % len(phrases)]
    sequence = _source_sequence(phrase, rng)
    if not sequence:
        return
    if len(sequence) >= stream.rows:
        for offset, glyph in enumerate(sequence[: stream.rows]):
            if glyph is not None:
                stream.words[offset] = glyph
    else:
        row = rng.randint(0, min(6, stream.rows - len(sequence)))
        while row + len(sequence) <= stream.rows:
            for offset, glyph in enumerate(sequence):
                if glyph is not None:
                    stream.words[row + offset] = glyph
            row += len(sequence) + rng.randint(3, 6)
    stream.tail = max(stream.tail, min(40, max(len(sequence) + 2, 18)))
    stream.period = max(stream.period, stream.rows + stream.tail + 2)
    stream.phase = stream.phase % stream.period


def _source_sequence(phrase: str, rng: random.Random) -> list[Glyph | None]:
    glyphs: list[Glyph | None] = []
    for char in phrase:
        if char.isspace():
            glyphs.append(None)
            continue
        glyphs.append(Glyph(char, rng.choice((0, 1, 1, 1, 2)), False, True))
    return glyphs


def _is_name_stream(stream: Stream) -> bool:
    return any(glyph.name for glyph in stream.words.values())


def _name_sequence(phrase: str, rng: random.Random) -> list[Glyph | None]:
    variant = rng.choice(_name_variants(phrase))
    glyphs = _letters(variant, rng, name=True)
    if rng.random() < 0.30 and len(glyphs) > 2:
        glyphs.insert(rng.randrange(1, len(glyphs) - 1), None)
    return glyphs


def _plain_sequence(phrase: str, rng: random.Random, *, name: bool) -> list[Glyph | None]:
    scrambled = "".join(ch.upper() if rng.random() < 0.5 else ch.lower() for ch in phrase)
    body = _letters(scrambled, rng, name=name)
    return [None] * rng.randint(2, 4) + body + [None] * rng.randint(2, 4)


def _letters(text: str, rng: random.Random, *, name: bool) -> list[Glyph | None]:
    glyphs: list[Glyph | None] = []
    for char in text:
        if char.isspace():
            glyphs.append(None)
            continue
        scale = rng.choice((0, 1, 1, 1, 2))
        glyphs.append(Glyph(char, scale, name))
        if not name and rng.random() < 0.35:
            glyphs.extend([None] * rng.randint(1, 2))
    return glyphs


def _name_variants(phrase: str) -> list[str]:
    first, second = phrase.split()
    variants = [
        f"{first} {second}",
        f"{first.capitalize()} {second.capitalize()}",
        f"{first.upper()} {second.upper()}",
        f"{first.lower()} {second.lower()}",
        f"{first.capitalize()} {second.lower()}",
        f"{first.lower()} {second.capitalize()}",
        f"{first.upper()} {second.capitalize()}",
    ]
    unique: list[str] = []
    for variant in variants:
        if variant not in unique:
            unique.append(variant)
    return unique


def _word_charset(words: list[str]) -> set[str]:
    chars: set[str] = set()
    for phrase in words:
        for char in phrase:
            if char.isspace():
                continue
            chars.add(char)
            chars.add(char.upper())
            chars.add(char.lower())
    return chars


def _logo_opacity(logo_opacity: float | None) -> tuple[float, float]:
    if logo_opacity is None or abs(float(logo_opacity) - 0.33) < 1e-9:
        return 0.33, 0.28
    near = float(logo_opacity)
    return near, near * (0.28 / 0.33)


def _logo_sprite(
    logo_path: str,
    logo_size: int,
    height: int,
    palette: Palette,
    logo_opacity: float | None,
) -> tuple[np.ndarray, np.ndarray] | None:
    if not logo_path:
        return None
    path = Path(logo_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"logo not found: {path}")
    near, _far = _logo_opacity(logo_opacity)
    mark = outline(path, max(12, round(logo_size * height / 1800 * 0.45)))
    return mark, palette.logo * near


def _logos(
    width: int,
    height: int,
    logo_path: str,
    logo_size: int,
    palette: Palette,
    streams: list[Stream],
    logo_opacity: float | None = None,
) -> tuple[list[LogoMark], tuple[int, int]]:
    heights = mark_heights(logo_size, height)
    if not logo_path:
        return [], heights
    path = Path(logo_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"logo not found: {path}")
    taken = [stream.x for stream in streams if any(glyph.name for glyph in stream.words.values())]
    logos: list[LogoMark] = []
    # Two passes per loop, half a cycle apart. Opacities match the desktop render.
    near_opacity, far_opacity = _logo_opacity(logo_opacity)
    placements = (
        (heights[0], 500, 1300, 0.0, near_opacity),
        (heights[1], 1800, 2600, 0.5, far_opacity),
    )
    for mark_h, left, right, phase, opacity in placements:
        mask = outline(path, mark_h)
        lo = int(left * width / REFERENCE_WIDTH)
        hi = int(right * width / REFERENCE_WIDTH)
        x = _free_x(mask.shape[1], lo, hi, width, taken)
        travel = height + mask.shape[0] + int(1100 * height / 1800)
        color = palette.logo * opacity
        logos.append(LogoMark(mask, x, max(1, travel), phase, color))
    return logos, heights


def _free_x(mark_w: int, lo: int, hi: int, width: int, taken: list[int]) -> int:
    lo = max(0, min(lo, width - 1))
    hi = max(lo + 1, min(hi, width))
    step = max(4, round(20 * width / REFERENCE_WIDTH))
    for x in range(lo, hi, step):
        if all(not (x - 60 < column < x + mark_w + 60) for column in taken):
            return x
    return lo


def _sprites(
    font_path: str,
    size: int,
    blur: float,
    chars: list[str],
    *,
    mirror: bool,
) -> tuple[dict[str, np.ndarray] | list[np.ndarray], int]:
    font = ImageFont.truetype(font_path, max(6, size), index=0)
    pad = int(max(0.0, blur) * 3) + 4
    canvas_w = size + 2 * pad
    canvas_h = int(size * 1.25) + 2 * pad
    images: list[np.ndarray] = []
    mapping: dict[str, np.ndarray] = {}
    for char in chars:
        image = Image.new("L", (canvas_w, canvas_h), 0)
        ImageDraw.Draw(image).text((pad + size * 0.05, pad), char, 255, font=font)
        if mirror:
            image = ImageOps.mirror(image)
        if blur >= 0.4:
            image = image.filter(ImageFilter.GaussianBlur(blur))
        array = np.asarray(image, np.float32) / 255.0
        images.append(array)
        mapping[char] = array
    if mirror:
        return images, pad
    return mapping, pad


def _glow(radius: float) -> np.ndarray:
    limit = max(1, int(round(radius)))
    span = 2 * limit
    y, x = np.mgrid[-span : span + 1, -span : span + 1]
    return np.exp(-(x * x + y * y) / (2 * radius * radius)).astype(np.float32)


def _blit(
    buf: np.ndarray,
    mask: np.ndarray,
    x: int,
    y: int,
    color: np.ndarray,
    width: int,
    height: int,
) -> None:
    mask_h, mask_w = mask.shape
    x0 = x if x > 0 else 0
    y0 = y if y > 0 else 0
    x1 = x + mask_w
    y1 = y + mask_h
    if x1 > width:
        x1 = width
    if y1 > height:
        y1 = height
    if x0 >= x1 or y0 >= y1:
        return
    buf[y0:y1, x0:x1] += mask[y0 - y : y1 - y, x0 - x : x1 - x, None] * color


def _mix(*parts: int) -> int:
    value = 0x811C9DC5
    for part in parts:
        value ^= part & 0xFFFFFFFF
        value = (value * 0x01000193) & 0xFFFFFFFF
    return value
