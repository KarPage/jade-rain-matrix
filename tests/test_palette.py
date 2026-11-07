import tempfile
import unittest
from pathlib import Path

import numpy as np

from jade_rain.config import parse_words
from jade_rain.logo import mark_heights
from jade_rain.theme import FALLBACK_BACKGROUND, parse_hex, resolve_palette


class PaletteTests(unittest.TestCase):
    def test_blue_accent_stays_blue(self) -> None:
        palette = resolve_palette(
            accent_override="#7aa2f7",
            accent_source_label="cli",
            background_override="",
            theme_file=None,
        )
        body = palette.ramp[2]
        self.assertGreater(body[2], body[0])
        self.assertGreater(body[2], body[1])
        self.assertEqual(palette.accent_source, "cli")
        np.testing.assert_allclose(palette.background, FALLBACK_BACKGROUND)

    def test_theme_file_and_legacy_background(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colors.toml"
            path.write_text(
                'accent = "#c45c26"\nbg = "#f4f0e6"\n',
                encoding="utf-8",
            )
            palette = resolve_palette(
                accent_override="",
                accent_source_label="",
                background_override="",
                theme_file=path,
            )
        self.assertEqual(palette.accent_hex, "#c45c26")
        self.assertLess(float(palette.background.max()), 48.0)

    def test_darker_background_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colors.toml"
            path.write_text(
                '\n'.join(
                    [
                        'accent = "#7aa2f7"',
                        'background = "#1a1b26"',
                        'darker_background = "#0e0e14"',
                    ]
                ),
                encoding="utf-8",
            )
            palette = resolve_palette(
                accent_override="",
                accent_source_label="",
                background_override="",
                theme_file=path,
            )
        self.assertLess(float(palette.background.mean()), 30.0)

    def test_paper_preset_keeps_a_light_field(self) -> None:
        palette = resolve_palette(
            accent_override="#1b4d38",
            accent_source_label="paper",
            background_override="#f3efe4",
            theme_file=None,
            highlight="#0e2e22",
            allow_light=True,
        )
        self.assertGreater(float(palette.background.mean()), 180.0)
        self.assertLess(float(palette.ramp[2].mean()), float(palette.background.mean()))

    def test_explicit_background_is_not_mixed(self) -> None:
        palette = resolve_palette(
            accent_override="#3fe0a4",
            accent_source_label="cli",
            background_override="#010203",
            theme_file=None,
        )
        np.testing.assert_allclose(palette.background, parse_hex("#010203"))

    def test_words_and_logo_heights(self) -> None:
        self.assertEqual(
            parse_words("# note\n\nKar Page\napps.karpage.com\n"),
            ["Kar Page", "apps.karpage.com"],
        )
        self.assertEqual(mark_heights(250, 1800), (250, 210))
        self.assertEqual(mark_heights(250, 900), (125, 105))


if __name__ == "__main__":
    unittest.main()
