import unittest
from unittest import mock

from jade_rain import editor


class AppWindowTest(unittest.TestCase):
    def test_chromium_app_window_has_class_and_no_chrome(self) -> None:
        with mock.patch("shutil.which", return_value="/usr/bin/chromium"), mock.patch.object(editor.Path, "mkdir"):
            cmd = editor.app_window_command("http://127.0.0.1:1/?token=x")
        self.assertIn("--app=http://127.0.0.1:1/?token=x", cmd)
        self.assertIn(f"--class={editor.APP_CLASS}", cmd)
        self.assertTrue(any(a.startswith("--user-data-dir=") for a in cmd))

    def test_falls_back_without_chromium(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(editor.app_window_command("u"), ["xdg-open", "u"])


class FocusTest(unittest.TestCase):
    def test_focuses_existing_window(self) -> None:
        listing = mock.Mock(stdout='[{"class": "%s", "address": "0x1"}]' % editor.APP_CLASS)
        with mock.patch("subprocess.run", side_effect=[listing, mock.Mock()]) as run:
            self.assertTrue(editor.focus_existing_window())
        self.assertIn('"address:0x1"', run.call_args_list[1].args[0][2])

    def test_no_window_means_open_new(self) -> None:
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout="[]")):
            self.assertFalse(editor.focus_existing_window())


class MatchTest(unittest.TestCase):
    def test_main_profile_app_is_not_ours(self) -> None:
        self.assertFalse(editor.is_settings_window({"class": "chromium", "pid": 1}))


class SizeTest(unittest.TestCase):
    def test_small_screen_is_85_percent(self) -> None:
        mons = [{"id": 0, "width": 1024, "height": 640, "scale": 1}]
        self.assertEqual(editor.float_size(0, mons), (870, 544))

    def test_big_screen_is_capped(self) -> None:
        mons = [{"id": 0, "width": 2880, "height": 1800, "scale": 4 / 3}]
        self.assertEqual(editor.float_size(0, mons), (1400, 1000))


class WaylandAndFloatingTest(unittest.TestCase):
    def test_wayland_requires_our_separate_profile(self):
        client = {"class": "chrome-127.0.0.1__-Default", "pid": 42}
        with mock.patch.object(editor.Path, "read_bytes", return_value=b"chromium\0--user-data-dir=/home/demo/.local/state/jade-rain/settings-browser\0"):
            self.assertTrue(editor.is_settings_window(client))
        with mock.patch.object(editor.Path, "read_bytes", return_value=b"chromium\0--user-data-dir=/home/demo/.config/chromium\0"):
            self.assertFalse(editor.is_settings_window(client))
        with mock.patch.object(editor.Path, "read_bytes", side_effect=OSError):
            self.assertFalse(editor.is_settings_window(client))

    def test_rotated_monitor_uses_logical_size(self):
        mons = [{"id": 1, "width": 1920, "height": 1080, "scale": 2, "transform": 1}]
        self.assertEqual(editor.float_size(1, mons), (459, 816))

    def test_floating_targets_only_our_address_with_lua_dispatch(self):
        listing = mock.Mock(stdout='[{"class":"chromium","address":"0x2"},{"class":"%s","address":"0x1","monitor":0}]' % editor.APP_CLASS)
        with mock.patch("subprocess.run", return_value=listing), mock.patch.object(editor, "_dispatch") as dispatch, mock.patch.object(editor, "float_size", return_value=(1400, 1000)):
            self.assertTrue(editor.float_window_when_ready())
        self.assertEqual(dispatch.call_count, 3)
        calls = [c.args[0] for c in dispatch.call_args_list]
        self.assertIn('hl.dsp.window.float', calls[0])
        self.assertIn('x = 1400, y = 1000', calls[1])
        self.assertIn('hl.dsp.window.center', calls[2])
        self.assertTrue(all('address:0x1' in c and 'address:0x2' not in c for c in calls))

    def test_focus_short_circuits_without_starting_a_server(self):
        with mock.patch.object(editor, "os_display", return_value=True), mock.patch.object(editor, "focus_existing_window", return_value=True), mock.patch.object(editor, "EditorServer") as server:
            self.assertEqual(editor.serve(), 0)
        server.assert_not_called()
