import os
import tempfile
import unittest
from pathlib import Path

from jade_rain.cli import main
from jade_rain.config import apply_mode_form, config_dir, load_document, load_settings, reset_mode
from jade_rain.credit import CREDIT_TEXT, SOURCE_PROFILE, SOURCE_URL


class ProfileTests(unittest.TestCase):
    def test_flat_config_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._home(home)
            config = home / ".config" / "jade-rain"
            config.mkdir(parents=True)
            (config / "config.toml").write_text(
                'logo = "/keep.png"\nlogo_size = 250\nword_scale = 0.86\ntext_mode = "off"\n',
                encoding="utf-8",
            )
            settings = load_settings()
            self.assertEqual(settings.logo, "/keep.png")
            self.assertEqual(settings.logo_size, 250)
            self.assertEqual(settings.word_scale, 0.86)
            self.assertEqual(settings.text_mode, "off")
            self.assertEqual(settings.display_mode, "live")
            self.assertIsNone(settings.phrase_mix)

    def test_profile_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self._home(Path(directory))
            apply_mode_form(
                "studio",
                "light",
                {
                    "color_preset": "paper",
                    "primary": "#1b4d38",
                    "highlight": "#0e2e22",
                    "background": "#f3efe4",
                    "phrases": "north wind\n",
                    "mix": 0.5,
                    "density": 0.7,
                    "speed": 1,
                    "glyph_set": "latin",
                    "logo_style": "sprite",
                    "logo_opacity": 0.4,
                },
            )
            settings = load_settings()
            self.assertEqual(settings.profile, "studio")
            self.assertEqual(settings.display_mode, "light")
            self.assertEqual(settings.color_preset, "paper")
            self.assertEqual(settings.background_color, "#f3efe4")
            self.assertEqual(settings.phrases, "north wind\n")
            self.assertEqual(settings.phrase_mix, 0.5)
            self.assertEqual(settings.glyph_set, "latin")
            self.assertEqual(settings.logo_style, "sprite")
            document = load_document()
            self.assertIn("studio", document.profiles)
            reset_mode("studio", "light")
            reset = load_settings()
            self.assertEqual(reset.display_mode, "light")
            self.assertEqual(reset.color_preset, "paper")
            self.assertAlmostEqual(reset.density, 0.65)

    def test_legacy_config_is_read_and_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self._home(home)
            legacy = home / ".config" / "jade-rain"
            legacy.mkdir(parents=True)
            (legacy / "config.toml").write_text(
                'logo = "/old.png"\nlogo_size = 250\nword_scale = 0.86\ntext_mode = "off"\n',
                encoding="utf-8",
            )
            (legacy / "words.txt").write_text("keep me\n", encoding="utf-8")
            settings = load_settings()
            self.assertEqual(settings.logo, "/old.png")
            self.assertEqual(config_dir(), legacy)
            apply_mode_form("jade", "live", {"phrases": "still here\n", "color_preset": "jade"})
            self.assertFalse((home / ".config" / "jade-rain-matrix").exists())
            self.assertIn("still here", (legacy / "config.toml").read_text(encoding="utf-8"))
            self.assertEqual((legacy / "words.txt").read_text(encoding="utf-8"), "keep me\n")
            current = home / ".config" / "jade-rain-matrix"
            current.mkdir()
            (current / "config.toml").write_text(
                'logo = "/new.png"\nlogo_size = 250\nword_scale = 0.86\ntext_mode = "off"\n',
                encoding="utf-8",
            )
            self.assertEqual(load_settings().logo, "/new.png")
            self.assertEqual((legacy / "words.txt").read_text(encoding="utf-8"), "keep me\n")

    def test_about_names_the_original_rain(self) -> None:
        self.assertIn("@iamdothash", CREDIT_TEXT)
        self.assertIn(SOURCE_URL, CREDIT_TEXT)
        self.assertIn(SOURCE_PROFILE, CREDIT_TEXT)
        self.assertIn("no license", CREDIT_TEXT)
        self.assertIn("Jade Rain Matrix", CREDIT_TEXT)
        with tempfile.TemporaryDirectory() as directory:
            self._home(Path(directory))
            self.assertEqual(main(["about"]), 0)

    def _home(self, home: Path) -> None:
        os.environ["HOME"] = str(home)
        os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
        os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
        os.environ.pop("XDG_DATA_HOME", None)


if __name__ == "__main__":
    unittest.main()
