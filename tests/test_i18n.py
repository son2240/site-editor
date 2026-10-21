"""Every Korean interface string has an English (and plain Korean) entry, and the example sites are clean."""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import _env  # noqa: F401
import credstore
import i18n_check
import projects

ROOT = Path(__file__).resolve().parents[1]


class Translations(unittest.TestCase):
    def test_no_untranslated_interface_text(self):
        self.assertEqual(i18n_check.missing(), [])

    def test_every_entry_has_english(self):
        src = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)":\s*\[(null|"(?:[^"\\]|\\.)*"),\s*"((?:[^"\\]|\\.)*)"\]', src):
            self.assertTrue(m.group(3).strip(), m.group(1))
            self.assertIsNone(re.search(r"[\uac00-\ud7a3]", m.group(3)), f"English text contains Korean: {m.group(1)}")

    def test_pages_load_the_translator_first(self):
        for name in ("editor.html", "home.html"):
            html = (ROOT / "static" / name).read_text(encoding="utf-8")
            self.assertLess(html.index("/static/i18n.js"), html.index("<script>"), name)


class Examples(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(credstore.HOME, ignore_errors=True)
        projects.save_settings({"storage": tempfile.mkdtemp(prefix="ex-store-")})

    def test_example_templates_create_full_sites(self):
        for tpl in ("example-ko", "example-en"):
            p = projects.create("Ex " + tpl, tpl)
            root = Path(p["path"])
            self.assertTrue((root / "index.html").exists())
            self.assertTrue((root / "img" / "hero.jpg").exists())
            html = (root / "index.html").read_text(encoding="utf-8")
            for ref in re.findall(r'(?:src|href)="((?!https?:|#)[^"]+)"', html):
                self.assertTrue((root / ref).exists(), f"{tpl}: broken link {ref}")

    def test_examples_contain_no_personal_data(self):
        text = " ".join(p.read_text(encoding="utf-8") for p in (ROOT / "examples").rglob("*") if p.suffix in (".html", ".css"))
        self.assertEqual(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text), ["hello@example.com"] * text.count("hello@example.com"))
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        for bad in [b for b in (user, "C:/Users", "C:\\Users", "AppData") if b]:
            self.assertNotIn(bad.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
