"""Local editor for Jade Rain Matrix.

This is a page on 127.0.0.1 served by the Python standard library. Omarchy's
base set includes python-gobject, but not GTK4, so a GTK window would be a
new package. The page adds none. It does not load anything from the network.
A token in the address stops other local programs from saving over the config.
"""

from __future__ import annotations

import base64
from copy import deepcopy
import hmac
import hashlib
import io
import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from jade_rain import __version__
from jade_rain.compose import scene_from_settings
from jade_rain.config import (
    DISPLAY_MODES,
    ConfigDocument,
    Profile,
    Settings,
    _settings_from_document,
    _profile_name,
    _display_mode,
    save_document,
    factory_values,
    factory_modes,
    apply_mode_form,
    config_dir,
    form_values,
    load_document,
    load_words,
    parse_words,
    reset_mode,
)
from jade_rain.credit import CREDIT_TEXT, SOURCE_PROFILE, SOURCE_URL
from jade_rain.paths import colors_file
from jade_rain.preview import canvas_scene
from jade_rain.textsrc import extract_text, load_source_phrases, write_source

_MAX_BODY = 2_500_000
_PREVIEW_WIDTH = 960
_PREVIEW_HEIGHT = 600
_PREVIEW_LONG_EDGE = 840


class EditorServer:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(24)
        handler = _handler(self.token)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/?token={self.token}"


def is_settings_window(client: dict) -> bool:
    """Our window: the X11 class, or on Wayland Chromium's URL app-id plus our own profile."""
    cls = client.get("class", "")
    if cls == APP_CLASS:
        return True
    if not cls.startswith("chrome-127.0.0.1"):
        return False
    try:
        cmdline = Path(f"/proc/{int(client.get('pid', 0))}/cmdline").read_bytes()
    except (OSError, ValueError):
        return False
    return b"jade-rain/settings-browser" in cmdline


def _dispatch(expression: str) -> None:
    subprocess.run(["hyprctl", "dispatch", expression], capture_output=True, timeout=3)


def float_size(monitor_id, monitors=None) -> tuple[int, int]:
    """85% of the window's monitor in logical pixels, capped at 1400x1000."""
    if monitors is None:
        try:
            out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3).stdout
            monitors = json.loads(out or "[]")
        except (OSError, ValueError, subprocess.SubprocessError):
            monitors = []
    for mon in monitors:
        if mon.get("id") == monitor_id or (monitor_id is None and mon.get("focused")):
            scale = float(mon.get("scale") or 1)
            width, height = mon["width"] / scale, mon["height"] / scale
            if mon.get("transform", 0) % 2:
                width, height = height, width
            return min(1400, int(width * 0.85)), min(1000, int(height * 0.85))
    return 950, 600


def float_window_when_ready(timeout: float = 15.0) -> bool:
    """Float, size to 85% of the monitor and center our app window once it maps. No config edits."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3).stdout
            clients = json.loads(out or "[]")
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
        for client in clients:
            if is_settings_window(client) and client.get("address"):
                win = f'"address:{client["address"]}"'
                _dispatch(f'hl.dsp.window.float({{ action = "on", window = {win} }})')
                w, h = float_size(client.get("monitor"))
                _dispatch(f'hl.dsp.window.resize({{ x = {w}, y = {h}, window = {win} }})')
                _dispatch(f'hl.dsp.window.center({{ window = {win} }})')
                return True
        time.sleep(0.25)
    return False


def focus_existing_window() -> bool:
    """Focus an open settings app window instead of opening a second one."""
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3).stdout
        clients = json.loads(out or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    for client in clients:
        if is_settings_window(client) and client.get("address"):
            address = client['address']
            _dispatch(f'hl.dsp.focus({{ window = "address:{address}" }})')
            return True
    return False


def serve(open_browser: bool = True) -> int:
    if open_browser and os_display() and focus_existing_window():
        print("settings window already open; focused it.", file=sys.stderr)
        return 0
    server = EditorServer()
    server.start()
    address = server.url()
    print(address)
    print("local only. Ctrl+C closes the editor.", file=sys.stderr)
    if open_browser and (os_display()):
        subprocess.Popen(
            app_window_command(address),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=float_window_when_ready, daemon=True).start()
    try:
        server.thread.join()
    except KeyboardInterrupt:
        print("", file=sys.stderr)
    finally:
        server.close()
    return 0


APP_CLASS = "io.github.karpage.jade-rain-settings"


def app_window_command(address: str) -> list[str]:
    """A chrome-less Chromium app window with its own class and profile.

    A separate profile keeps it out of the main browser so the class sticks.
    Falls back to xdg-open when Chromium is not installed.
    """
    import shutil

    browser = shutil.which("chromium")
    if not browser:
        return ["xdg-open", address]
    profile = Path.home() / ".local" / "state" / "jade-rain" / "settings-browser"
    profile.mkdir(parents=True, exist_ok=True)
    return [
        browser,
        f"--app={address}",
        f"--class={APP_CLASS}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def os_display() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def local_request(host_header: str | None, origin_header: str | None, port: int) -> bool:
    """True when Host is this loopback port and Origin, if sent, matches it.

    A DNS-rebinding page arrives with a foreign Host. A cross-site form arrives
    with a foreign Origin. Missing Origin is allowed for non-browser clients.
    """
    parsed = _host_and_port(host_header)
    if parsed is None:
        return False
    host, seen_port = parsed
    if host not in {"127.0.0.1", "localhost"} or seen_port != port:
        return False
    if origin_header is None:
        return True
    origin = origin_header.strip()
    if not origin.lower().startswith("http://"):
        return False
    origin_parsed = _host_and_port(origin[7:])
    if origin_parsed is None:
        return False
    origin_host, origin_port = origin_parsed
    return origin_host == host and origin_port == port


def _host_and_port(value: str | None) -> tuple[str, int] | None:
    if value is None:
        return None
    text = value.strip()
    if text == "" or any(character in text for character in " ,@/\\?#[]"):
        return None
    host, separator, port_text = text.rpartition(":")
    if separator != ":" or host == "" or not port_text.isdigit():
        return None
    return host.casefold(), int(port_text)


def _handler(token: str) -> type[BaseHTTPRequestHandler]:
    mutation_lock = threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _local(self) -> bool:
            address = self.server.server_address
            port = address[1]
            if isinstance(port, int) and local_request(self.headers.get("Host"), self.headers.get("Origin"), port):
                return True
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return False

        def do_GET(self) -> None:
            if not self._local():
                return
            if not _authorized(self.path, token, None):
                self._send(403, b"forbidden", "text/plain; charset=utf-8")
                return
            path = urlparse(self.path).path
            if path != "/":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
            query = parse_qs(urlparse(self.path).query)
            page = _page(token, query.get("profile", [""])[0], query.get("mode", [""])[0])
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            if not self._local():
                return
            try:
                length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                self._json({"ok": False, "error": "invalid request length"}, status=400)
                return
            if length < 0 or length > _MAX_BODY:
                self._send(413, b"too large", "text/plain; charset=utf-8")
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._send(400, b"bad json", "text/plain; charset=utf-8")
                return
            if not isinstance(payload, dict) or not _token_ok(payload.get("token"), token):
                self._send(403, b"forbidden", "text/plain; charset=utf-8")
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/scene":
                    self._json(_canvas_preview(payload))
                    return
                if path == "/api/preview":
                    image = _preview(payload)
                    self._send(200, image, "image/png")
                    return
                if path == "/api/save":
                    with mutation_lock:
                        settings = _save(payload)
                    self._json({"ok": True, "profile": settings.profile, "mode": settings.display_mode})
                    return
                if path == "/api/reset":
                    with mutation_lock:
                        settings = reset_mode(str(payload.get("profile", "jade")), str(payload.get("mode", "live")))
                    self._json({"ok": True, "profile": settings.profile, "mode": settings.display_mode,
                                "form": _form_from_settings(settings)})
                    return
                if path == "/api/import":
                    with mutation_lock:
                        count = _import_file(str(payload.get("path", "")))
                    self._json({"ok": True, "phrases": count})
                    return
                if path == "/api/logo":
                    with mutation_lock:
                        stored = _store_logo(str(payload.get("name", "logo")), str(payload.get("data", "")))
                    self._json({"ok": True, "logo": stored})
                    return
                if path == "/api/close":
                    self._json({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
                self._json({"ok": False, "error": str(error)}, status=400)
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

        def _json(self, payload: dict[str, object], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._send(status, body, "application/json")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'self'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # An obsolete preview fetch was cancelled by a newer edit.
                pass

    return Handler


def _authorized(path: str, token: str, body_token: object) -> bool:
    query = parse_qs(urlparse(path).query)
    supplied = query.get("token", [""])[0]
    return _token_ok(supplied, token) or _token_ok(body_token, token)


def _token_ok(supplied: object, token: str) -> bool:
    if not isinstance(supplied, str):
        return False
    return hmac.compare_digest(supplied, token)


def _page(token: str, profile: str = "", mode: str = "") -> str:
    document = load_document()
    if profile in document.profiles:
        document.active = profile
    if mode in DISPLAY_MODES:
        document.mode = mode
    settings = _settings_from_document(document)
    form = _form_from_settings(settings)
    payload = json.dumps(
        {
            "token": token,
            "profile": document.active,
            "profiles": list(document.profiles),
            "mode": settings.display_mode,
            "modes": list(DISPLAY_MODES),
            "form": form,
            "forms": {name: _form_from_settings(_settings_from_document(
                ConfigDocument(document.active, name, document.profiles, document.path)
            )) for name in DISPLAY_MODES},
            "credit": CREDIT_TEXT,
            "sourceUrl": SOURCE_URL,
            "sourceProfile": SOURCE_PROFILE,
            "version": __version__,
        }
    ).replace("<", "\\u003c")
    html = Path(__file__).with_name("settings.html").read_text(encoding="utf-8")
    return html.replace("/*__STATE__*/", payload).replace(
        "/*__PREVIEW__*/", Path(__file__).with_name("preview.js").read_text(encoding="utf-8")
    ).replace("/*__EDITOR__*/", Path(__file__).with_name("settings.js").read_text(encoding="utf-8"))


def _form_from_settings(settings: Settings) -> dict[str, object]:
    return {
        "color_preset": settings.color_preset,
        "primary": settings.primary,
        "highlight": settings.highlight,
        "background": settings.background_color,
        "logo": settings.logo,
        "logo_size": settings.logo_size,
        "logo_opacity": 0.33 if settings.logo_opacity is None else settings.logo_opacity,
        "logo_style": settings.logo_style,
        "word_scale": settings.word_scale,
        "text_mode": settings.text_mode,
        "text_density": settings.text_density,
        "mix": CLASSIC if settings.phrase_mix is None else settings.phrase_mix,
        "density": settings.density,
        "speed": settings.speed,
        "glyph_set": settings.glyph_set,
        "glyphs": settings.glyphs,
        "phrases": settings.phrases,
    }


CLASSIC = 0.32


def _save(payload: dict[str, object]) -> Settings:
    profile = str(payload.get("new_profile") or payload.get("profile") or "jade")
    mode = str(payload.get("mode") or "live")
    form = payload.get("form")
    if not isinstance(form, dict):
        raise ValueError("form is missing")
    forms = payload.get("forms")
    if forms is None:
        return apply_mode_form(profile, mode, form)
    if not isinstance(forms, dict) or not forms or len(forms) > len(DISPLAY_MODES):
        raise ValueError("mode settings are missing")
    name, display = _profile_name(profile), _display_mode(mode)
    checked = {}
    for key, value in forms.items():
        if not isinstance(value, dict):
            raise ValueError("mode settings must be a form")
        checked[_display_mode(str(key))] = form_values(value)
    document = load_document()
    if name not in document.profiles:
        source = str(payload.get("profile") or "")
        document.profiles[name] = deepcopy(document.profiles[source]) if source in document.profiles else Profile(name, factory_values(), factory_modes())
        document.profiles[name].name = name
    for key, value in checked.items():
        # Preserve non-editor keys too; no unrelated customization is discarded.
        document.profiles[name].modes.setdefault(key, {}).update(value)
    document.active, document.mode = name, display
    save_document(document)
    return _settings_from_document(document)


def _preview_size(payload: dict[str, object]) -> tuple[int, int]:
    """Pane size, capped so a live preview stays quick. Aspect is kept."""

    def raw(key: str, fallback: int) -> int:
        value = payload.get(key, fallback)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return fallback
        return int(value)

    width = max(2, raw("width", _PREVIEW_WIDTH))
    height = max(2, raw("height", _PREVIEW_HEIGHT))
    scale = min(1.0, _PREVIEW_LONG_EDGE / max(width, height))
    return max(160, int(width * scale)), max(100, int(height * scale))


def _preview_scene(payload: dict[str, object], frames: int = 4):
    form = payload.get("form")
    if not isinstance(form, dict):
        raise ValueError("form is missing")
    mode = str(payload.get("mode") or "live")
    settings = apply_preview(mode, form)
    words = parse_words(settings.phrases) if settings.phrases.strip() else load_words(settings.words_file)
    source: list[str] = []
    if settings.text_mode != "off":
        try:
            source = load_source_phrases()
        except ValueError:
            source = []
    width, height = _preview_size(payload)
    scene = scene_from_settings(
        settings,
        width=width,
        height=height,
        frames=frames,
        words=words,
        source_phrases=source,
        theme_file=colors_file(),
        density=settings.density,
    )
    return scene


def _preview(payload: dict[str, object]) -> bytes:
    scene = _preview_scene(payload)
    buffer = io.BytesIO()
    Image.fromarray(scene.frame(1), "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _canvas_preview(payload: dict[str, object]) -> dict[str, object]:
    scene = _preview_scene(payload, frames=640)
    return canvas_scene(scene, str(payload.get("mode") or "live"))


def apply_preview(mode: str, form: dict[str, object]) -> Settings:
    document = ConfigDocument(
        "preview",
        mode,
        {"preview": Profile("preview", {}, {mode: form_values(form)})},
        None,
    )
    return _settings_from_document(document)


def _import_file(path: str) -> int:
    if not path.strip():
        raise ValueError("choose a text file on this computer")
    phrases = extract_text(Path(path).expanduser())
    if not phrases:
        raise ValueError("no usable phrases in that file")
    write_source(phrases)
    return len(phrases)


def _store_logo(name: str, data: str) -> str:
    if not data:
        raise ValueError("logo file is empty")
    try:
        raw = base64.b64decode(data, validate=True)
    except ValueError as error:
        raise ValueError("logo upload was not valid") from error
    if len(raw) > 2_000_000:
        raise ValueError("logo is larger than 2 MB")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = ".png"
    elif raw.lstrip().startswith(b"<svg") or raw.lstrip().startswith(b"<?xml"):
        suffix = ".svg"
    else:
        raise ValueError("logo must be a PNG or SVG")
    safe = "".join(ch for ch in Path(name).name if ch.isalnum() or ch in "._-")[:40] or "logo"
    # An unsaved replacement must never overwrite the file currently in use.
    digest = hashlib.sha256(raw).hexdigest()[:16]
    destination = config_dir() / "logos" / f"{safe}-{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return str(destination)
