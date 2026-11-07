"""Omarchy screensaver playback.

Omarchy starts a screensaver by name (`omarchy-launch-screensaver`) when the
shell has been idle. There is no screensaver hook directory. `enable` writes
a small launcher in ~/.local/bin that plays the rendered video with mpv,
which is already in the Omarchy base set. Any key or mouse button quits.
`enable` refuses to replace a launcher it did not write.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from jade_rain.config import PRIMARY_COMMAND, config_dir, package_root

MARKER = "jade-rain-screensaver-hook v1"


def script_path() -> Path:
    return package_root() / "share" / "screensaver.lua"


def hook_paths() -> list[Path]:
    return [
        Path.home() / ".local" / "bin" / "omarchy-launch-screensaver",
        Path.home() / ".local" / "share" / "omarchy" / "bin" / "omarchy-launch-screensaver",
    ]


def hook_path() -> Path:
    return hook_paths()[0]


def player_command(video: Path) -> list[str]:
    script = script_path()
    if not script.is_file():
        raise FileNotFoundError(f"screensaver script missing: {script}")
    return [
        "mpv",
        "--fullscreen",
        "--loop-file=inf",
        "--no-osc",
        "--osd-level=0",
        "--cursor-autohide=always",
        "--no-input-default-bindings",
        "--no-terminal",
        f"--script={script}",
        str(video),
    ]


def find_video() -> Path | None:
    from jade_rain.paths import background_dir, current_theme_name

    folder = background_dir(current_theme_name())
    for name in ("jade-rain-screensaver.mp4", "jade-rain.mp4"):
        candidate = folder / name
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    return None


def play(video: Path | None = None, *, dry_run: bool = False) -> int:
    chosen = video or find_video()
    if chosen is None or not chosen.is_file():
        print(
            f"no screensaver video yet. Render one with: {PRIMARY_COMMAND} render",
            file=sys.stderr,
        )
        print(f"set mode = \"screensaver\" in {config_dir() / 'config.toml'} first", file=sys.stderr)
        return 1
    command = player_command(chosen)
    if dry_run:
        print(" ".join(command))
        return 0
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def enable() -> Path:
    binary = shlex.quote(str(package_root() / "bin" / PRIMARY_COMMAND))
    body = f"""#!/usr/bin/env bash
# {MARKER}
exec {binary} screensaver
"""
    for destination in hook_paths():
        if destination.exists() and MARKER not in _read_limited(destination):
            raise ValueError(f"refusing to replace {destination}; it was not written by Jade Rain Matrix")
    primary = hook_paths()[0]
    for destination in hook_paths():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(".omarchy-launch-screensaver.part")
        if temporary.is_symlink():
            temporary.unlink()
        temporary.write_text(body, encoding="utf-8")
        os.chmod(temporary, 0o755)
        os.replace(temporary, destination)
    return primary


def disable() -> bool:
    removed = False
    for destination in hook_paths():
        if not destination.exists():
            continue
        if MARKER not in _read_limited(destination):
            continue
        destination.unlink()
        removed = True
    return removed


def _read_limited(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        return ""
    if path.stat().st_size > 16_000:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")
