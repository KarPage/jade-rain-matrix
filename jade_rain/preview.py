"""A real renderer scene packed for local canvas playback (no frame polling).

Python remains the source of truth for layout, glyphs, words, logo and palette.
The browser only advances streams and composites these exact alpha masks.
"""
from __future__ import annotations

import base64
import io
from dataclasses import asdict

import numpy as np
from PIL import Image

from jade_rain.scene import Scene


def canvas_scene(scene: Scene, mode: str) -> dict[str, object]:
    masks: list[np.ndarray] = []

    def add(mask: np.ndarray) -> int:
        masks.append(mask)
        return len(masks) - 1

    rain = [{"ids": [add(mask) for mask in sprites], "pad": pad} for sprites, pad in scene.rain]
    words = [[{"ids": {char: add(mask) for char, mask in sprites.items()}, "pad": pad}
              for sprites, pad in layer] for layer in scene.word_sprites]
    glows = [add(mask) for mask in scene.glows]
    logos = [{"id": add(logo.mask), "x": logo.x, "travel": logo.travel,
              "phase": logo.phase, "color": logo.color.tolist()} for logo in scene.logos]
    sprite = None if scene.logo_sprite is None else {
        "id": add(scene.logo_sprite[0]), "color": scene.logo_sprite[1].tolist()}
    # Shelf-pack small grayscale masks. Alpha PNG decodes directly in canvas.
    width = max(1024, max((mask.shape[1] for mask in masks), default=1))
    boxes: list[tuple[int, int, int, int]] = []
    x = y = row_height = 0
    for mask in masks:
        h, w = mask.shape
        if x + w > width:
            x, y, row_height = 0, y + row_height, 0
        boxes.append((x, y, w, h))
        x += w
        row_height = max(row_height, h)
    atlas = Image.new("RGBA", (width, max(1, y + row_height)), (255, 255, 255, 0))
    for mask, (x, y, w, h) in zip(masks, boxes):
        tile = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        tile.putalpha(Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8)))
        atlas.paste(tile, (x, y))
    data = io.BytesIO()
    atlas.save(data, format="PNG")
    return {
        "width": scene.width, "height": scene.height, "frames": scene.frames,
        "cycles": scene.cycles, "mode": mode,
        "background": scene.background.tolist(), "ramp": scene.ramp.tolist(),
        "glowColor": scene.glow_color.tolist(), "rain": rain, "words": words,
        "glows": glows, "logos": logos, "logoSprite": sprite,
        "streams": [asdict(stream) for stream in scene.streams], "boxes": boxes,
        "atlas": "data:image/png;base64," + base64.b64encode(data.getvalue()).decode("ascii"),
    }
