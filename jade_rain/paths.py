"""Omarchy background paths, the live/still mode, and the theme-set hook."""

from __future__ import annotations

import fcntl
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jade_rain.config import cli_path, omarchy_config, omarchy_state, state_dir

VIDEO_NAME = "jade-rain.mp4"
STILL_NAME = "jade-rain.webp"
HOOK_MARKER = "jade-rain-hook v1"
OUTPUTS_NAME = "outputs"


class RenderBusy(RuntimeError):
    pass


@dataclass
class RenderLock:
    path: Path
    handle: object

    def release(self) -> None:
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def theme_name_file() -> Path:
    return omarchy_state() / "current" / "theme.name"


def colors_file() -> Path:
    return omarchy_state() / "current" / "theme" / "colors.toml"


def current_theme_name() -> str:
    path = theme_name_file()
    if path.is_file():
        name = path.read_text(encoding="utf-8").strip()
        if name:
            return clean_theme_name(name)
    return "jade-rain"


def clean_theme_name(name: str) -> str:
    text = name.strip()
    if not text or "/" in text or text in {".", ".."} or ".." in text:
        raise ValueError(f"invalid theme name: {name!r}")
    return text


def background_dir(theme: str) -> Path:
    return omarchy_config() / "backgrounds" / clean_theme_name(theme)


def wallpaper_paths(theme: str) -> tuple[Path, Path]:
    folder = background_dir(theme)
    return folder / VIDEO_NAME, _still_in(folder)


def mode_outputs(theme: str, mode: str) -> tuple[Path, Path]:
    """Video and still paths for a display mode. live and still share the original names."""
    folder = background_dir(theme)
    if mode == "light":
        return folder / "jade-rain-light.mp4", folder / "jade-rain-light.webp"
    if mode == "screensaver":
        return folder / "jade-rain-screensaver.mp4", folder / "jade-rain-screensaver.webp"
    return wallpaper_paths(theme)


def _still_in(folder: Path) -> Path:
    webp = folder / STILL_NAME
    png = folder / "jade-rain.png"
    if png.is_file() and not webp.is_file():
        return png
    return webp


def mode_path() -> Path:
    return state_dir() / "mode"


def read_mode() -> str:
    path = mode_path()
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text in {"live", "still"}:
            return text
    return "live"


def write_mode(mode: str) -> None:
    if mode not in {"live", "still"}:
        raise ValueError(f"unknown mode: {mode}")
    path = mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n", encoding="utf-8")


def active_wallpaper(theme: str, mode: str | None = None) -> Path:
    video, still = wallpaper_paths(theme)
    chosen = mode or read_mode()
    return video if chosen == "live" else still


def hook_path() -> Path:
    return omarchy_config() / "hooks" / "theme-set.d" / "jade-rain"


def hook_text() -> str:
    cli = cli_path()
    return f"""#!/bin/bash
# {HOOK_MARKER}
# Opt-in. Returns at once. jade-rain-matrix render --from-hook does the work.
set -euo pipefail
state="${{XDG_STATE_HOME:-$HOME/.local/state}}/jade-rain"
mkdir -p "$state"
printf '%s\\n' "${{1:-}}" > "$state/pending-theme"
cli="{cli}"
log="$state/hook.log"
if command -v setsid >/dev/null 2>&1; then
  setsid -f "$cli" render --from-hook >>"$log" 2>&1 </dev/null
else
  nohup "$cli" render --from-hook >>"$log" 2>&1 </dev/null &
fi
exit 0
"""


def hook_enabled() -> bool:
    path = hook_path()
    if not path.is_file():
        return False
    return HOOK_MARKER in path.read_text(encoding="utf-8")


def enable_hook() -> Path:
    path = hook_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hook_text(), encoding="utf-8")
    path.chmod(0o755)
    return path


def disable_hook() -> bool:
    path = hook_path()
    if path.is_file() and HOOK_MARKER in path.read_text(encoding="utf-8"):
        path.unlink()
        return True
    return False


def pending_theme_path() -> Path:
    return state_dir() / "pending-theme"


def write_pending_theme(name: str) -> None:
    path = pending_theme_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name.strip() + "\n", encoding="utf-8")


def consume_pending_theme() -> str | None:
    path = pending_theme_path()
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    path.unlink()
    return text or None


def peek_pending_theme() -> bool:
    path = pending_theme_path()
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def outputs_path() -> Path:
    return state_dir() / OUTPUTS_NAME


def record_output(path: Path) -> None:
    record = outputs_path()
    record.parent.mkdir(parents=True, exist_ok=True)
    text = str(path.resolve())
    existing = record.read_text(encoding="utf-8").splitlines() if record.is_file() else []
    if text not in existing:
        existing.append(text)
    record.write_text("\n".join(existing) + "\n", encoding="utf-8")


def try_lock(*, block: bool) -> RenderLock:
    path = state_dir() / "render.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    flags = fcntl.LOCK_EX
    if not block:
        flags |= fcntl.LOCK_NB
    try:
        fcntl.flock(handle, flags)
    except BlockingIOError:
        handle.close()
        raise RenderBusy("a render is already running") from None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return RenderLock(path, handle)


def set_background(path: Path) -> bool:
    """Point Omarchy at path. Return False when the desktop tool is absent."""
    tool = _which("omarchy-theme-bg-set")
    if tool is None:
        print(f"wallpaper file: {path}")
        print("omarchy-theme-bg-set is not on PATH; the desktop was left as it is")
        return False
    subprocess.run([tool, str(path)], check=True)
    return True


def _which(name: str) -> str | None:
    for folder in os.environ.get("PATH", "").split(":"):
        candidate = Path(folder) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
