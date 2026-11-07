"""Local text fed into the rain.

.txt and .md are read as text. .epub is a zip of HTML, parsed with the
standard library. .pdf uses pdftotext when that program is on PATH.
Nothing is uploaded. Input is size-capped, never executed, and never passed
through a shell.
"""

from __future__ import annotations

import os
import posixpath
import random
import re
import select
import shutil
import subprocess
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from jade_rain.config import config_dir

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_EXTRACT_BYTES = 2_000_000
MAX_STORED_CHARS = 400_000
MAX_PHRASES = 24
MAX_PHRASE_CHARS = 28
MAX_WORD_CHARS = 18
PHRASE_TOKEN_LIMIT = 100_000
SOURCE_SEED = 20261107
PDF_TIMEOUT_SECONDS = 20
MAX_ZIP_MEMBERS = 4000
MAX_HTML_FILES = 200
MAX_HTML_FILE_BYTES = 1_000_000
MAX_COMPRESSION_RATIO = 80

_PAGE_LINE = re.compile(r"^(?:page\s+)?\d{1,4}(?:\s*/\s*\d{1,4})?$", re.IGNORECASE)
_DASHED_PAGE = re.compile(r"^[\-–—]\s*\d{1,4}\s*[\-–—]$")
_MD_IMAGE = re.compile(r"!\[([^]]{0,80})](?:\([^)]{0,200}\))?")
_MD_LINK = re.compile(r"\[([^]]{0,80})](?:\([^)]{0,200}\))?")
_MD_HEADING = re.compile(r"^#{1,6}\s+")
_HTML_TAG = re.compile(r"<[^>]{0,200}>")
_HREF = re.compile(rb"""href\s*=\s*["']([^"']{1,200})["']""", re.IGNORECASE)
_CHUNK = (3, 2, 4)

PDF_MISSING = (
    "pdftotext is not installed, so this PDF cannot be read. "
    "poppler is not in the Omarchy base packages. "
    "Install it with: omarchy pkg add poppler"
)


class TextRejected(ValueError):
    """The file is the wrong type, too large, or not a usable book."""


def source_path() -> Path:
    return config_dir() / "source.txt"


def pdf_command(tool: str, path: Path) -> list[str]:
    """argv for pdftotext. The path is one argument, never a shell string."""
    return [tool, "-enc", "UTF-8", "-nopgbrk", "-q", str(path), "-"]


def extract_text(path: Path) -> str:
    """Return cleaned prose from a local txt, md, epub, or pdf file."""
    if not path.is_file():
        raise TextRejected(f"not a file: {path}")
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise TextRejected(f"file is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB")
    kind = path.suffix.lower()
    if kind in {".txt", ".md", ".markdown"}:
        raw = _read_text_bytes(path)
        return clean_text(raw, markdown=kind != ".txt")
    if kind == ".epub":
        return clean_text(read_epub(path), markdown=False)
    if kind == ".pdf":
        return clean_text(read_pdf(path), markdown=False)
    raise TextRejected("use a .txt, .md, .epub, or .pdf file")


def clean_text(raw: str, *, markdown: bool) -> str:
    """Drop markup, page numbers, and repeated running headers."""
    text = raw.replace("\x00", " ").replace("\f", "\n").replace("\r\n", "\n").replace("\r", "\n")
    kept: list[str] = []
    in_fence = False
    for raw_line in text.split("\n"):
        fence = raw_line.strip()
        if fence.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = _clean_line(raw_line, markdown=markdown)
        if not line or _PAGE_LINE.match(line) or _DASHED_PAGE.match(line):
            continue
        kept.append(line)
    counts: dict[str, int] = {}
    for line in kept:
        if len(line) > 60 or len(line.split()) > 6:
            continue
        key = line.casefold()
        if key in counts or len(counts) < 20_000:
            counts[key] = counts.get(key, 0) + 1
    body: list[str] = []
    for line in kept:
        key = line.casefold()
        if len(line) <= 60 and counts.get(key, 0) >= 4:
            continue
        body.append(line)
    return "\n".join(body)[:MAX_STORED_CHARS]


def sample_phrases(text: str, *, limit: int = MAX_PHRASES, seed: int = SOURCE_SEED) -> list[str]:
    """Stable subset. The same text and seed always return the same phrases."""
    if limit < 1:
        return []
    picker = random.Random(seed)
    chosen: list[str] = []
    for index, phrase in enumerate(iter_phrases(text)):
        if index >= PHRASE_TOKEN_LIMIT:
            break
        if len(chosen) < limit:
            chosen.append(phrase)
            continue
        pick = picker.randrange(index + 1)
        if pick < limit:
            chosen[pick] = phrase
    return chosen


def iter_phrases(text: str):
    pending: list[str] = []
    step = 0
    seen = 0
    for token in _tokens(text):
        seen += 1
        if seen > PHRASE_TOKEN_LIMIT:
            break
        pending.append(token)
        need = _CHUNK[step % len(_CHUNK)]
        if len(pending) < need:
            continue
        phrase = _fit(pending[:need])
        del pending[:need]
        step += 1
        if phrase:
            yield phrase
    if len(pending) >= 2:
        phrase = _fit(pending)
        if phrase:
            yield phrase


def load_source_phrases(path: Path | None = None) -> list[str]:
    """Sample phrases from the stored source. Missing file yields an empty list."""
    file = path or source_path()
    if not file.is_file() or file.is_symlink():
        return []
    if file.stat().st_size > MAX_INPUT_BYTES:
        raise TextRejected("source.txt is larger than the size cap")
    raw = file.read_text(encoding="utf-8", errors="replace")[: MAX_STORED_CHARS + 2000]
    lines = raw.splitlines()
    index = 0
    if lines and lines[0].startswith("# jade-rain source"):
        while index < len(lines) and lines[index].startswith("#"):
            index += 1
        if index < len(lines) and not lines[index].strip():
            index += 1
    return sample_phrases("\n".join(lines[index:]))


def write_source(origin: Path, cleaned: str) -> Path:
    path = source_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    name = origin.name.replace("\n", " ").replace("\r", " ")[:180]
    header = f"# jade-rain source\n# from: {name}\n# local only, never uploaded\n\n"
    _atomic_write(path, header + cleaned[:MAX_STORED_CHARS])
    return path


def read_pdf(path: Path) -> str:
    tool = shutil.which("pdftotext")
    if not tool:
        raise TextRejected(PDF_MISSING)
    data = _run_capped(pdf_command(tool, path), MAX_EXTRACT_BYTES, PDF_TIMEOUT_SECONDS)
    return data.decode("utf-8", "replace")


def read_epub(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        raise TextRejected("not an epub")
    parts: list[str] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) > MAX_ZIP_MEMBERS:
            raise TextRejected("epub has too many entries")
        known = set(names)
        ordered = _html_members(archive, known)
        for name in ordered[:MAX_HTML_FILES]:
            if not _safe_member(name) or name not in known:
                continue
            info = archive.getinfo(name)
            if info.file_size > MAX_HTML_FILE_BYTES or info.file_size < 0:
                continue
            if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                continue
            if total + info.file_size > MAX_EXTRACT_BYTES:
                break
            total += info.file_size
            raw = archive.read(info)
            parts.append(_html_to_text(raw.decode("utf-8", "replace")))
            if sum(len(part) for part in parts) >= MAX_EXTRACT_BYTES:
                break
    return "\n".join(parts)[:MAX_EXTRACT_BYTES]


def _html_members(archive: zipfile.ZipFile, known: set[str]) -> list[str]:
    opf = next((name for name in known if name.lower().endswith(".opf") and _safe_member(name)), "")
    if opf:
        info = archive.getinfo(opf)
        if 0 < info.file_size <= 200_000 and (
            info.compress_size == 0 or info.file_size / info.compress_size <= MAX_COMPRESSION_RATIO
        ):
            base = posixpath.dirname(opf)
            ordered: list[str] = []
            for match in _HREF.finditer(archive.read(info)):
                href = match.group(1).decode("utf-8", "replace").split("#", 1)[0].strip()
                if not href.lower().endswith((".xhtml", ".html", ".htm")):
                    continue
                joined = posixpath.normpath(posixpath.join(base, href))
                if _safe_member(joined) and joined in known and joined not in ordered:
                    ordered.append(joined)
            if ordered:
                return ordered
    return sorted(name for name in known if name.lower().endswith((".xhtml", ".html", ".htm")) and _safe_member(name))


def _safe_member(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name:
        return False
    parts = [part for part in name.split("/") if part]
    return bool(parts) and all(part not in {".", ".."} for part in parts)


class _TextHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "head"}:
            self._skip += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "head"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self.parts.append(data)


def _html_to_text(raw: str) -> str:
    parser = _TextHTML()
    parser.feed(raw[:MAX_HTML_FILE_BYTES])
    parser.close()
    return "".join(parser.parts)


def _read_text_bytes(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(MAX_EXTRACT_BYTES + 1)
    if len(data) > MAX_EXTRACT_BYTES:
        data = data[:MAX_EXTRACT_BYTES]
    return data.decode("utf-8", "replace")


def _clean_line(raw_line: str, *, markdown: bool) -> str:
    line = raw_line.strip()
    if markdown:
        line = _MD_HEADING.sub("", line)
        if line.startswith(">"):
            line = line[1:].strip()
        line = _MD_IMAGE.sub(r"\1", line)
        line = _MD_LINK.sub(r"\1", line)
        line = line.replace("`", " ")
        line = line.replace("*", " ").replace("_", " ")
    line = _HTML_TAG.sub(" ", line)
    return " ".join(line.split())


def _tokens(text: str):
    buf: list[str] = []

    def flush():
        if not buf:
            return
        token = "".join(buf)
        buf.clear()
        if _ok_token(token):
            yield token

    for char in text:
        if char.isalpha() or char.isdigit():
            buf.append(char)
            continue
        if char in {"'", "’", "-"} and buf and buf[-1] not in {"'", "’", "-"}:
            buf.append(char)
            continue
        yield from flush()
    yield from flush()


def _ok_token(token: str) -> bool:
    if len(token) > MAX_WORD_CHARS or token.isdigit():
        return False
    return any(char.isalpha() for char in token)


def _fit(words: list[str]) -> str:
    chunk = list(words)
    while len(chunk) >= 2:
        phrase = " ".join(chunk)
        if len(phrase) <= MAX_PHRASE_CHARS:
            return phrase
        chunk.pop()
    return ""


def _run_capped(args: list[str], limit: int, timeout: float) -> bytes:
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        shell=False,
    )
    stdout = proc.stdout
    if stdout is None:
        proc.kill()
        raise RuntimeError("pdftotext could not be started")
    chunks: list[bytes] = []
    total = 0
    deadline = time.monotonic() + timeout
    try:
        while total < limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TextRejected("pdftotext timed out")
            ready, _, _ = select.select([stdout], [], [], min(1.0, remaining))
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            block = stdout.read(65536)
            if not block:
                break
            room = limit - total
            chunks.append(block[:room])
            total += len(block)
            if total >= limit:
                break
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        stdout.close()
    if proc.returncode not in (0, None, -9) and not chunks:
        raise RuntimeError("pdftotext failed")
    return b"".join(chunks)


def _atomic_write(path: Path, text: str) -> None:
    if path.is_symlink():
        path.unlink()
    temporary = path.with_name(".source.txt.part")
    if temporary.is_symlink():
        temporary.unlink()
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
