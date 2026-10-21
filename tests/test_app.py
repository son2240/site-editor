"""The multi-project app: project list, uploads, routes, cookie/token guard, undo across saves, launcher."""
import http.client
import io
import json
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import _env  # noqa: F401
import credstore
import editor
import htmlmap
import launcher
import projects
import styles

PAGE = '<!doctype html><html><head><title>T</title></head>\n<body>\n  <h1 id="t">Title</h1>\n  <p>Text</p>\n</body></html>\n'


def fresh_home():
    shutil.rmtree(credstore.HOME, ignore_errors=True)
    store = Path(tempfile.mkdtemp(prefix="se-store-"))
    projects.save_settings({"storage": str(store)})
    return store


def make_folder(name="site", html=PAGE):
    d = Path(tempfile.mkdtemp(prefix="se-src-")) / name
    d.mkdir()
    (d / "index.html").write_text(html, encoding="utf-8")
    return d


class ProjectList(unittest.TestCase):
    def setUp(self):
        self.store = fresh_home()

    def test_open_folder_rename_remove_keeps_files(self):
        src = make_folder()
        p = projects.add_folder(src)
        self.assertFalse(p["managed"])
        self.assertEqual(projects.add_folder(src)["id"], p["id"])  # opening twice does not duplicate
        projects.rename(p["id"], "My site")
        self.assertEqual(projects.list_all()[0]["name"], "My site")
        self.assertEqual(projects.list_all("my")[0]["id"], p["id"])
        self.assertEqual(projects.list_all("nothing"), [])
        with self.assertRaises(projects.ProjectError):  # a linked folder is never deleted
            projects.delete(p["id"], "My site")
        projects.remove(p["id"])
        self.assertTrue((src / "index.html").exists())
        self.assertEqual(projects.list_all(), [])

    def test_folder_without_html_is_refused(self):
        d = Path(tempfile.mkdtemp())
        with self.assertRaises(projects.ProjectError):
            projects.add_folder(d)

    def test_new_duplicate_and_delete_to_trash(self):
        p = projects.create("Demo")
        self.assertTrue(p["managed"])
        self.assertTrue((Path(p["path"]) / "index.html").exists())
        self.assertEqual(Path(p["path"]).parent, self.store)
        c = projects.duplicate(p["id"])
        self.assertNotEqual(c["path"], p["path"])
        with self.assertRaises(projects.ProjectError):
            projects.delete(p["id"], "wrong name")
        r = projects.delete(p["id"], "Demo")
        self.assertFalse(Path(p["path"]).exists())
        self.assertTrue((Path(r["trashed"]) / "index.html").exists())  # recoverable

    def test_folder_upload_flattens_and_sanitizes(self):
        up = projects.start_upload("Uploaded")
        projects.upload_file(up["upload"], "mysite/index.html", PAGE.encode())
        projects.upload_file(up["upload"], "mysite/css/a.css", b"p{}")
        projects.upload_file(up["upload"], "mysite/.git/config", b"secret")  # skipped
        for bad in ("../evil.txt", "/abs.txt", "C:/x.txt"):
            with self.assertRaises(projects.ProjectError):
                projects.upload_file(up["upload"], bad, b"x")
        p = projects.finish_upload(up["upload"])
        root = Path(p["path"])
        self.assertTrue((root / "index.html").exists())
        self.assertTrue((root / "css" / "a.css").exists())
        self.assertFalse((root / ".git").exists())
        self.assertFalse((root / ".site-editor-upload").exists())

    def test_zip_upload_blocks_zip_slip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("site/index.html", PAGE)
            z.writestr("site/img/a.png", b"\x89PNG")
        p = projects.upload_zip("Zipped", buf.getvalue())
        self.assertTrue((Path(p["path"]) / "img" / "a.png").exists())
        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("index.html", PAGE)
            z.writestr("../../escaped.txt", "x")
        with self.assertRaises(projects.ProjectError):
            projects.upload_zip("Bad", bad.getvalue())
        self.assertFalse((self.store.parent / "escaped.txt").exists())
        self.assertEqual(len([x for x in self.store.iterdir() if x.name.startswith("Bad")]), 0)  # cleaned up

    def test_export_zip_skips_git(self):
        src = make_folder()
        (src / ".git").mkdir()
        (src / ".git" / "config").write_text("x", encoding="utf-8")
        p = projects.add_folder(src)
        name, data = projects.export_zip(p["id"])
        self.assertTrue(name.endswith(".zip"))
        self.assertEqual(zipfile.ZipFile(io.BytesIO(data)).namelist(), ["index.html"])


class UndoAcrossSaves(unittest.TestCase):
    def test_restore_many_undoes_a_save(self):
        site = make_folder()
        ed = editor.Editor(site, history_dir=site.parent / "hist")
        h1 = next(n for n in htmlmap.parse(PAGE) if n.tag == "h1")
        res = ed.save_all({"rules": [{"selector": "#t", "media": "", "props": {"font-size": "3rem"}}],
                           "page": "index.html", "html_edits": [{"op": "inner", "id": h1.id, "html": "New"}]})
        self.assertEqual(res["created"], [styles.FILE])
        self.assertEqual(len(res["snapshots"]), 1)  # index.html (the css file is new)
        ed.restore_many(res["snapshots"], res["created"])
        self.assertEqual((site / "index.html").read_text(encoding="utf-8"), PAGE)
        self.assertFalse((site / styles.FILE).exists())


class AppRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fresh_home()
        cls.site = make_folder()
        cls.pid = projects.add_folder(cls.site)["id"]
        cls.token = "tok123"
        srv = editor.serve(0, cls.token)
        cls.port = srv.server_address[1]
        srv.RequestHandlerClass = editor.make_handler(editor.App(cls.token, cls.port))
        cls.srv = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def req(self, method, path, body=None, token=False, cookie=False, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["X-Editor-Token"] = self.token
        if cookie:
            h["Cookie"] = f"{editor.COOKIE}={self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())

    def test_ping_is_public_but_nothing_else(self):
        self.assertEqual(json.loads(self.req("GET", "/api/ping")[1]), {"app": "site-editor"})
        self.assertEqual(self.req("GET", "/api/projects")[0], 403)
        self.assertEqual(self.req("GET", "/")[0], 403)
        self.assertEqual(self.req("GET", "/api/projects", token=True, host="evil.example")[0], 403)

    def test_url_token_becomes_a_strict_cookie(self):
        st, _, h = self.req("GET", f"/?t={self.token}")
        self.assertEqual(st, 302)
        self.assertEqual(h["Location"], "/")
        self.assertIn("HttpOnly", h["Set-Cookie"])
        self.assertIn("SameSite=Strict", h["Set-Cookie"])
        self.assertEqual(self.req("GET", "/", cookie=True)[0], 200)

    def test_home_and_project_pages(self):
        st, body, _ = self.req("GET", "/", cookie=True)
        self.assertIn("최근 프로젝트".encode(), body)
        st, body, _ = self.req("GET", f"/p/{self.pid}/", cookie=True)
        self.assertEqual(st, 200)
        self.assertIn(f'const BASE = "/p/{self.pid}"'.encode(), body)
        self.assertEqual(self.req("GET", "/p/ffffffffff/", cookie=True)[0], 302)  # unknown project -> home

    def test_project_api_and_design_route(self):
        st, body, _ = self.req("GET", f"/api/p/{self.pid}/pages", token=True)
        self.assertEqual(json.loads(body)["pages"], ["index.html"])
        st, body, _ = self.req("GET", f"/p/{self.pid}/design/index.html", cookie=True)
        self.assertIn(b'data-se-id="0"', body)
        self.assertIn(b"/static/bridge.js", body)
        self.assertEqual(self.req("GET", f"/p/{self.pid}/site/index.html")[0], 403)  # needs the cookie

    def test_thumbnail_is_sandboxed(self):
        st, body, h = self.req("GET", f"/p/{self.pid}/thumb/index.html")
        self.assertEqual(st, 200)
        self.assertEqual(h["Content-Security-Policy"], "sandbox allow-scripts")
        self.assertNotIn(self.token.encode(), body)

    def test_project_list_shows_targets(self):
        st, body, _ = self.req("GET", "/api/projects", token=True)
        p = json.loads(body)["projects"][0]
        self.assertEqual(p["id"], self.pid)
        self.assertIn("modified", p)
        self.assertEqual(p["targets"], [])

    def test_export_download_uses_cookie(self):
        st, body, h = self.req("GET", f"/p/{self.pid}/export.zip", cookie=True)
        self.assertEqual(st, 200)
        self.assertEqual(h["Content-Type"], "application/zip")
        self.assertIn("index.html", zipfile.ZipFile(io.BytesIO(body)).namelist())

    def test_deploy_still_needs_confirmation(self):
        st, body, _ = self.req("POST", f"/api/p/{self.pid}/deploy", {"target": "x", "change_id": "x"}, token=True)
        self.assertEqual(st, 400)
        self.assertIn(b"confirmation", body)


class Launcher(unittest.TestCase):
    def test_session_file_round_trip(self):
        launcher.write_session(9999, "abc")
        self.assertEqual(launcher.url("/x"), "http://127.0.0.1:9999/x?t=abc")

    def test_ping_false_when_nothing_listens(self):
        self.assertFalse(launcher.ping(1, timeout=0.2))

    def test_shortcut_script_gets_paths_through_env_not_command_line(self):
        calls = []
        with mock.patch("subprocess.run", side_effect=lambda *a, **k: calls.append((a, k)) or mock.Mock(stdout="")):
            launcher.make_shortcut(Path(tempfile.gettempdir()) / "x.lnk", "--background", minimized=True)
        args, kw = calls[-1]
        self.assertEqual(args[0][:2], ["powershell", "-NoProfile"])
        self.assertEqual(kw["env"]["SE_MIN"], "1")
        self.assertIn("launcher.py", kw["env"]["SE_ARGS"])
        self.assertIn("--background", kw["env"]["SE_ARGS"])

    def test_open_app_focuses_existing_window(self):
        with mock.patch.object(launcher, "ping", return_value=True), \
                mock.patch.object(launcher, "focus_existing_window", return_value=True) as focus, \
                mock.patch.object(launcher, "open_window") as open_w:
            launcher.open_app()
        focus.assert_called_once()
        open_w.assert_not_called()


if __name__ == "__main__":
    unittest.main()
