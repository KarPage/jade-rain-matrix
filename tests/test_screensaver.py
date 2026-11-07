import os
import tempfile
import unittest
from pathlib import Path

from jade_rain.screensaver import MARKER, enable, play, player_command, script_path


class ScreensaverTests(unittest.TestCase):
    def test_player_command_is_a_list(self) -> None:
        video = Path("/tmp/jade-rain-screensaver.mp4")
        command = player_command(video)
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], "mpv")
        self.assertIn("--fullscreen", command)
        self.assertTrue(any(part.startswith("--script=") for part in command))
        self.assertEqual(command[-1], str(video))
        script = script_path().read_text(encoding="utf-8")
        self.assertIn("quit", script)
        self.assertIn("MBTN_LEFT", script)

    def test_enable_refuses_a_foreign_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            os.environ["HOME"] = str(home)
            hook = home / ".local" / "bin" / "omarchy-launch-screensaver"
            hook.parent.mkdir(parents=True)
            hook.write_text("#!/bin/sh\necho other\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                enable()
            self.assertNotIn(MARKER, hook.read_text(encoding="utf-8"))

    def test_dry_run_prints_without_opening_mpv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            os.environ["HOME"] = str(home)
            os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
            os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
            folder = home / ".local" / "state" / "omarchy" / "current"
            folder.mkdir(parents=True)
            (folder / "theme.name").write_text("test-theme\n", encoding="utf-8")
            video = home / ".config" / "omarchy" / "backgrounds" / "test-theme" / "jade-rain-screensaver.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"not a real video")
            self.assertEqual(play(dry_run=True), 0)


if __name__ == "__main__":
    unittest.main()
