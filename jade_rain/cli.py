"""jade-rain-matrix command line. jade-rain is the same program."""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import time
from pathlib import Path

from jade_rain import __version__
from jade_rain.compose import scene_from_settings
from jade_rain.config import (
    PRESETS,
    even,
    Settings,
    load_settings,
    load_words,
    parse_words,
    set_text_mode,
    source_file,
    write_text_mode_config,
)
from jade_rain.credit import CREDIT_TEXT
from jade_rain.editor import serve
from jade_rain.paths import (
    RenderBusy,
    active_wallpaper,
    colors_file,
    consume_pending_theme,
    current_theme_name,
    disable_hook,
    enable_hook,
    hook_enabled,
    hook_path,
    mode_outputs,
    wallpaper_paths,
    peek_pending_theme,
    read_mode,
    record_output,
    set_background,
    try_lock,
    write_mode,
)
from jade_rain.render import encode_video, still_index, write_image
from jade_rain.screensaver import disable as disable_screensaver
from jade_rain.screensaver import enable as enable_screensaver
from jade_rain.screensaver import play as play_screensaver
from jade_rain.textsrc import TextRejected, extract_text, load_source_phrases, sample_phrases, write_source


def _program() -> str:
    name = Path(sys.argv[0]).name
    if name in {"jade-rain", "jade-rain-matrix"}:
        return name
    return "jade-rain-matrix"


def main(argv: list[str] | None = None) -> int:
    program = _program()
    parser = argparse.ArgumentParser(prog=program, description="Jade Rain Matrix digital-rain wallpaper for Omarchy.")
    parser.add_argument("--version", action="version", version=f"{program} {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    render = commands.add_parser("render", help="render the loop and still from config")
    render.add_argument("--preset", choices=tuple(PRESETS))
    render.add_argument("--width", type=int)
    render.add_argument("--height", type=int)
    render.add_argument("--fps", type=int)
    render.add_argument("--frames", type=int)
    render.add_argument("--accent", help="hex color; overrides the theme accent for this run")
    render.add_argument("--background", help="hex field color, used as-is")
    render.add_argument("--colors", type=Path, help="colors.toml to read instead of the active theme")
    render.add_argument("--logo", help="PNG path, or empty string for no logo")
    render.add_argument("--logo-size", type=int, dest="logo_size")
    render.add_argument("--word-scale", type=float, dest="word_scale")
    render.add_argument("--words", type=Path)
    render.add_argument("--workers", type=int)
    render.add_argument("--out", type=Path, help="with --still-only, write this image and nothing else")
    render.add_argument("--out-dir", type=Path, help="wallpaper directory instead of the theme backgrounds")
    render.add_argument("--theme", help="background folder name; default is the active theme")
    render.add_argument("--at", type=float, default=0.34, help="still position in the loop, 0..1")
    render.add_argument("--still-only", action="store_true")
    render.add_argument("--no-still", action="store_true")
    render.add_argument("--no-set", action="store_true", help="write files without calling omarchy-theme-bg-set")
    render.add_argument("--from-hook", action="store_true", help=argparse.SUPPRESS)
    render.add_argument("--density", type=float, default=None, help=argparse.SUPPRESS)

    commands.add_parser("toggle", help="switch between the live loop and the still")
    commands.add_parser("live", help="show the live loop")
    commands.add_parser("still", help="show the still")

    hook = commands.add_parser("hook", help="opt-in theme-change hook")
    hook_commands = hook.add_subparsers(dest="hook_command", required=True)
    hook_commands.add_parser("enable")
    hook_commands.add_parser("disable")
    hook_commands.add_parser("status")

    commands.add_parser("paths", help="print the config, state, and wallpaper paths")

    source = commands.add_parser("source", help="read a local text file into the rain")
    source.add_argument("file", type=Path)
    source.add_argument("--mode", choices=("off", "mix", "replace"))

    commands.add_parser("edit", help="open the local editor")
    commands.add_parser("about", help="print credits and version")

    saver = commands.add_parser("screensaver", help="play the rain as a screensaver")
    saver.add_argument("--dry-run", action="store_true", help="print the mpv command and exit")
    saver.add_argument("--enable", action="store_true", help="opt in to the Omarchy idle hook")
    saver.add_argument("--disable", action="store_true", help="remove the idle hook Jade Rain Matrix wrote")

    args = parser.parse_args(argv)
    try:
        if args.command == "render":
            return _command_render(args)
        if args.command == "toggle":
            return _command_mode(None)
        if args.command == "live":
            return _command_mode("live")
        if args.command == "still":
            return _command_mode("still")
        if args.command == "hook":
            return _command_hook(args.hook_command)
        if args.command == "paths":
            return _command_paths()
        if args.command == "source":
            return _command_source(args.file, args.mode)
        if args.command == "edit":
            return serve()
        if args.command == "about":
            print(CREDIT_TEXT)
            print(f"{program} {__version__}")
            return 0
        if args.command == "screensaver":
            return _command_screensaver(args.dry_run, args.enable, args.disable)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"{program}: {exc}", file=sys.stderr)
        return 1
    print(f"{program}: unknown command {args.command}", file=sys.stderr)
    return 2


def _command_hook(action: str) -> int:
    if action == "enable":
        path = enable_hook()
        print(f"theme-set hook installed: {path}")
        print("It returns immediately. Rendering continues in the background.")
        return 0
    if action == "disable":
        if disable_hook():
            print("theme-set hook removed")
        else:
            print("theme-set hook was not installed")
        return 0
    if action == "status":
        if hook_enabled():
            print(f"enabled  {hook_path()}")
        else:
            print("disabled")
        return 0
    print(f"{_program()}: unknown hook command {action}", file=sys.stderr)
    return 2


def _command_paths() -> int:
    theme = current_theme_name()
    video, still = wallpaper_paths(theme)
    print(f"theme: {theme}")
    print(f"mode: {read_mode()}")
    print(f"video: {video}")
    print(f"still: {still}")
    print(f"colors: {colors_file()}")
    print(f"hook: {hook_path()}")
    print(f"source: {source_file()}")
    return 0


def _command_source(path: Path, mode: str | None) -> int:
    cleaned = extract_text(path.expanduser())
    if not cleaned.strip():
        raise TextRejected("no readable prose in that file")
    dest = write_source(path, cleaned)
    phrases = sample_phrases(cleaned)
    settings = load_settings()
    chosen = mode if mode is not None else ("mix" if settings.text_mode == "off" else settings.text_mode)
    if settings.config_path is None:
        if chosen != "mix":
            write_text_mode_config(chosen)
    elif chosen != settings.text_mode:
        set_text_mode(chosen)
    print(f"wrote {dest}")
    print(f"phrases {len(phrases)}")
    print(f"text_mode = {chosen}")
    print(f"text_density = {settings.text_density}")
    print("stored locally and not uploaded")
    print(f"next: {_program()} render")
    return 0


def _command_mode(forced: str | None) -> int:
    theme = current_theme_name()
    current = read_mode()
    if forced is None:
        mode = "still" if current == "live" else "live"
    else:
        mode = forced
    write_mode(mode)
    path = active_wallpaper(theme, mode)
    if not path.is_file():
        print(f"{_program()}: missing {path}", file=sys.stderr)
        print(f"run {_program()} render first", file=sys.stderr)
        return 1
    set_background(path)
    print(f"{mode}  {path}")
    return 0


def _command_render(args: argparse.Namespace) -> int:
    if args.from_hook:
        return _render_from_hook()
    try:
        lock = try_lock(block=False)
    except RenderBusy as exc:
        print(f"{_program()}: {exc}", file=sys.stderr)
        return 1
    try:
        return _render_job(args, apply=not args.no_set)
    finally:
        lock.release()


def _render_from_hook() -> int:
    deadline = time.monotonic() + 8
    while True:
        try:
            lock = try_lock(block=False)
            break
        except RenderBusy:
            if time.monotonic() > deadline:
                print("render already running; it will pick up the theme change", file=sys.stderr)
                return 0
            time.sleep(0.2)
    try:
        while True:
            consume_pending_theme()
            code = _render_job(_hook_args(), apply=True)
            if code != 0:
                return code
            if peek_pending_theme():
                continue
            time.sleep(0.3)
            if not peek_pending_theme():
                return 0
    finally:
        lock.release()


def _hook_args() -> argparse.Namespace:
    return argparse.Namespace(
        preset=None,
        width=None,
        height=None,
        fps=None,
        frames=None,
        accent=None,
        background=None,
        colors=None,
        logo=None,
        logo_size=None,
        word_scale=None,
        words=None,
        workers=None,
        out=None,
        out_dir=None,
        theme=None,
        at=0.34,
        still_only=False,
        no_still=False,
        no_set=False,
        from_hook=True,
        density=None,
    )


def _command_screensaver(dry_run: bool, enable: bool, disable: bool) -> int:
    if enable and disable:
        raise ValueError("choose enable or disable")
    if enable:
        path = enable_screensaver()
        print(f"screensaver hook installed: {path}")
        print("Omarchy starts it by name when the shell is idle. Any key or click quits.")
        print(f"Render first: set mode = \"screensaver\", then {_program()} render")
        return 0
    if disable:
        removed = disable_screensaver()
        print("screensaver hook removed" if removed else "no Jade Rain Matrix screensaver hook was installed")
        return 0
    return play_screensaver(dry_run=dry_run)


def _rain_text(settings: Settings) -> tuple[str, list[str], float]:
    mode = settings.text_mode
    density = settings.text_density
    if mode == "off":
        return "off", [], density
    try:
        phrases = load_source_phrases()
    except TextRejected as exc:
        print(f"{_program()}: {exc}", file=sys.stderr)
        return "off", [], density
    if not phrases:
        print(f"{_program()}: text_mode is set and source.txt has no phrases", file=sys.stderr)
        return "off", [], density
    return mode, phrases, density


def _cpu_count() -> int:
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = os.cpu_count() or 1
    return max(1, affinity)


def _worker_split(requested: int) -> tuple[int, int]:
    """Frame processes and x264 threads. They run at the same time."""
    cpus = _cpu_count()
    if requested > 0:
        render = requested
        encode = max(1, cpus - render) if render < cpus else 1
        return render, min(8, encode)
    if cpus == 1:
        return 1, 1
    render = max(1, min(8, (cpus + 1) // 2))
    return render, max(1, min(8, cpus - render))


def _render_job(args: argparse.Namespace, *, apply: bool) -> int:
    settings = load_settings()
    if args.logo is not None:
        settings = dataclasses.replace(settings, logo=args.logo)
    if args.logo_size is not None:
        settings = dataclasses.replace(settings, logo_size=args.logo_size)
    if args.word_scale is not None:
        settings = dataclasses.replace(settings, word_scale=args.word_scale)
    still_job = args.still_only or settings.display_mode == "still"
    preset = PRESETS[args.preset or settings.preset]
    width = even(args.width or preset.width)
    height = even(args.height or preset.height)
    fps = args.fps or preset.fps
    frames = args.frames or preset.frames
    if fps < 1 or frames < 1:
        raise ValueError("fps and frames must be at least 1")
    if not still_job and frames < 2:
        raise ValueError("a loop needs at least 2 frames")
    theme_file = args.colors if args.colors is not None else colors_file()
    if args.colors is None and not theme_file.is_file():
        theme_file = None
    text_mode, text_phrases, text_density = _rain_text(settings)
    settings = dataclasses.replace(settings, text_mode=text_mode, text_density=text_density)
    if args.words:
        words = load_words(args.words)
    elif settings.phrases.strip():
        words = parse_words(settings.phrases)
    else:
        words = load_words(settings.words_file)
    workers, encode_threads = _worker_split(
        args.workers if args.workers is not None else settings.workers
    )
    theme = args.theme or current_theme_name()
    started = time.monotonic()
    scene = scene_from_settings(
        settings,
        width=width,
        height=height,
        frames=frames,
        words=words,
        source_phrases=text_phrases,
        theme_file=theme_file,
        accent=args.accent or "",
        background=args.background or "",
        density=args.density,
    )
    print(
        f"{settings.display_mode}  profile {settings.profile}  {width}x{height}  "
        f"{frames} frames  {fps} fps  words {len(words)}  speed {settings.speed}  "
        f"mix {settings.phrase_mix if settings.phrase_mix is not None else 'classic'}  "
        f"text {text_mode} {len(text_phrases)}  workers {workers}+{encode_threads}",
        file=sys.stderr,
    )
    print(f"scene {time.monotonic() - started:.1f}s", file=sys.stderr)
    if still_job and args.out is not None:
        image = scene.frame(still_index(frames, args.at))
        written = write_image(image, args.out)
        print(written)
        return 0
    video_path, still_path = mode_outputs(theme, settings.display_mode)
    if args.out_dir is not None:
        video_path = args.out_dir / video_path.name
        still_path = args.out_dir / still_path.name
    if not still_job:
        elapsed = encode_video(
            scene,
            video_path,
            fps=fps,
            workers=workers,
            x264_preset=preset.x264_preset,
            crf=preset.crf,
            threads=encode_threads,
        )
        record_output(video_path)
        print(f"video {video_path}  {elapsed:.1f}s")
    if not args.no_still or still_job:
        image = scene.frame(still_index(frames, args.at))
        written = write_image(image, still_path if args.out is None else args.out)
        if args.out is None:
            record_output(written)
        print(written)
        still_path = written
    if apply and settings.display_mode == "screensaver":
        print("screensaver video is not set as the desktop background", file=sys.stderr)
    elif apply and not still_job:
        if args.from_hook and peek_pending_theme():
            print("theme changed during render; leaving the background alone", file=sys.stderr)
        elif settings.display_mode == "light" and video_path.is_file():
            set_background(video_path)
        else:
            chosen = active_wallpaper(theme, read_mode())
            if args.out_dir is not None:
                chosen = video_path if read_mode() == "live" else still_path
            if settings.display_mode == "live" and chosen.is_file():
                set_background(chosen)
    elif apply and still_job and args.out is None and still_path.is_file():
        set_background(still_path)
    return 0
