import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from jade_rain.config import package_logo
from jade_rain.logo import mark_mask, outline


def _save(image: Image.Image, directory: Path, name: str) -> Path:
    path = directory / name
    image.save(path)
    return path


class LogoTests(unittest.TestCase):
    def test_alpha_trace_ignores_the_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = Image.new("RGBA", (120, 90), (255, 255, 255, 0))
            mark = Image.new("RGBA", (24, 24), (255, 255, 255, 255))
            canvas.paste(mark, (40, 30))
            path = _save(canvas, Path(directory), "alpha.png")
            mask, source = mark_mask(path)
            self.assertEqual(source, "alpha")
            self.assertEqual(mask.size, (24, 24))
            edge = outline(path, 40)
        self.assertLess(edge.shape[0], 70)
        self.assertEqual(float(edge[0, 0]), 0.0)
        self.assertLess(float((edge > 0.2).mean()), 0.25)

    def test_opaque_png_uses_luminance_not_the_rectangle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            canvas = Image.new("RGB", (100, 80), (0, 0, 0))
            mark = Image.new("RGB", (20, 20), (255, 255, 255))
            canvas.paste(mark, (30, 25))
            path = _save(canvas, Path(directory), "opaque.png")
            mask, source = mark_mask(path)
            self.assertEqual(source, "luminance")
            self.assertEqual(mask.size, (20, 20))
            edge = outline(path, 36)
        self.assertLess(edge.shape[0], 60)
        self.assertEqual(float(edge[0].max()), 0.0)
        self.assertEqual(float(edge[-1].max()), 0.0)

    def test_shipped_logo_is_an_outline(self) -> None:
        edge = outline(package_logo(), 220)
        self.assertEqual(float(edge[0].max()), 0.0)
        self.assertEqual(float(edge[-1].max()), 0.0)
        self.assertEqual(float(edge[:, 0].max()), 0.0)
        self.assertEqual(float(edge[:, -1].max()), 0.0)
        self.assertGreater(float(edge.max()), 0.5)
        # A traced plate would be a bright bar. This mark is a thin monogram.
        self.assertLess(float((edge > 0.45).mean()), 0.22)
        row_fill = (edge > 0.3).mean(axis=1)
        self.assertLess(float(row_fill.max()), 0.75)


if __name__ == "__main__":
    unittest.main()
