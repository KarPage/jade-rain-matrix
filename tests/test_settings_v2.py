"""Real editor HTTP contracts for the simplified UI."""
import http.client
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jade_rain.editor import EditorServer
from jade_rain.config import config_dir


class SettingsV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HOME": self.tmp.name,
            "XDG_CONFIG_HOME": self.tmp.name + "/config", "XDG_STATE_HOME": self.tmp.name + "/state"})
        self.env.start()
        self.server = EditorServer()
        self.server.start()
        self.port = self.server.httpd.server_address[1]

    def tearDown(self):
        self.server.close()
        self.env.stop()
        self.tmp.cleanup()

    def request(self, path, body=None, **headers):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET" if body is None else "POST", path,
            body=None if body is None else json.dumps(body), headers=headers)
        response = conn.getresponse()
        status, raw = response.status, response.read()
        conn.close()
        return status, raw

    def test_preview_is_first_and_advanced_is_collapsed(self):
        status, raw = self.request("/?token=" + self.server.token)
        self.assertEqual(status, 200)
        page = raw.decode()
        self.assertIn('<canvas id="preview"', page)
        self.assertLess(page.index('<canvas id="preview"'), page.index('id="mode-buttons"'))
        self.assertIn('<details id="advanced">', page)
        self.assertIn('How often your words show', page)
        self.assertIn('Save changes', page)
        self.assertIn('Reset to defaults', page)

    def test_scene_uses_real_renderer_and_never_writes_settings(self):
        status, raw = self.request('/api/scene', {"token": self.server.token, "mode": "live",
            "width": 640, "height": 240, "form": {"phrases": "Stay curious", "glyph_set": "digits", "mix": 1}})
        self.assertEqual(status, 200)
        scene = json.loads(raw)
        self.assertTrue(scene['atlas'].startswith('data:image/png;base64,'))
        self.assertEqual(scene['frames'], 640)
        self.assertGreater(len(scene['streams']), 0)
        self.assertTrue(scene['rain'])
        self.assertTrue(any(stream['words'] for stream in scene['streams']))
        self.assertFalse((config_dir() / 'config.toml').exists())

    def test_scene_is_token_and_origin_gated(self):
        self.assertEqual(self.request('/api/scene', {"token": "wrong", "form": {}})[0], 403)
        self.assertEqual(self.request('/api/scene', {"token": self.server.token, "form": {}},
            Origin='http://foreign.example')[0], 403)
        self.assertEqual(self.request('/api/scene', {"token": self.server.token, "form": {}},
            Host='foreign.example')[0], 403)

    def test_scene_rejects_invalid_settings(self):
        status, raw = self.request('/api/scene', {"token": self.server.token, "form": {"speed": 99}})
        self.assertEqual(status, 400)
        self.assertFalse(json.loads(raw)['ok'])

    def test_reset_returns_form_without_needing_a_reload(self):
        status, raw = self.request('/api/reset', {"token": self.server.token, "profile": "jade", "mode": "light"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['form']['color_preset'], 'paper')

    def test_scene_updates_density_speed_colors_and_logo(self):
        base = {"token": self.server.token, "mode": "live", "width": 480, "height": 240}
        a = json.loads(self.request('/api/scene', dict(base, form={"density": .2, "speed": 1}))[1])
        b = json.loads(self.request('/api/scene', dict(base, form={"density": 1.5, "speed": 4,
            "primary": "#ff4422", "background": "#030405"}))[1])
        self.assertLess(len(a['streams']), len(b['streams']))
        self.assertEqual(b['cycles'], 4)
        self.assertEqual(b['background'], [3., 4., 5.])
        self.assertNotEqual(a['ramp'], b['ramp'])

    def test_save_all_mode_drafts_in_one_transaction(self):
        payload = {"token": self.server.token, "profile": "jade", "mode": "still",
            "form": {"phrases": "Still word"}, "forms": {
                "live": {"phrases": "Live word", "speed": 3}, "still": {"phrases": "Still word"}}}
        self.assertEqual(self.request('/api/save', payload)[0], 200)
        from jade_rain.config import load_document
        document = load_document()
        self.assertEqual(document.profiles['jade'].modes['live']['phrases'], 'Live word')
        self.assertEqual(document.profiles['jade'].modes['still']['phrases'], 'Still word')
        self.assertEqual(document.mode, 'still')
        before = document.path.read_bytes()
        payload['forms']['light'] = {"speed": 99}
        self.assertEqual(self.request('/api/save', payload)[0], 400)
        self.assertEqual(document.path.read_bytes(), before)

    def test_explicit_empty_fields_clear_inherited_customization(self):
        from jade_rain.config import ConfigDocument, Profile, save_document, load_settings
        doc = ConfigDocument('jade', 'live', {'jade': Profile('jade', {
            'primary': '#ff0000', 'phrases': 'Old words', 'glyphs': 'OLD'}, {})}, None)
        save_document(doc)
        self.request('/api/save', {"token": self.server.token, "profile": "jade", "mode": "live",
            "form": {"primary": "", "phrases": "", "glyphs": "", "color_preset": "theme"}})
        settings = load_settings()
        self.assertEqual(settings.primary, '')
        self.assertEqual(settings.phrases, '')
        self.assertEqual(settings.glyphs, '')

    def test_replacing_a_logo_never_overwrites_the_saved_logo_before_save(self):
        import base64
        import io
        from PIL import Image
        def upload(color):
            data = io.BytesIO()
            Image.new('RGBA', (8,8), color).save(data, format='PNG')
            status, raw = self.request('/api/logo', {"token": self.server.token, "name": "same.png",
                "data": base64.b64encode(data.getvalue()).decode()})
            self.assertEqual(status, 200)
            return Path(json.loads(raw)['logo'])
        first = upload('white')
        previous = first.read_bytes()
        second = upload('green')
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), previous)

    def test_malformed_content_length_returns_a_plain_error(self):
        self.assertEqual(self.request('/api/scene', {}, **{'Content-Length': 'bad'})[0], 400)


if __name__ == '__main__': unittest.main()
