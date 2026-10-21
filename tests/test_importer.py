"""Import a site by URL: crawl, download assets, rewrite links (against a local fake site)."""
import shutil
import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import _env  # noqa: F401
import credstore
import importer
import launcher
import projects

FILES = {
    "index.html": """<!doctype html><html><head><meta charset="utf-8"><title>Fake</title>
<base href="/">
<link rel="stylesheet" href="/css/site.css?v=3" integrity="sha384-abc" crossorigin="anonymous">
<link rel="stylesheet" href="https://cdn.example.org/lib.css">
<link rel="icon" href="favicon.png">
<meta property="og:image" content="http://HOST/img/og.png">
<style>.hero{background:url('/img/bg.png')}</style>
</head><body>
<a href="/about">About</a> <a href="blog/post.html#top">Post</a> <a href="https://other.example.com/">Other</a>
<a href="mailto:me@example.com">Mail</a> <a href="/files/cv.pdf">CV</a>
<img src="img/logo.png" srcset="img/logo.png 1x, /img/logo@2x.png 2x" alt="">
<div style="background-image:url(/img/bg.png)"></div>
<script src="js/app.js"></script>
</body></html>""",
    "about/index.html": """<!doctype html><html><head><link rel="stylesheet" href="../css/site.css?v=3"></head>
<body><a href="/">Home</a><img src="/img/logo.png"><a href="/deep/one.html">deep</a></body></html>""",
    "blog/post.html": """<html><body><a href="../index.html">home</a><img src="../img/logo.png"></body></html>""",
    "deep/one.html": "<html><body><a href='/deep/two.html'>two</a></body></html>",
    "deep/two.html": "<html><body>two</body></html>",
    "css/site.css": "@import url('base.css'); body{font-family:F} @font-face{src:url(../fonts/f.woff2)} .x{background:url(\"/img/bg.png\")}",
    "css/base.css": "p{color:red}",
    "fonts/f.woff2": "FONT",
    "img/logo.png": "PNG1", "img/logo@2x.png": "PNG2", "img/bg.png": "BG", "img/og.png": "OG",
    "favicon.png": "ICO", "js/app.js": "console.log(1)", "files/cv.pdf": "%PDF",
    "spa.html": """<!doctype html><html><body><div id="app"></div>
<script>document.getElementById('app').innerHTML = '<h1>Drawn by JS</h1>';</script></body></html>""",
}


class FakeSite:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="fake-site-"))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(self.root)))
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        for rel, text in FILES.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text.replace("HOST", self.srv.server_address[0] + ":" + str(self.srv.server_address[1])), encoding="utf-8")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class Import(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.site = FakeSite()

    @classmethod
    def tearDownClass(cls):
        cls.site.srv.shutdown()

    def setUp(self):
        shutil.rmtree(credstore.HOME, ignore_errors=True)
        projects.save_settings({"storage": tempfile.mkdtemp(prefix="imp-store-")})

    def run_import(self, **kw):
        logs = []
        p = importer.import_site(self.site.url, "Imported", log=logs.append, **kw)
        return Path(p["path"]), p, logs

    def test_pages_and_assets_are_saved_with_matching_paths(self):
        root, p, _ = self.run_import()
        for rel in ("index.html", "about/index.html", "blog/post.html", "deep/one.html", "img/logo.png", "img/logo@2x.png",
                    "img/bg.png", "img/og.png", "favicon.png", "js/app.js", "css/base.css", "fonts/f.woff2", "files/cv.pdf"):
            self.assertTrue((root / rel).exists(), rel)
        css = [x for x in (root / "css").iterdir() if x.name.startswith("site-")]
        self.assertEqual(len(css), 1)  # site.css?v=3 -> site-<hash>.css
        self.assertEqual(p["source_url"], self.site.url)

    def test_links_become_relative_and_other_sites_stay(self):
        root, _, _ = self.run_import()
        idx = (root / "index.html").read_text(encoding="utf-8")
        css_name = next(x.name for x in (root / "css").iterdir() if x.name.startswith("site-"))
        self.assertIn(f'href="css/{css_name}"', idx)
        self.assertNotIn("integrity", idx)                      # local copy no longer matches the SRI hash
        self.assertNotIn("<base", idx)
        self.assertIn('href="about/index.html"', idx)
        self.assertIn('href="blog/post.html#top"', idx)
        self.assertIn('href="https://other.example.com/"', idx)  # other sites untouched
        self.assertIn('href="https://cdn.example.org/lib.css"', idx)
        self.assertIn('href="mailto:me@example.com"', idx)
        self.assertIn('srcset="img/logo.png 1x, img/logo@2x.png 2x"', idx)
        self.assertIn("url('img/bg.png')", idx)
        self.assertIn("url(img/bg.png)", idx)
        self.assertIn('content="img/og.png"', idx)
        about = (root / "about" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="../index.html"', about)
        self.assertIn('src="../img/logo.png"', about)
        css = next(x for x in (root / "css").iterdir() if x.name.startswith("site-")).read_text(encoding="utf-8")
        self.assertIn("url('base.css')", css)
        self.assertIn("url(../fonts/f.woff2)", css)
        self.assertIn('url("../img/bg.png")', css)

    def test_page_limit_keeps_unvisited_pages_as_full_urls(self):
        root, _, _ = self.run_import(max_pages=2)
        self.assertFalse((root / "deep" / "one.html").exists())
        about = (root / "about" / "index.html").read_text(encoding="utf-8")
        self.assertIn(f'href="{self.site.url}deep/one.html"', about)  # still works online

    def test_bad_urls(self):
        for bad in ("ftp://x", "javascript:alert(1)", "file:///C:/Windows"):
            with self.assertRaises(importer.ImportError_):
                importer.normalize(bad)
        self.assertEqual(importer.normalize("localhost:8000/a"), "https://localhost:8000/a")
        with self.assertRaises(importer.ImportError_):  # nothing listens there
            importer.import_site("http://127.0.0.1:1/", log=lambda s: None)

    def test_local_path_mapping(self):
        lp = importer.local_path
        self.assertEqual(lp("https://a.com/", True), "index.html")
        self.assertEqual(lp("https://a.com/about", True), "about/index.html")
        self.assertNotIn("..", lp("https://a.com/x/../../etc/passwd", False))
        self.assertEqual(lp("https://a.com/a:b*c.png", False), "a_b_c.png")
        self.assertTrue(lp("https://a.com/s.css?v=1", False).startswith("s-"))

    @unittest.skipUnless(launcher._app_browser(), "needs Edge or Chrome")
    def test_rendered_mode_saves_the_drawn_page_without_scripts(self):
        logs = []
        p = importer.import_site(self.site.url + "spa.html", "SPA", max_pages=1, rendered=True, log=logs.append)
        page = next(Path(p["path"]).rglob("*.html")).read_text(encoding="utf-8")
        self.assertIn("<h1>Drawn by JS</h1>", page)
        self.assertNotIn("<script", page)


if __name__ == "__main__":
    unittest.main()
