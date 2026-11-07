"""Turn a scene into an mp4 loop and a still."""

from __future__ import annotations

import multiprocessing
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from jade_rain.scene import Scene

_SCENE: Scene | None = None


def still_index(frames: int, fraction: float) -> int:
    if frames <= 1:
        return 0
    return int(fraction * frames) % frames


def write_image(rgb: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(rgb, "RGB")
    if path.suffix.lower() == ".webp":
        try:
            image.save(path, "WEBP", quality=86, method=4)
            return path
        except OSError:
            path = path.with_suffix(".png")
    image.save(path, "PNG", compress_level=3)
    return path


def encode_video(
    scene: Scene,
    path: Path,
    *,
    fps: int,
    workers: int,
    x264_preset: str,
    crf: int,
    threads: int = 1,
) -> float:
    global _SCENE
    _SCENE = scene
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    if partial.exists():
        partial.unlink()
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{scene.width}x{scene.height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        x264_preset,
        "-crf",
        str(crf),
        "-threads",
        str(max(1, threads)),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(partial),
    ]
    started = time.monotonic()
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    if process.stdin is None:
        raise RuntimeError("ffmpeg stdin was not opened")
    step = max(1, scene.frames // 20)
    try:
        if workers <= 1:
            for index in range(scene.frames):
                process.stdin.write(scene.frame(index).tobytes())
                _note(index, scene.frames, step, started)
        else:
            context = multiprocessing.get_context("fork")
            with context.Pool(workers) as pool:
                for index, raw in enumerate(pool.imap(_frame_job, range(scene.frames), chunksize=2)):
                    process.stdin.write(raw)
                    _note(index, scene.frames, step, started)
        process.stdin.close()
        process.stdin = None
        code = process.wait()
    except BrokenPipeError:
        if process.stdin is not None:
            process.stdin.close()
        code = process.wait()
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg exited {code}") from None
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        partial.unlink(missing_ok=True)
        raise
    if code != 0:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg exited {code}")
    partial.replace(path)
    return time.monotonic() - started


def _frame_job(index: int) -> bytes:
    if _SCENE is None:
        raise RuntimeError("render worker started without a scene")
    return _SCENE.frame(index).tobytes()


def _note(index: int, frames: int, step: int, started: float) -> None:
    if index % step != 0 and index + 1 != frames:
        return
    elapsed = time.monotonic() - started
    print(f"frame {index + 1}/{frames}  {elapsed:.1f}s", file=sys.stderr, flush=True)
