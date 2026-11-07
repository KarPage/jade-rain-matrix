import unittest

import numpy as np

from jade_rain.config import package_logo, parse_words
from jade_rain.logo import mark_heights
from jade_rain.scene import build_scene, rain_characters
from jade_rain.theme import resolve_palette

WORDS = parse_words("Kar Page\napps.karpage.com\nOmaRaptor\n")


def scene(**overrides: object) -> object:
    palette = resolve_palette(
        accent_override="#3fe0a4",
        accent_source_label="test",
        background_override="#0d0204",
        theme_file=None,
    )
    settings = {
        "width": 320,
        "height": 200,
        "frames": 6,
        "palette": palette,
        "words": WORDS,
        "logo_path": str(package_logo()),
        "logo_size": 250,
        "word_scale": 0.86,
        "density": 0.25,
    }
    settings.update(overrides)
    return build_scene(**settings)  # type: ignore[arg-type]


class SceneTests(unittest.TestCase):
    def test_loop_closes_and_moves(self) -> None:
        built = scene()
        first = built.frame(0)
        nxt = built.frame(1)
        last = built.frame(built.frames - 1)
        after = built.frame(built.frames)
        self.assertEqual(first.shape, (200, 320, 3))
        self.assertEqual(first.tobytes(), after.tobytes())
        self.assertNotEqual(first.tobytes(), nxt.tobytes())
        step = np.abs(first.astype(np.int16) - nxt.astype(np.int16)).mean()
        seam = np.abs(last.astype(np.int16) - first.astype(np.int16)).mean()
        self.assertGreater(float(step), 0.0)
        self.assertLess(float(seam), float(step) * 4 + 0.5)

    def test_logo_and_word_scale(self) -> None:
        built = scene()
        self.assertEqual(built.logo_mark_heights, mark_heights(250, 200))
        self.assertEqual(len(built.logos), 2)
        full = scene(word_scale=1.0, logo_path="")
        small = scene(word_scale=0.86, logo_path="")
        self.assertLess(sum(small.word_font_px), sum(full.word_font_px))
        self.assertTrue(any(glyph.name for stream in built.streams for glyph in stream.words.values()))

    def test_empty_words_are_pure_rain(self) -> None:
        built = scene(words=[], logo_path="")
        self.assertFalse(any(stream.words for stream in built.streams))
        self.assertEqual(built.logos, [])

    def test_rain_sprites_are_not_blank(self) -> None:
        built = scene(words=[], logo_path="", density=0.1)
        sprites, _pad = built.rain[2]
        self.assertGreater(float(max(sprite.max() for sprite in sprites)), 0.5)

    def test_text_off_matches_the_default_scene(self) -> None:
        plain = scene(logo_path="")
        ignored = scene(
            logo_path="",
            text_mode="off",
            text_phrases=["quartz xylophone"],
            text_density=1,
        )
        self.assertEqual(plain.frame(0).tobytes(), ignored.frame(0).tobytes())
        self.assertEqual(plain.frame(3).tobytes(), ignored.frame(3).tobytes())

    def test_source_phrases_mix_and_replace(self) -> None:
        mixed = scene(
            words=["Kar Page"],
            logo_path="",
            density=1,
            text_mode="mix",
            text_phrases=["quartz xylophone"],
            text_density=1,
        )
        replaced = scene(
            words=["Kar Page"],
            logo_path="",
            density=1,
            text_mode="replace",
            text_phrases=["quartz xylophone"],
            text_density=1,
        )
        mixed_chars = {glyph.char.lower() for stream in mixed.streams for glyph in stream.words.values()}
        replaced_chars = {glyph.char.lower() for stream in replaced.streams for glyph in stream.words.values()}
        self.assertIn("q", mixed_chars)
        self.assertTrue(any(glyph.name for stream in mixed.streams for glyph in stream.words.values()))
        self.assertIn("q", replaced_chars)
        self.assertNotIn("k", replaced_chars)
        self.assertFalse(any(glyph.name for stream in replaced.streams for glyph in stream.words.values()))
        self.assertEqual(replaced.frame(0).tobytes(), replaced.frame(replaced.frames).tobytes())

    def test_source_phrases_show_in_the_visible_columns(self) -> None:
        phrase = "quartz xylophone"
        mixed = scene(
            words=["Kar Page"],
            logo_path="",
            width=960,
            height=600,
            frames=12,
            density=1,
            text_mode="mix",
            text_phrases=[phrase],
            text_density=0.35,
        )
        replaced = scene(
            words=["Kar Page"],
            logo_path="",
            width=960,
            height=600,
            frames=12,
            density=1,
            text_mode="replace",
            text_phrases=[phrase],
            text_density=0.35,
        )
        mixed_columns = [reading for reading in (_column_text(stream) for stream in mixed.streams) if reading]
        self.assertTrue(any(glyph.name for stream in mixed.streams for glyph in stream.words.values()))
        self.assertTrue(any("quartz" in column for column in mixed_columns))
        self.assertGreaterEqual(sum("quartz" in column for column in mixed_columns), 3)
        self.assertTrue(all(glyph.steady for stream in mixed.streams for glyph in stream.words.values() if not glyph.name))
        self.assertTrue(any("quartz" in column for column in _visible_text(mixed, 0)))
        self.assertTrue(any("quartz" in column for column in _visible_text(mixed, 6)))
        mixed.frame(0)

        replaced_columns = [reading for reading in (_column_text(stream) for stream in replaced.streams) if reading]
        self.assertFalse(any(glyph.name for stream in replaced.streams for glyph in stream.words.values()))
        self.assertTrue(replaced_columns)
        self.assertTrue(all("quartz" in column or "xylophone" in column for column in replaced_columns))
        self.assertGreaterEqual(len(replaced_columns), 8)
        self.assertTrue(any("xylophone" in column for column in _visible_text(replaced, 3)))
        self.assertNotIn("k", "".join(_visible_text(replaced, 3)))
        replaced.frame(3)


    def test_classic_mix_and_opacity_match_the_original_scene(self) -> None:
        original = scene()
        classic = scene(phrase_mix=0.32, logo_opacity=0.33, cycles=1, glyph_set="katakana")
        self.assertTrue(np.array_equal(original.frame(2), classic.frame(2)))

    def test_two_cycles_still_meet_the_first_frame(self) -> None:
        built = scene(cycles=2, frames=8)
        self.assertTrue(np.array_equal(built.frame(0), built.frame(built.frames)))
        self.assertFalse(np.array_equal(built.frame(0), built.frame(1)))

    def test_light_field_uses_dark_ink(self) -> None:
        palette = resolve_palette(
            accent_override="#1b4d38",
            accent_source_label="paper",
            background_override="#f3efe4",
            theme_file=None,
            highlight="#0e2e22",
            allow_light=True,
        )
        built = scene(palette=palette, logo_path="", words=[], density=0.45, frames=4)
        frame = built.frame(1)
        self.assertGreater(float(frame.mean()), 160.0)
        self.assertLess(int(frame.min()), 90)

    def test_latin_glyphs_are_ascii(self) -> None:
        chars = rain_characters("latin")
        self.assertTrue(chars)
        self.assertTrue(all(ord(char) < 128 for char in chars))
        built = scene(glyph_set="latin", words=[], logo_path="")
        self.assertGreater(int(built.frame(1).std()), 0)


def _column_text(stream: object) -> str:
    rows = range(stream.rows)
    chars = []
    for row in rows:
        glyph = stream.words.get(row)
        chars.append(glyph.char if glyph is not None else " ")
    return " ".join("".join(chars).casefold().split())


def _visible_text(built: object, t: int) -> list[str]:
    cycle = t / built.frames
    found: list[str] = []
    for stream in built.streams:
        head = int((stream.phase + stream.period * cycle) % stream.period)
        chars: list[str] = []
        for depth in range(stream.tail, -1, -1):
            glyph = stream.words.get(head - depth)
            chars.append(glyph.char if glyph is not None else " ")
        text = " ".join("".join(chars).casefold().split())
        if text:
            found.append(text)
    return found


if __name__ == "__main__":
    unittest.main()
