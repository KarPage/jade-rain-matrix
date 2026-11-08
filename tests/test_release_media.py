"""Only approved, compact actual-screen media belongs in the release."""
from pathlib import Path
import re
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

class ReleaseMediaTests(unittest.TestCase):
    def test_readme_has_only_animation_and_approved_single_still(self):
        text = (ROOT / 'README.md').read_text()
        images = re.findall(r'!\[[^]]*\]\(([^)]+)\)', text)
        self.assertEqual(images, ['docs/screenshots/jade-rain-loop-readme.webp', 'docs/screenshots/jade-rain-real-1.webp'])
        self.assertNotIn('jade-rain-live-', text)
        self.assertTrue(all((ROOT / name).is_file() for name in images))

    def test_media_is_small_and_actually_animated(self):
        path = ROOT / 'docs/screenshots/jade-rain-loop-readme.webp'
        self.assertLess(path.stat().st_size, 8_000_000)
        with Image.open(path) as image:
            self.assertEqual(image.size, (960, 580))
            self.assertEqual(image.n_frames, 120)
            self.assertEqual(image.info['loop'], 0)
        with Image.open(ROOT / 'docs/screenshots/jade-rain-real-1.webp') as image:
            self.assertEqual(image.size, (1920, 1157))

    def test_no_rejected_or_legacy_screenshot_assets(self):
        self.assertEqual(sorted(p.name for p in (ROOT / 'docs/screenshots').iterdir()), ['jade-rain-loop-readme.webp', 'jade-rain-real-1.webp'])
        self.assertFalse((ROOT / 'screenshots').exists())
