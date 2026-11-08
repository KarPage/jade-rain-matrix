"""User settings, words, and preset sizes."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jade_rain.theme import COLOR_PRESETS, parse_hex

REFERENCE_WIDTH = 2880
REFERENCE_HEIGHT = 1800

# size, blur, gain, columns, (tail min, tail max). Tuned at 2880x1800.
LAYER_SPECS = (
    (22, 2.0, 0.45, 110, (16, 30)),
    (34, 0.9, 0.85, 90, (16, 28)),
    (58, 0.0, 1.15, 50, (12, 22)),
    (150, 14.0, 0.5, 10, (2, 4)),
)

# Word glyphs use these fractions of the rain glyph, then word_scale.
WORD_SIZE_STEPS = (0.72, 0.85, 0.92)
DEFAULT_WORD_SCALE = 0.86
DEFAULT_LOGO_SIZE = 250
DEFAULT_TEXT_MODE = "off"
DEFAULT_TEXT_DENSITY = 0.35
TEXT_MODES = ("off", "mix", "replace")
DISPLAY_MODES = ("live", "still", "light", "screensaver")
GLYPH_SETS = ("katakana", "latin", "digits", "custom")
LOGO_STYLES = ("watermark", "sprite")
COLOR_PRESET_NAMES = ("theme", "jade", "matrix", "ink", "paper")
CLASSIC_PHRASE_MIX = 0.32

PRESET_NAMES = ("full", "laptop", "draft")
_TEXT_MODE_LINE = re.compile(r"^[ \t]*text_mode\s*=.*$", re.MULTILINE)


@dataclass(frozen=True)
class Preset:
    name: str
    width: int
    height: int
    fps: int
    frames: int
    x264_preset: str
    crf: int


PRESETS: dict[str, Preset] = {
    "full": Preset("full", 2880, 1800, 24, 640, "slow", 20),
    "laptop": Preset("laptop", 1920, 1200, 24, 360, "medium", 20),
    "draft": Preset("draft", 960, 600, 12, 72, "veryfast", 23),
}


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def package_words() -> Path:
    return package_root() / "share" / "words.txt"


def package_logo() -> Path:
    return package_root() / "assets" / "kp-logo-white.png"


CONFIG_DIR_NAME = "jade-rain-matrix"
LEGACY_CONFIG_DIR_NAME = "jade-rain"
PRIMARY_COMMAND = "jade-rain-matrix"
ALIAS_COMMAND = "jade-rain"


def cli_path() -> Path:
    return package_root() / "bin" / PRIMARY_COMMAND


def source_file() -> Path:
    return config_dir() / "source.txt"


def _config_root() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return Path(base) if base else Path.home() / ".config"


def _config_has_files(path: Path) -> bool:
    return any((path / name).is_file() for name in ("config.toml", "words.txt", "source.txt"))


def config_dir() -> Path:
    """New config dir, or the old one when the new one has no files yet.

    The old directory is never removed. A later jade-rain-matrix directory
    wins once it contains config, words, or source text.
    """
    root = _config_root()
    current = root / CONFIG_DIR_NAME
    legacy = root / LEGACY_CONFIG_DIR_NAME
    if _config_has_files(current):
        return current
    if _config_has_files(legacy):
        return legacy
    return current


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "jade-rain"


def omarchy_config() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "omarchy"


def omarchy_state() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "omarchy"


@dataclass(frozen=True)
class Settings:
    preset: str
    accent: str
    logo: str
    logo_size: int
    word_scale: float
    words_file: Path
    workers: int
    text_mode: str
    text_density: float
    config_path: Path | None
    profile: str = "default"
    display_mode: str = "live"
    color_preset: str = "theme"
    primary: str = ""
    highlight: str = ""
    background_color: str = ""
    density: float = 1.0
    speed: int = 1
    glyph_set: str = "katakana"
    glyphs: str = ""
    logo_opacity: float | None = None
    logo_style: str = "watermark"
    phrases: str = ""
    phrase_mix: float | None = None
    mode_overrides: dict[str, dict[str, object]] = field(default_factory=dict)


def _table(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a table")
    return data


def _optional_str(table: dict[str, object], key: str) -> str | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def load_settings() -> Settings:
    path = config_dir() / "config.toml"
    words_default = config_dir() / "words.txt"
    if not path.is_file():
        words = words_default if words_default.is_file() else package_words()
        logo = str(package_logo()) if package_logo().is_file() else ""
        return Settings(
            preset="full",
            accent="",
            logo=logo,
            logo_size=DEFAULT_LOGO_SIZE,
            word_scale=DEFAULT_WORD_SCALE,
            words_file=words,
            workers=0,
            text_mode="mix" if source_file().is_file() and not source_file().is_symlink() else "off",
            text_density=DEFAULT_TEXT_DENSITY,
            config_path=None,
        )
    table = _table(path)
    if isinstance(table.get("profiles"), dict):
        return _settings_from_document(_document_from_table(path, table))
    preset = (_optional_str(table, "preset") or "full").lower()
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESET_NAMES)}")
    accent = _optional_str(table, "accent") or ""
    logo = _optional_str(table, "logo") if "logo" in table else ""
    if logo is None:
        logo = ""
    logo_size = table.get("logo_size", DEFAULT_LOGO_SIZE)
    word_scale = table.get("word_scale", DEFAULT_WORD_SCALE)
    workers = table.get("workers", 0)
    if isinstance(logo_size, bool) or not isinstance(logo_size, int):
        raise ValueError("logo_size must be an integer")
    if isinstance(word_scale, bool) or not isinstance(word_scale, (int, float)):
        raise ValueError("word_scale must be a number")
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise ValueError("workers must be an integer")
    if logo_size < 8:
        raise ValueError("logo_size must be at least 8")
    if not 0.05 <= float(word_scale) <= 2.0:
        raise ValueError("word_scale must be between 0.05 and 2")
    if workers < 0:
        raise ValueError("workers must be 0 (auto) or a positive count")
    text_mode = _text_mode(_optional_str(table, "text_mode"))
    text_density = _text_density(table.get("text_density", DEFAULT_TEXT_DENSITY))
    words_value = _optional_str(table, "words")
    if words_value:
        words_file = Path(words_value).expanduser()
    elif words_default.is_file():
        words_file = words_default
    else:
        words_file = package_words()
    return Settings(
        preset=preset,
        accent=accent,
        logo=logo,
        logo_size=logo_size,
        word_scale=float(word_scale),
        words_file=words_file,
        workers=workers,
        text_mode=text_mode,
        text_density=text_density,
        config_path=path,
    )


def _text_mode(value: str | None) -> str:
    mode = (value or DEFAULT_TEXT_MODE).lower()
    if mode not in TEXT_MODES:
        raise ValueError("text_mode must be off, mix, or replace")
    return mode


def _text_density(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("text_density must be a number from 0 to 1")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError("text_density must be a number from 0 to 1")
    return number


@dataclass
class Profile:
    name: str
    values: dict[str, object]
    modes: dict[str, dict[str, object]]


@dataclass
class ConfigDocument:
    active: str
    mode: str
    profiles: dict[str, Profile]
    path: Path | None


def factory_values(logo: str = "") -> dict[str, object]:
    return {
        "preset": "full",
        "color_preset": "theme",
        "primary": "",
        "highlight": "",
        "background": "",
        "logo": logo,
        "logo_size": DEFAULT_LOGO_SIZE,
        "logo_opacity": 0.33,
        "logo_style": "watermark",
        "word_scale": DEFAULT_WORD_SCALE,
        "text_mode": DEFAULT_TEXT_MODE,
        "text_density": DEFAULT_TEXT_DENSITY,
        "mix": CLASSIC_PHRASE_MIX,
        "density": 1.0,
        "speed": 1,
        "glyph_set": "katakana",
        "glyphs": "",
        "phrases": "",
        "workers": 0,
    }


def factory_modes() -> dict[str, dict[str, object]]:
    return {
        "live": {},
        "still": {},
        "light": {
            "color_preset": "paper",
            "primary": "#1b4d38",
            "highlight": "#0e2e22",
            "background": "#f3efe4",
            "density": 0.65,
            "speed": 1,
            "mix": 0.2,
        },
        "screensaver": {
            "color_preset": "matrix",
            "density": 0.85,
            "speed": 1,
        },
    }


def _display_mode(mode: str) -> str:
    if mode not in DISPLAY_MODES:
        raise ValueError("mode must be live, still, light, or screensaver")
    return mode


def _profile_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", name):
        raise ValueError("profile name must be letters, numbers, dash, or underscore")
    return name


def _string_value(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    return default


def _merge_values(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        if value is None:
            continue
        # A missing key inherits; an explicit empty string clears a mode field.
        # Otherwise selecting theme colors or removing inherited words cannot work.
        merged[key] = value
    return merged


def _document_from_table(path: Path, table: dict[str, object]) -> ConfigDocument:
    raw_profiles = table.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ValueError("profiles must be a table of named profiles")
    profiles: dict[str, Profile] = {}
    for name, body in raw_profiles.items():
        checked = _profile_name(str(name))
        if not isinstance(body, dict):
            raise ValueError(f"profile {checked} must be a table")
        modes_raw = body.get("modes")
        values = {key: value for key, value in body.items() if key != "modes"}
        modes: dict[str, dict[str, object]] = {mode: {} for mode in DISPLAY_MODES}
        if isinstance(modes_raw, dict):
            for mode, override in modes_raw.items():
                if mode not in DISPLAY_MODES:
                    raise ValueError("mode must be live, still, light, or screensaver")
                if not isinstance(override, dict):
                    raise ValueError(f"{checked} {mode} must be a table")
                modes[mode] = dict(override)
        profiles[checked] = Profile(checked, values, modes)
    active = _profile_name(_string_value(table.get("active"), next(iter(profiles))))
    if active not in profiles:
        raise ValueError(f"active profile {active} is not defined")
    mode = _string_value(table.get("mode"), "live") or "live"
    if mode not in DISPLAY_MODES:
        raise ValueError("mode must be live, still, light, or screensaver")
    return ConfigDocument(active, mode, profiles, path)


def _document_from_flat(path: Path, table: dict[str, object]) -> ConfigDocument:
    values = factory_values(_string_value(table.get("logo"), ""))
    if "accent" in table and isinstance(table["accent"], str):
        values["primary"] = table["accent"].strip()
    for key in ("preset", "logo", "text_mode", "glyph_set", "glyphs", "phrases", "logo_style", "color_preset"):
        if key in table and isinstance(table[key], str):
            values[key] = table[key].strip() if key != "phrases" else table[key]
    if "logo_size" in table:
        values["logo_size"] = table["logo_size"]
    if "word_scale" in table:
        values["word_scale"] = table["word_scale"]
    if "workers" in table:
        values["workers"] = table["workers"]
    if "text_density" in table:
        values["text_density"] = table["text_density"]
    if "mix" in table:
        values["mix"] = table["mix"]
    if "density" in table:
        values["density"] = table["density"]
    if "speed" in table:
        values["speed"] = table["speed"]
    if "logo_opacity" in table:
        values["logo_opacity"] = table["logo_opacity"]
    if "highlight" in table and isinstance(table["highlight"], str):
        values["highlight"] = table["highlight"]
    if "background" in table and isinstance(table["background"], str):
        values["background"] = table["background"]
    profile = Profile("default", values, factory_modes())
    return ConfigDocument("default", "live", {"default": profile}, path)


def load_document() -> ConfigDocument:
    path = config_dir() / "config.toml"
    if not path.is_file():
        logo = str(package_logo()) if package_logo().is_file() else ""
        profile = Profile("jade", factory_values(logo), factory_modes())
        return ConfigDocument("jade", "live", {"jade": profile}, None)
    table = _table(path)
    if isinstance(table.get("profiles"), dict):
        return _document_from_table(path, table)
    return _document_from_flat(path, table)


def _settings_from_document(document: ConfigDocument) -> Settings:
    profile = document.profiles[document.active]
    values = _merge_values(factory_values(), profile.values)
    values = _merge_values(values, profile.modes.get(document.mode, {}))
    preset = str(values.get("preset") or "full").lower()
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESET_NAMES)}")
    color_preset, primary, highlight, background = _colors(values)
    logo = _string_value(values.get("logo"), "")
    phrases = _string_value(values.get("phrases"), "")
    if len(phrases) > 8000:
        phrases = phrases[:8000]
    words_default = config_dir() / "words.txt"
    words_value = _optional_str(profile.values, "words")
    if words_value:
        words_file = Path(words_value).expanduser()
    elif words_default.is_file():
        words_file = words_default
    else:
        words_file = package_words()
    logo_size = values.get("logo_size", DEFAULT_LOGO_SIZE)
    word_scale = values.get("word_scale", DEFAULT_WORD_SCALE)
    workers = values.get("workers", 0)
    density = values.get("density", 1.0)
    speed = values.get("speed", 1)
    mix = values.get("mix", CLASSIC_PHRASE_MIX)
    if isinstance(logo_size, bool) or not isinstance(logo_size, int):
        raise ValueError("logo_size must be an integer")
    if isinstance(word_scale, bool) or not isinstance(word_scale, (int, float)):
        raise ValueError("word_scale must be a number")
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 0:
        raise ValueError("workers must be 0 (auto) or a positive count")
    if logo_size < 8:
        raise ValueError("logo_size must be at least 8")
    if not 0.05 <= float(word_scale) <= 2.0:
        raise ValueError("word_scale must be between 0.05 and 2")
    if isinstance(density, bool) or not isinstance(density, (int, float)) or not 0.15 <= float(density) <= 2.5:
        raise ValueError("density must be between 0.15 and 2.5")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        raise ValueError("speed must be 1, 2, 3, or 4")
    speed_int = int(round(float(speed)))
    if speed_int not in {1, 2, 3, 4}:
        raise ValueError("speed must be 1, 2, 3, or 4")
    if isinstance(mix, bool) or not isinstance(mix, (int, float)) or not 0 <= float(mix) <= 1:
        raise ValueError("mix must be between 0 and 1")
    glyph_set = str(values.get("glyph_set") or "katakana")
    if glyph_set not in GLYPH_SETS:
        raise ValueError("glyph_set must be katakana, latin, digits, or custom")
    logo_style = str(values.get("logo_style") or "watermark")
    if logo_style not in LOGO_STYLES:
        raise ValueError("logo_style must be watermark or sprite")
    opacity_raw = values.get("logo_opacity", 0.33)
    if isinstance(opacity_raw, bool) or not isinstance(opacity_raw, (int, float)) or not 0 <= float(opacity_raw) <= 1:
        raise ValueError("logo_opacity must be between 0 and 1")
    text_mode = _text_mode(_string_value(values.get("text_mode"), DEFAULT_TEXT_MODE) or DEFAULT_TEXT_MODE)
    return Settings(
        preset=preset,
        accent=primary,
        logo=logo,
        logo_size=logo_size,
        word_scale=float(word_scale),
        words_file=words_file,
        workers=workers,
        text_mode=text_mode,
        text_density=_text_density(values.get("text_density", DEFAULT_TEXT_DENSITY)),
        config_path=document.path,
        profile=document.active,
        display_mode=document.mode,
        color_preset=color_preset,
        primary=primary,
        highlight=highlight,
        background_color=background,
        density=float(density),
        speed=speed_int,
        glyph_set=glyph_set,
        glyphs=_string_value(values.get("glyphs"), "")[:64],
        logo_opacity=float(opacity_raw),
        logo_style=logo_style,
        phrases=phrases,
        phrase_mix=float(mix),
        mode_overrides={mode: dict(body) for mode, body in profile.modes.items()},
    )


def _colors(values: dict[str, object]) -> tuple[str, str, str, str]:
    name = str(values.get("color_preset") or "theme")
    if name not in COLOR_PRESET_NAMES:
        raise ValueError("color_preset must be theme, jade, matrix, ink, or paper")
    primary = _string_value(values.get("primary"), "")
    highlight = _string_value(values.get("highlight"), "")
    background = _string_value(values.get("background"), "")
    preset = COLOR_PRESETS.get(name)
    if preset is not None:
        primary = primary or preset[0]
        highlight = highlight or preset[1]
        background = background or preset[2]
    return name, primary, highlight, background


def save_document(document: ConfigDocument) -> Path:
    if not document.profiles:
        raise ValueError("at least one profile is required")
    active = _profile_name(document.active)
    if active not in document.profiles:
        raise ValueError(f"active profile {active} is not defined")
    if document.mode not in DISPLAY_MODES:
        raise ValueError("mode must be live, still, light, or screensaver")
    lines = [
        f"active = {_toml_string(active)}",
        f"mode = {_toml_string(document.mode)}",
        "",
    ]
    for name, profile in document.profiles.items():
        checked = _profile_name(name)
        lines.append(f"[profiles.{checked}]")
        for key, value in profile.values.items():
            if key == "modes":
                continue
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
        for mode in DISPLAY_MODES:
            override = profile.modes.get(mode, {})
            lines.append(f"[profiles.{checked}.modes.{mode}]")
            for key, value in override.items():
                lines.append(f"{key} = {_toml_value(value)}")
            lines.append("")
    path = document.path or (config_dir() / "config.toml")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("refusing to edit a symlinked config.toml")
    temporary = path.with_name(".config.toml.part")
    if temporary.is_symlink():
        temporary.unlink()
    temporary.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
    return f'"{escaped}"'


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        raise ValueError("config values cannot be booleans")
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, str):
        return _toml_string(value)
    raise ValueError(f"cannot store {type(value).__name__} in config.toml")


def form_values(raw: dict[str, object]) -> dict[str, object]:
    """Validate one editor form into a mode override. Unknown keys are ignored."""

    def text(key: str, limit: int) -> str:
        value = raw.get(key, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        if len(value) > limit:
            raise ValueError(f"{key} is too long")
        return value

    def number(key: str, low: float, high: float, fallback: float) -> float:
        value = raw.get(key, fallback)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(f"{key} must be a number")
        try:
            parsed = float(value)
        except ValueError as error:
            raise ValueError(f"{key} must be a number") from error
        if not low <= parsed <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
        return parsed

    preset = text("color_preset", 16) or "theme"
    if preset not in COLOR_PRESET_NAMES:
        raise ValueError(f"color preset must be one of {', '.join(COLOR_PRESET_NAMES)}")
    style = text("logo_style", 16) or "watermark"
    if style not in LOGO_STYLES:
        raise ValueError("logo style must be watermark or sprite")
    glyphs = text("glyph_set", 16) or "katakana"
    if glyphs not in GLYPH_SETS:
        raise ValueError("glyph set must be katakana, latin, digits, or custom")
    mode = text("text_mode", 16) or DEFAULT_TEXT_MODE
    if mode not in TEXT_MODES:
        raise ValueError("text mode must be off, mix, or replace")
    for key in ("primary", "highlight", "background"):
        color = text(key, 16).strip()
        if color:
            parse_hex(color)
    return {
        "color_preset": preset,
        "primary": text("primary", 16).strip(),
        "highlight": text("highlight", 16).strip(),
        "background": text("background", 16).strip(),
        "logo": text("logo", 400).strip(),
        "logo_size": int(number("logo_size", 40, 800, 250)),
        "logo_opacity": round(number("logo_opacity", 0, 1, 0.33), 4),
        "logo_style": style,
        "word_scale": round(number("word_scale", 0.4, 1.6, 0.86), 4),
        "text_mode": mode,
        "text_density": round(number("text_density", 0, 1, DEFAULT_TEXT_DENSITY), 4),
        "mix": round(number("mix", 0, 1, CLASSIC_PHRASE_MIX), 4),
        "density": round(number("density", 0.2, 1.5, 1.0), 4),
        "speed": int(number("speed", 1, 4, 1)),
        "glyph_set": glyphs,
        "glyphs": text("glyphs", 64),
        "phrases": text("phrases", 8000),
    }


def apply_mode_form(profile_name: str, mode: str, raw: dict[str, object]) -> Settings:
    document = load_document()
    name = _profile_name(profile_name)
    display = _display_mode(mode)
    if name not in document.profiles:
        document.profiles[name] = Profile(name, dict(factory_values()), factory_modes())
    document.active = name
    document.mode = display
    document.profiles[name].modes[display] = form_values(raw)
    save_document(document)
    return load_settings()


def reset_mode(profile_name: str, mode: str) -> Settings:
    document = load_document()
    name = _profile_name(profile_name)
    display = _display_mode(mode)
    if name not in document.profiles:
        document.profiles[name] = Profile(name, dict(factory_values()), factory_modes())
    document.active = name
    document.mode = display
    document.profiles[name].modes[display] = dict(factory_modes().get(display, {}))
    save_document(document)
    return load_settings()


def set_text_mode(mode: str) -> Path | None:
    """Set text_mode in an existing config.toml. A missing file is left missing."""
    checked = _text_mode(mode)
    path = config_dir() / "config.toml"
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("refusing to edit a symlinked config.toml")
    if path.stat().st_size > 256_000:
        raise ValueError("config.toml is unexpectedly large")
    table = _table(path)
    if isinstance(table.get("profiles"), dict):
        document = _document_from_table(path, table)
        profile = document.profiles[document.active]
        profile.values["text_mode"] = checked
        for override in profile.modes.values():
            if "text_mode" in override:
                override["text_mode"] = checked
        save_document(document)
        return path
    text = path.read_text(encoding="utf-8")
    line = f'text_mode = "{checked}"'
    if _TEXT_MODE_LINE.search(text):
        updated = _TEXT_MODE_LINE.sub(line, text, count=1)
    else:
        updated = text if text.endswith("\n") else text + "\n"
        updated += line + "\n"
    temporary = path.with_name(".config.toml.part")
    if temporary.is_symlink():
        temporary.unlink()
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, path)
    return path


def write_text_mode_config(mode: str) -> Path:
    """Create config.toml when a mode other than the implicit one must be recorded."""
    checked = _text_mode(mode)
    path = config_dir() / "config.toml"
    if path.exists():
        set_text_mode(checked)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logo = str(package_logo()) if package_logo().is_file() else ""
    logo = logo.replace("\\", "\\\\").replace('"', '\\"')
    body = (
        'preset = "full"\n'
        'accent = ""\n'
        f'logo = "{logo}"\n'
        f"logo_size = {DEFAULT_LOGO_SIZE}\n"
        f"word_scale = {DEFAULT_WORD_SCALE}\n"
        f'text_mode = "{checked}"\n'
        f"text_density = {DEFAULT_TEXT_DENSITY}\n"
    )
    temporary = path.with_name(".config.toml.part")
    temporary.write_text(body, encoding="utf-8")
    os.replace(temporary, path)
    return path


def parse_words(text: str) -> list[str]:
    """One phrase per line. Blank lines and # comments are ignored."""
    phrases: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        phrases.append(line)
        if len(phrases) == 24:
            break
    return phrases


def load_words(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"words file not found: {path}")
    return parse_words(path.read_text(encoding="utf-8"))


def even(value: int) -> int:
    value = max(2, value)
    return value if value % 2 == 0 else value - 1
