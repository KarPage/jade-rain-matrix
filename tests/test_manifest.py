import json
import os
import unittest
from pathlib import Path

from jade_rain import __version__

ROOT = Path(__file__).resolve().parent.parent


class ManifestTests(unittest.TestCase):
    def test_manifest_matches_the_package(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["version"], __version__)
        self.assertEqual(manifest["name"], "Jade Rain Matrix")
        self.assertEqual(manifest["barWidget"]["displayName"], "Jade Rain Matrix")
        self.assertEqual(manifest["id"], "io.github.karpage.jade-rain")
        self.assertFalse(manifest["id"].startswith("omarchy."))
        self.assertNotIn("..", manifest["id"])
        entry = manifest["entryPoints"]["service"]
        self.assertFalse(entry.startswith("/"))
        self.assertNotIn("..", entry)
        self.assertTrue((ROOT / entry).is_file())
        self.assertIn("service", manifest["kinds"])
        self.assertIn("bar-widget", manifest["kinds"])
        widget = manifest["entryPoints"]["barWidget"]
        self.assertEqual(widget, "BarWidget.qml")
        self.assertTrue((ROOT / widget).is_file())
        qml = (ROOT / widget).read_text(encoding="utf-8")
        self.assertIn("Jade Rain Matrix", qml)
        self.assertIn("jade-rain", qml)
        self.assertIn("edit", qml)
        self.assertNotIn("http://", qml)
        self.assertNotIn("https://", qml)

    def test_plugin_tree_has_no_symlinks(self) -> None:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            if ".git" in dirnames:
                dirnames.remove(".git")
            for name in dirnames + filenames:
                path = Path(dirpath) / name
                self.assertFalse(path.is_symlink(), str(path))


if __name__ == "__main__":
    unittest.main()
