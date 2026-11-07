"""Local editor for Jade Rain Matrix.

This is a page on 127.0.0.1 served by the Python standard library. Omarchy's
base set includes python-gobject, but not GTK4, so a GTK window would be a
new package. The page adds none. It does not load anything from the network.
A token in the address stops other local programs from saving over the config.
"""

from __future__ import annotations

import base64
import hmac
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


def serve(open_browser: bool = True) -> int:
    server = EditorServer()
    server.start()
    address = server.url()
    print(address)
    print("local only. Ctrl+C closes the editor.", file=sys.stderr)
    if open_browser and (os_display()):
        subprocess.Popen(
            ["xdg-open", address],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        server.thread.join()
    except KeyboardInterrupt:
        print("", file=sys.stderr)
    finally:
        server.close()
    return 0


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
            length = int(self.headers.get("Content-Length", "0") or "0")
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
                if path == "/api/preview":
                    image = _preview(payload)
                    self._send(200, image, "image/png")
                    return
                if path == "/api/save":
                    settings = _save(payload)
                    self._json({"ok": True, "profile": settings.profile, "mode": settings.display_mode})
                    return
                if path == "/api/reset":
                    settings = reset_mode(str(payload.get("profile", "jade")), str(payload.get("mode", "live")))
                    self._json({"ok": True, "profile": settings.profile, "mode": settings.display_mode})
                    return
                if path == "/api/import":
                    count = _import_file(str(payload.get("path", "")))
                    self._json({"ok": True, "phrases": count})
                    return
                if path == "/api/logo":
                    stored = _store_logo(str(payload.get("name", "logo")), str(payload.get("data", "")))
                    self._json({"ok": True, "logo": stored})
                    return
                if path == "/api/close":
                    self._json({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
            except (ValueError, OSError, FileNotFoundError) as error:
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
            self.end_headers()
            self.wfile.write(body)

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
            "credit": CREDIT_TEXT,
            "sourceUrl": SOURCE_URL,
            "sourceProfile": SOURCE_PROFILE,
            "version": __version__,
        }
    ).replace("<", "\\u003c")
    return _HTML.replace("/*__STATE__*/", payload)


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
    return apply_mode_form(profile, mode, form)


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


def _preview(payload: dict[str, object]) -> bytes:
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
        frames=4,
        words=words,
        source_phrases=source,
        theme_file=colors_file(),
        density=settings.density,
    )
    buffer = io.BytesIO()
    Image.fromarray(scene.frame(1), "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


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
    destination = config_dir() / "logos" / f"{safe}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(raw)
    temporary.replace(destination)
    return str(destination)


_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jade Rain Matrix</title>
<style>
  :root {
    color-scheme: dark;
    --bg:#0d0204;
    --field:#12080c;
    --ink:#e7fff4;
    --muted:#8fbfa8;
    --jade:#3fe0a4;
    --line:#1e4a3a;
    --font: ui-monospace, "JetBrains Mono", "Noto Sans Mono", monospace;
  }
  * { box-sizing: border-box; border-radius:0 !important; }
  html, body { height:100%; }
  body { margin:0; background:var(--bg); color:var(--ink); font:13px/1.45 var(--font); }
  main { display:grid; grid-template-columns: minmax(300px, 380px) minmax(0, 1fr); height:100vh; }
  form { height:100vh; overflow:auto; padding:18px 18px 28px; border-right:1px solid var(--line); }
  aside { position:relative; height:100vh; background:#0d0204; overflow:hidden; }
  h1 { margin:0; font-size:15px; font-weight:500; letter-spacing:.14em; text-transform:uppercase; }
  p.lead { margin:6px 0 0; color:var(--muted); }
  h2 { margin:18px 0 8px; padding-top:10px; border-top:1px solid var(--line); color:var(--jade); font-size:11px; font-weight:500; letter-spacing:.16em; text-transform:uppercase; }
  label { display:block; margin:10px 0 4px; color:var(--muted); }
  .hint { color:var(--jade); }
  input, select, textarea, button {
    width:100%;
    background:var(--field);
    color:var(--ink);
    border:1px solid var(--line);
    border-radius:0;
    padding:7px 8px;
    font:inherit;
    accent-color:var(--jade);
    outline:none;
  }
  textarea { min-height:88px; resize:vertical; }
  input:focus, select:focus, textarea:focus, button:focus { border-color:var(--jade); }
  select {
    appearance:none;
    background-image:linear-gradient(45deg, transparent 50%, var(--jade) 50%), linear-gradient(135deg, var(--jade) 50%, transparent 50%);
    background-position:calc(100% - 14px) 55%, calc(100% - 8px) 55%;
    background-size:6px 6px, 6px 6px;
    background-repeat:no-repeat;
    padding-right:22px;
  }
  input[type="range"] {
    appearance:none;
    -webkit-appearance:none;
    height:16px;
    padding:0;
    background:transparent;
    border:0;
  }
  input[type="range"]::-webkit-slider-runnable-track { height:1px; background:var(--jade); border-radius:0; }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance:none;
    width:8px; height:14px; margin-top:-6px;
    background:var(--jade); border:0; border-radius:0;
  }
  input[type="range"]::-moz-range-track { height:1px; background:var(--jade); border:0; border-radius:0; }
  input[type="range"]::-moz-range-thumb { width:8px; height:14px; background:var(--jade); border:0; border-radius:0; }
  input[type="color"] { padding:0; height:28px; }
  input[type="color"]::-webkit-color-swatch-wrapper { padding:0; border-radius:0; }
  input[type="color"]::-webkit-color-swatch { border:0; border-radius:0; }
  input[type="file"] { padding:6px; }
  input[type="file"]::file-selector-button,
  input[type="file"]::-webkit-file-upload-button {
    border-radius:0;
    border:1px solid var(--line);
    background:transparent;
    color:var(--ink);
    font:inherit;
    padding:4px 8px;
  }
  .row { display:grid; grid-template-columns:1fr 72px; gap:8px; align-items:center; }
  .actions { display:flex; gap:8px; margin-top:16px; }
  button { width:auto; background:transparent; color:var(--ink); cursor:pointer; }
  button.primary { background:var(--jade); color:#062016; border-color:var(--jade); }
  img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; background:#0d0204; border-radius:0; }
  .status { min-height:1.4em; margin:8px 0 0; color:var(--jade); }
  .about {
    position:fixed; z-index:2; left:18px; top:18px; width:min(440px, calc(100vw - 36px));
    background:#0d0204; border:1px solid var(--jade); padding:14px 16px; color:var(--muted);
  }
  .about p { margin:0 0 10px; }
  a { color:var(--jade); }
  @media (max-width: 800px) {
    main { grid-template-columns:1fr; height:auto; }
    form { height:auto; border-right:0; }
    aside { height:56vw; min-height:220px; }
  }
</style>
</head>
<body>
<main>
  <form id="editor">
    <h1>Jade Rain Matrix</h1>
    <p class="lead">Saved on this computer.</p>
    <label for="profile">Profile</label>
    <select id="profile" name="profile"></select>
    <label for="new-profile">Save as a new profile</label>
    <input id="new-profile" maxlength="32" placeholder="blank keeps the profile above" autocomplete="off">
    <label for="mode">Mode <span class="hint">1 live · 2 still · 3 light · 4 saver</span></label>
    <select id="mode" name="mode"></select>
    <h2>Text</h2>
    <label for="phrases">Words and phrases, one per line</label>
    <textarea id="phrases" autofocus></textarea>
    <label for="mix">Phrase mix <span id="mix-out"></span></label>
    <input id="mix" type="range" min="0" max="1" step="0.01">
    <label for="glyph">Glyphs</label>
    <select id="glyph">
      <option value="katakana">katakana</option>
      <option value="latin">latin</option>
      <option value="digits">digits</option>
      <option value="custom">custom</option>
    </select>
    <label for="glyphs">Custom glyphs</label>
    <input id="glyphs" maxlength="64" placeholder="used when glyphs is custom">
    <h2>Colors</h2>
    <label for="preset">Preset</label>
    <select id="preset">
      <option value="theme">theme</option>
      <option value="jade">jade</option>
      <option value="matrix">matrix</option>
      <option value="ink">ink</option>
      <option value="paper">paper</option>
    </select>
    <label for="primary">Primary</label>
    <div class="row"><input id="primary" maxlength="7" placeholder="#3fe0a4" spellcheck="false"><input id="primary-pick" type="color" aria-label="primary picker" tabindex="0"></div>
    <label for="highlight">Highlight</label>
    <div class="row"><input id="highlight" maxlength="7" placeholder="#e9fff6" spellcheck="false"><input id="highlight-pick" type="color" aria-label="highlight picker"></div>
    <label for="background">Background</label>
    <div class="row"><input id="background" maxlength="7" placeholder="#0d0204" spellcheck="false"><input id="background-pick" type="color" aria-label="background picker"></div>
    <h2>Logo</h2>
    <label for="logo">Path</label>
    <input id="logo" placeholder="PNG or SVG on this computer" spellcheck="false">
    <label for="logo-file">File</label>
    <input id="logo-file" type="file" accept="image/png,image/svg+xml,.png,.svg">
    <label for="logo-style">Style</label>
    <select id="logo-style"><option value="watermark">watermark</option><option value="sprite">glyph sprite</option></select>
    <label for="logo-size">Size <span id="size-out"></span></label>
    <input id="logo-size" type="range" min="40" max="800" step="10">
    <label for="logo-opacity">Opacity <span id="opacity-out"></span></label>
    <input id="logo-opacity" type="range" min="0" max="1" step="0.01">
    <h2>Motion</h2>
    <label for="density">Density <span id="density-out"></span></label>
    <input id="density" type="range" min="0.2" max="1.5" step="0.05">
    <label for="speed">Speed <span id="speed-out"></span></label>
    <input id="speed" type="range" min="1" max="4" step="1">
    <h2>Imported text</h2>
    <label for="text-mode">Source file</label>
    <select id="text-mode"><option value="off">off</option><option value="mix">mix</option><option value="replace">replace</option></select>
    <label for="import-path">File on this computer</label>
    <div class="row"><input id="import-path" placeholder="/path/to/book.txt" spellcheck="false"><button id="import" type="button">Import</button></div>
    <div class="actions">
      <button class="primary" type="submit">Save</button>
      <button id="reset" type="button">Reset mode</button>
      <button id="about" type="button">About</button>
    </div>
    <p class="status" id="status" role="status"></p>
    <section class="about" id="about-panel" hidden>
      <p id="credit"></p>
      <p><a id="source-url" href=""></a><br><a id="source-profile" href=""></a></p>
      <p>Jade Rain Matrix <span id="version"></span>. The editor never leaves this machine. Esc closes this panel, then the window.</p>
    </section>
  </form>
  <aside>
    <img id="frame" alt="Live preview of the rain">
  </aside>
</main>
<script>
const STATE = /*__STATE__*/;
const $ = (id) => document.getElementById(id);
function fillSelect(el, values, current) {
  el.replaceChildren();
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    if (value === current) option.selected = true;
    el.appendChild(option);
  });
}
function readForm() {
  return {
    color_preset: $("preset").value,
    primary: $("primary").value.trim(),
    highlight: $("highlight").value.trim(),
    background: $("background").value.trim(),
    logo: $("logo").value.trim(),
    logo_size: Number($("logo-size").value),
    logo_opacity: Number($("logo-opacity").value),
    logo_style: $("logo-style").value,
    word_scale: Number(STATE.form.word_scale),
    text_mode: $("text-mode").value,
    text_density: Number(STATE.form.text_density),
    mix: Number($("mix").value),
    density: Number($("density").value),
    speed: Number($("speed").value),
    glyph_set: $("glyph").value,
    glyphs: $("glyphs").value,
    phrases: $("phrases").value
  };
}
function writeForm(form) {
  $("phrases").value = form.phrases || "";
  $("mix").value = form.mix;
  $("glyph").value = form.glyph_set;
  $("glyphs").value = form.glyphs || "";
  $("preset").value = form.color_preset;
  $("primary").value = form.primary || "";
  $("highlight").value = form.highlight || "";
  $("background").value = form.background || "";
  $("logo").value = form.logo || "";
  $("logo-style").value = form.logo_style;
  $("logo-size").value = form.logo_size;
  $("logo-opacity").value = form.logo_opacity;
  $("density").value = form.density;
  $("speed").value = form.speed;
  $("text-mode").value = form.text_mode;
  syncPickers();
  syncLabels();
}
function syncLabels() {
  $("mix-out").textContent = Number($("mix").value).toFixed(2);
  $("size-out").textContent = $("logo-size").value;
  $("opacity-out").textContent = Number($("logo-opacity").value).toFixed(2);
  $("density-out").textContent = Number($("density").value).toFixed(2);
  $("speed-out").textContent = $("speed").value;
}
function syncPickers() {
  ["primary", "highlight", "background"].forEach((name) => {
    const hex = $(name).value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(hex)) $(name + "-pick").value = hex;
  });
}
async function post(path, extra, image) {
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(Object.assign({token: STATE.token, profile: $("profile").value, new_profile: $("new-profile").value.trim(), mode: $("mode").value, form: readForm()}, extra || {}))
  });
  if (image) return response;
  return response.json();
}
function say(text) { $("status").textContent = text; }
fillSelect($("profile"), STATE.profiles, STATE.profile);
fillSelect($("mode"), STATE.modes, STATE.mode);
writeForm(STATE.form);
$("credit").textContent = STATE.credit;
$("source-url").textContent = STATE.sourceUrl;
$("source-url").href = STATE.sourceUrl;
$("source-profile").textContent = "@iamdothash";
$("source-profile").href = STATE.sourceProfile;
$("version").textContent = STATE.version;
document.querySelectorAll("input[type=range]").forEach((el) => el.addEventListener("input", syncLabels));
["primary", "highlight", "background"].forEach((name) => {
  $(name).addEventListener("input", syncPickers);
  $(name + "-pick").addEventListener("input", () => { $(name).value = $(name + "-pick").value; });
});
$("editor").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = await post("/api/save");
  say(body.ok ? "Saved " + body.profile + " / " + body.mode : body.error);
});
function typingTarget(target) {
  if (!target || !target.tagName) return false;
  if (target.tagName === "TEXTAREA") return true;
  return target.tagName === "INPUT" && (target.type === "text" || target.type === "" || target.type === "search");
}
document.addEventListener("keydown", async (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    $("editor").requestSubmit();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    if (!$("about-panel").hidden) { $("about-panel").hidden = true; return; }
    try { await post("/api/close"); } catch (error) {}
    window.close();
    return;
  }
  if (event.ctrlKey || event.metaKey || event.altKey || typingTarget(event.target)) return;
  const modes = { "1": "live", "2": "still", "3": "light", "4": "screensaver" };
  const next = modes[event.key];
  if (!next || next === $("mode").value) return;
  event.preventDefault();
  $("mode").value = next;
  reloadMode();
});
let previewTimer = 0;
let previewGen = 0;
function colorsReady() {
  return ["primary", "highlight", "background"].every((name) => {
    const value = $(name).value.trim();
    return value === "" || /^#[0-9a-fA-F]{6}$/.test(value);
  });
}
function schedulePreview() {
  if (!colorsReady()) return;
  window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(drawPreview, 280);
}
async function drawPreview() {
  const gen = ++previewGen;
  const pane = document.querySelector("aside");
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(160, Math.round(pane.clientWidth * ratio));
  const height = Math.max(100, Math.round(pane.clientHeight * ratio));
  const response = await post("/api/preview", {width: width, height: height}, true);
  if (gen !== previewGen) return;
  if (!response.ok) {
    say("Preview failed");
    return;
  }
  const blob = await response.blob();
  const previous = $("frame").src;
  $("frame").src = URL.createObjectURL(blob);
  if (previous.startsWith("blob:")) URL.revokeObjectURL(previous);
}
$("editor").addEventListener("input", schedulePreview);
$("editor").addEventListener("change", schedulePreview);
$("reset").addEventListener("click", async () => {
  const body = await post("/api/reset");
  say(body.ok ? "Reset " + body.mode + ". Reload to see it." : body.error);
});
$("about").addEventListener("click", () => { $("about-panel").hidden = !$("about-panel").hidden; });
$("import").addEventListener("click", async () => {
  const body = await post("/api/import", {path: $("import-path").value});
  if (body.ok) { $("text-mode").value = "mix"; schedulePreview(); say("Imported " + body.phrases + " phrases. They stay in source.txt."); }
  else say(body.error);
});
$("logo-file").addEventListener("change", async () => {
  const file = $("logo-file").files[0];
  if (!file) return;
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  const body = await post("/api/logo", {name: file.name, data: btoa(binary)});
  if (body.ok) { $("logo").value = body.logo; schedulePreview(); say("Logo stored locally."); }
  else say(body.error);
});
function reloadMode() {
  const url = new URL(location.href);
  url.searchParams.set("token", STATE.token);
  url.searchParams.set("profile", $("profile").value);
  url.searchParams.set("mode", $("mode").value);
  location.href = url.toString();
}
$("profile").addEventListener("change", reloadMode);
$("mode").addEventListener("change", reloadMode);
window.addEventListener("resize", schedulePreview);
if (location.hash === "#about") $("about-panel").hidden = false;
$("phrases").focus();
drawPreview();
</script>
</body>
</html>
"""
