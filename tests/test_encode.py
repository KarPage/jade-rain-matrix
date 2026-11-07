import subprocess
import tempfile
import unittest
from pathlib import Path

from jade_rain.render import encode_video, write_image
from jade_rain.scene import build_scene
from jade_rain.theme import resolve_palette


class EncodeTests(unittest.TestCase):
    def test_short_loop_and_webp(self) -> None:
        palette = resolve_palette(
            accent_override="#3fe0a4",
            accent_source_label="test",
            background_override="#0d0204",
            theme_file=None,
        )
        scene = build_scene(
            width=160,
            height=100,
            frames=6,
            palette=palette,
            words=[],
            logo_path="",
            logo_size=250,
            word_scale=0.86,
            density=0.2,
        )
        self.assertEqual(scene.frame(0).tobytes(), scene.frame(scene.frames).tobytes())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            video = folder / "jade-rain.mp4"
            encode_video(
                scene,
                video,
                fps=12,
                workers=1,
                x264_preset="veryfast",
                crf=23,
                threads=1,
            )
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-count_frames",
                    "-show_entries",
                    "stream=nb_read_frames,width,height",
                    "-of",
                    "csv=p=0",
                    str(video),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            width, height, frames = probe.stdout.strip().split(",")
            self.assertEqual((width, height, frames), ("160", "100", "6"))
            still = write_image(scene.frame(2), folder / "jade-rain.webp")
            self.assertEqual(still.suffix, ".webp")
            self.assertGreater(still.stat().st_size, 32)


if __name__ == "__main__":
    unittest.main()
