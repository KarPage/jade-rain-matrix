import http.client
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from jade_rain.editor import EditorServer, local_request
from jade_rain.config import config_dir


class EditorTests(unittest.TestCase):
    def test_editor_is_local_and_token_gated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            os.environ["HOME"] = str(home)
            os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
            os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
            server = EditorServer()
            server.start()
            try:
                host, port = server.httpd.server_address
                self.assertEqual(host, "127.0.0.1")
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
                self.assertEqual(blocked.exception.code, 403)
                page = urllib.request.urlopen(server.url(), timeout=5).read().decode("utf-8")
                self.assertIn("Jade Rain Matrix", page)
                self.assertIn("@iamdothash", page)
                self.assertIn("https://github.com/bjarneo/omarchy-matrix-theme", page)
                self.assertIn("border-radius:0", page)
                self.assertNotIn("border-radius:6", page)
                self.assertNotIn("border-radius:8", page)
                for heading in ("Your words", "Colors", "Your logo", "Motion", "Imported text"):
                    self.assertIn(heading, page)
                wide = self._post(
                    port,
                    "/api/preview",
                    {"token": server.token, "mode": "live", "form": {}, "width": 1600, "height": 800},
                )
                self.assertTrue(wide.startswith(b"\x89PNG"))
                preview = self._post(port, "/api/preview", {"token": server.token, "mode": "live", "form": {}})
                self.assertTrue(preview.startswith(b"\x89PNG"))
                saved = json.loads(
                    self._post(
                        port,
                        "/api/save",
                        {
                            "token": server.token,
                            "profile": "jade",
                            "mode": "screensaver",
                            "form": {"color_preset": "matrix", "phrases": "own rain\n", "speed": 1},
                        },
                    )
                )
                self.assertTrue(saved["ok"])
                self.assertEqual(saved["mode"], "screensaver")
                text = (config_dir() / "config.toml").read_text(encoding="utf-8")
                self.assertIn("[profiles.jade.modes.screensaver]", text)
                self.assertIn("own rain", text)
            finally:
                server.close()

    def test_host_and_origin_must_be_this_loopback(self) -> None:
        self.assertTrue(local_request("127.0.0.1:9", None, 9))
        self.assertTrue(local_request("localhost:9", None, 9))
        self.assertTrue(local_request("127.0.0.1:9", "http://127.0.0.1:9", 9))
        self.assertFalse(local_request(None, None, 9))
        self.assertFalse(local_request("evil.example", None, 9))
        self.assertFalse(local_request("127.0.0.1", None, 9))
        self.assertFalse(local_request("127.0.0.1:8", None, 9))
        self.assertFalse(local_request("127.0.0.1.evil:9", None, 9))
        self.assertFalse(local_request("127.0.0.1:9", "http://evil.example", 9))
        self.assertFalse(local_request("127.0.0.1:9", "http://localhost:9", 9))
        self.assertFalse(local_request("127.0.0.1:9", "null", 9))
        self.assertFalse(local_request("127.0.0.1:9", "https://127.0.0.1:9", 9))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            os.environ["HOME"] = str(home)
            os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
            os.environ["XDG_STATE_HOME"] = str(home / ".local" / "state")
            server = EditorServer()
            server.start()
            try:
                host, port = server.httpd.server_address
                self.assertEqual(host, "127.0.0.1")
                self.assertEqual(self._status(port, "GET", f"/?token={server.token}", {"Host": "evil.example"}), 403)
                self.assertEqual(
                    self._status(
                        port,
                        "POST",
                        "/api/import",
                        {"Host": f"127.0.0.1:{port}", "Origin": "http://evil.example", "Content-Type": "application/json"},
                        json.dumps({"token": server.token, "path": ""}),
                    ),
                    403,
                )
                self.assertEqual(
                    self._status(port, "GET", f"/?token={server.token}", {"Host": f"localhost:{port}"}),
                    200,
                )
                self.assertEqual(
                    self._status(
                        port,
                        "GET",
                        f"/?token={server.token}",
                        {"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"},
                    ),
                    200,
                )
            finally:
                server.close()

    def _status(self, port: int, method: str, path: str, headers: dict[str, str], body: str | None = None) -> int:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response.read()
        status = response.status
        connection.close()
        return status

    def _post(self, port: int, path: str, payload: dict[str, object]) -> bytes:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=30).read()


if __name__ == "__main__":
    unittest.main()
