import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

import jade_rain.textsrc as textsrc
from jade_rain.cli import main
from jade_rain.config import load_settings, set_text_mode
from jade_rain.textsrc import (
    PDF_MISSING,
    clean_text,
    extract_text,
    pdf_command,
    read_epub,
    sample_phrases,
    write_source,
)


class TextSourceTests(unittest.TestCase):
    def test_cleaning_and_phrase_shape(self) -> None:
        lines = ["Jade Rain"]
        for index in range(8):
            lines.append("Jade Rain")
            lines.append(str(index + 1))
            lines.append(f"The river carries stone number {index} onward")
        raw = "\n".join(lines) + "\n```\nprint('no')\n```\nSee [the river](http://example.test) today.\n"
        cleaned = clean_text(raw, markdown=True)
        self.assertNotIn("print", cleaned)
        self.assertNotIn("example.test", cleaned)
        self.assertNotIn("\n12\n", f"\n{cleaned}\n")
        self.assertEqual(cleaned.lower().count("jade rain"), 0)
        self.assertIn("river carries", cleaned)
        phrases = sample_phrases(cleaned)
        self.assertGreater(len(phrases), 0)
        for phrase in phrases:
            words = phrase.split()
            self.assertGreaterEqual(len(words), 2)
            self.assertLessEqual(len(words), 4)
            self.assertLessEqual(len(phrase), 28)
        again = sample_phrases(cleaned)
        self.assertEqual(phrases, again)
        long = " ".join(f"word{index}" for index in range(400))
        sampled = sample_phrases(long, limit=24)
        self.assertEqual(len(sampled), 24)
        self.assertEqual(sampled, sample_phrases(long, limit=24))

    def test_pdf_command_is_not_a_shell_string(self) -> None:
        path = Path("/tmp/book; rm -rf /.pdf")
        command = pdf_command("/usr/bin/pdftotext", path)
        self.assertIsInstance(command, list)
        self.assertEqual(command[0], "/usr/bin/pdftotext")
        self.assertEqual(command[-2], str(path))
        self.assertEqual(command[-1], "-")
        self.assertNotIn(";", command[0])

    def test_missing_pdftotext_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            pdf = folder / "book.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            previous = os.environ.get("PATH")
            os.environ["PATH"] = str(folder)
            try:
                with self.assertRaises(ValueError) as caught:
                    extract_text(pdf)
            finally:
                if previous is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = previous
        self.assertIn("pdftotext", str(caught.exception))
        self.assertIn("poppler", str(caught.exception))
        self.assertEqual(str(caught.exception), PDF_MISSING)

    def test_pdftotext_argv_and_epub_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            tool = folder / "pdftotext"
            record = folder / "args"
            tool.write_text(
                "#!/usr/bin/python3\n"
                "import os, pathlib, sys\n"
                "pathlib.Path(os.environ['PDF_ARGS']).write_text('\\n'.join(sys.argv))\n"
                "sys.stdout.buffer.write(b'The quiet river moves slowly today\\n12\\n')\n",
                encoding="utf-8",
            )
            tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
            pdf = folder / "chapter.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            previous = os.environ.get("PATH")
            os.environ["PATH"] = str(folder)
            os.environ["PDF_ARGS"] = str(record)
            try:
                text = extract_text(pdf)
            finally:
                if previous is None:
                    os.environ.pop("PATH", None)
                else:
                    os.environ["PATH"] = previous
                os.environ.pop("PDF_ARGS", None)
            argv = record.read_text(encoding="utf-8").splitlines()
            self.assertEqual(argv[-1], "-")
            self.assertEqual(argv[-2], str(pdf))
            self.assertIn("-nopgbrk", argv)
            self.assertIn("quiet river", text)
            self.assertNotIn("\n12\n", f"\n{text}\n")

            epub = folder / "book.epub"
            with zipfile.ZipFile(epub, "w") as archive:
                archive.writestr(
                    "OEBPS/chapter.xhtml",
                    "<html><head><title>Skip Me</title></head><body>"
                    "<script>alert(1)</script><p>quartz xylophone sings softly</p></body></html>",
                )
                archive.writestr("../evil.xhtml", "<p>stolen secret phrase</p>")
            body = read_epub(epub)
            self.assertIn("quartz xylophone", body)
            self.assertNotIn("alert", body)
            self.assertNotIn("stolen", body)

    def test_size_cap_and_symlink_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            big = folder / "big.txt"
            big.write_text("hello river " * 50, encoding="utf-8")
            previous = textsrc.MAX_INPUT_BYTES
            textsrc.MAX_INPUT_BYTES = 20
            try:
                with self.assertRaises(ValueError):
                    extract_text(big)
            finally:
                textsrc.MAX_INPUT_BYTES = previous
            config = folder / "cfg"
            os.environ["XDG_CONFIG_HOME"] = str(config)
            outside = folder / "outside.txt"
            outside.write_text("keep", encoding="utf-8")
            source = config / "jade-rain" / "source.txt"
            source.parent.mkdir(parents=True)
            source.symlink_to(outside)
            try:
                write_source(folder / "notes.txt", "The quiet river moves")
                self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
                self.assertFalse(source.is_symlink())
                self.assertIn("quiet river", source.read_text(encoding="utf-8"))
            finally:
                os.environ.pop("XDG_CONFIG_HOME", None)

    def test_source_command_stays_local(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            os.environ["XDG_CONFIG_HOME"] = str(folder / "config")
            os.environ["XDG_STATE_HOME"] = str(folder / "state")
            try:
                book = folder / "notes.md"
                book.write_text("# Chapter\n\nThe quiet river moves slowly today.\n\n4\n", encoding="utf-8")
                config = folder / "config" / "jade-rain" / "config.toml"
                config.parent.mkdir(parents=True)
                config.write_text('logo = "/keep.png"\ntext_mode = "off"\nword_scale = 0.86\n', encoding="utf-8")
                code = main(["source", str(book)])
                self.assertEqual(code, 0)
                stored = (folder / "config" / "jade-rain" / "source.txt").read_text(encoding="utf-8")
                self.assertIn("quiet river", stored)
                self.assertNotIn("http", stored)
                updated = config.read_text(encoding="utf-8")
                self.assertIn('logo = "/keep.png"', updated)
                self.assertIn('text_mode = "mix"', updated)
                self.assertIn("word_scale = 0.86", updated)
                self.assertEqual(load_settings().text_mode, "mix")
                set_text_mode("replace")
                self.assertEqual(load_settings().text_mode, "replace")
                self.assertIn('logo = "/keep.png"', config.read_text(encoding="utf-8"))
            finally:
                os.environ.pop("XDG_CONFIG_HOME", None)
                os.environ.pop("XDG_STATE_HOME", None)


if __name__ == "__main__":
    unittest.main()
