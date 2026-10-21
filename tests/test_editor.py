"""Offline tests: data file parsing, editor safety, snapshots, upload checks, deploy flow, HTTP guard."""
import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import _env  # noqa: F401,E402  (must come before the tool modules)
import deploy  # noqa: E402
import editor  # noqa: E402
import jsdata  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
SAMPLE = """// header comment with a URL https://example.com
window.SITE = {
  profile: { name: { ko: '이름', en: "Name" }, github: "https://github.com/x", }, // trailing comma
  /* block */ projects: [],
  flag: true, nothing: null,
};
"""


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def make_site():
    root = Path(tempfile.mkdtemp(prefix="site-editor-test-"))
    remote, site = root / "remote.git", root / "site"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    site.mkdir()
    git(site, "init", "-q", "-b", "main")
    git(site, "config", "user.name", "test")
    git(site, "config", "user.email", "test@example.invalid")
    git(site, "config", "core.autocrlf", "false")
    (site / "index.html").write_text("<p>hi</p>\n", encoding="utf-8")
    (site / "content.js").write_text(SAMPLE, encoding="utf-8")
    git(site, "add", "-A")
    git(site, "commit", "-q", "-m", "init")
    git(site, "remote", "add", "origin", str(remote))
    git(site, "push", "-q", "origin", "main")
    return site, remote


class JsData(unittest.TestCase):
    def test_parse_js_literal(self):
        name, d = jsdata.parse(SAMPLE)
        self.assertEqual(name, "SITE")
        self.assertEqual(d["profile"]["name"], {"ko": "이름", "en": "Name"})
        self.assertEqual(d["profile"]["github"], "https://github.com/x")
        self.assertEqual((d["flag"], d["nothing"], d["projects"]), (True, None, []))

    def test_round_trip(self):
        name, d = jsdata.parse(SAMPLE)
        self.assertEqual(jsdata.parse(jsdata.dump(name, d)), (name, d))

    def test_rejects_code(self):
        with self.assertRaises(jsdata.DataError):
            jsdata.parse("window.SITE = { a: alert(1) };")
        with self.assertRaises(jsdata.DataError):
            jsdata.parse("var x = 1;")


class EditorTest(unittest.TestCase):
    def setUp(self):
        self.site, self.remote = make_site()
        self.ed = editor.Editor(self.site, history_dir=self.site.parent / "history")

    def test_paths_stay_inside_the_site(self):
        for bad in ("../outside.txt", "/../../etc/passwd", ".git/config"):
            with self.assertRaises(PermissionError):
                self.ed.resolve(bad)

    def test_save_snapshot_and_restore(self):
        c = self.ed.read_content()
        c["data"]["profile"]["name"]["ko"] = "새 이름"
        self.ed.save_all({"data": c["data"]})
        self.assertEqual(self.ed.read_content()["data"]["profile"]["name"]["ko"], "새 이름")
        snap = self.ed.list_history()[0]
        self.assertEqual(snap["path"], "content.js")  # snapshot of the version before the save
        self.ed.restore(snap["id"])
        self.assertEqual(self.ed.read_content()["data"]["profile"]["name"]["ko"], "이름")
        self.assertEqual(len(self.ed.list_history()), 2)  # restoring also snapshots first

    def test_draft_is_memory_only(self):
        c = self.ed.read_content()["data"]
        c["profile"]["name"]["ko"] = "초안"
        self.ed.set_draft(c)
        self.assertIn("초안", self.ed.draft)
        self.assertNotIn("초안", (self.site / "content.js").read_text(encoding="utf-8"))

    def test_upload_checks_real_image_bytes(self):
        with self.assertRaises(ValueError):
            self.ed.upload("evil.png", base64.b64encode(b"<script>").decode())
        with self.assertRaises(ValueError):
            self.ed.upload("page.svg", base64.b64encode(b"<svg/>").decode())
        r1 = self.ed.upload("My Photo!.png", base64.b64encode(PNG).decode())
        r2 = self.ed.upload("My Photo!.png", base64.b64encode(PNG).decode())
        self.assertEqual((r1["path"], r2["path"]), ("assets/img/My-Photo.png", "assets/img/My-Photo-1.png"))

    def test_file_editing_and_discard(self):
        self.ed.write_file("index.html", "<p>changed</p>\n")
        with self.assertRaises(jsdata.DataError):
            self.ed.write_file("content.js", "broken")
        self.ed.discard("index.html")
        self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "<p>hi</p>\n")


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.site, self.remote = make_site()

    def head_remote(self):
        return subprocess.run(["git", "-C", str(self.remote), "rev-parse", "main"], capture_output=True, text=True).stdout.strip()

    def test_nothing_to_deploy(self):
        r = deploy.review(self.site)
        self.assertEqual(r["files"], [])
        with self.assertRaises(deploy.DeployError):
            deploy.deploy(self.site, "x", r["change_id"], log=lambda s: None)

    def test_approval_is_bound_to_the_reviewed_change(self):
        (self.site / "index.html").write_text("<p>v1</p>\n", encoding="utf-8")
        r = deploy.review(self.site)
        (self.site / "index.html").write_text("<p>v2, edited after review</p>\n", encoding="utf-8")
        with self.assertRaises(deploy.DeployError) as cm:
            deploy.deploy(self.site, "x", r["change_id"], log=lambda s: None)
        self.assertIn("changed after", str(cm.exception))

    def test_secrets_block_deploy(self):
        fake = "xox" + "b-1234567890-abcdefghij"  # built at run time: the source holds no token-shaped text
        (self.site / "notes.txt").write_text(f"token = {fake}\n", encoding="utf-8")
        (self.site / ".env").write_text("A=1\n", encoding="utf-8")
        r = deploy.review(self.site)
        kinds = sorted(s["kind"] for s in r["secrets"])
        self.assertEqual(kinds, ["blocked file name", "slack token"])
        self.assertNotIn(fake, json.dumps(r["secrets"]))  # values are never echoed
        with self.assertRaises(deploy.DeployError):
            deploy.deploy(self.site, "x", r["change_id"], log=lambda s: None)

    def test_deploy_commits_and_pushes(self):
        (self.site / "index.html").write_text("<p>new</p>\n", encoding="utf-8")
        (self.site / "new.css").write_text("p{}\n", encoding="utf-8")
        r = deploy.review(self.site)
        self.assertEqual({f["path"]: f["status"] for f in r["files"]}, {"index.html": "modified", "new.css": "added"})
        self.assertIn("+<p>new</p>", r["diff"])
        logs = []
        res = deploy.deploy(self.site, "Edit intro", r["change_id"], log=logs.append)
        self.assertTrue(res["ok"])
        self.assertEqual(self.head_remote(), res["commit"])
        self.assertEqual(deploy.review(self.site)["files"], [])

    def test_unpushed_commits_are_shown_and_published(self):
        (self.site / "index.html").write_text("<p>committed but not pushed</p>\n", encoding="utf-8")
        git(self.site, "commit", "-q", "-am", "local only")
        r = deploy.review(self.site)
        self.assertEqual([f["path"] for f in r["files"]], ["index.html"])
        self.assertIn("+<p>committed but not pushed</p>", r["diff"])
        self.assertEqual(len(r["unpushed_commits"]), 1)
        res = deploy.deploy(self.site, "", r["change_id"], log=lambda s: None)
        self.assertEqual(self.head_remote(), res["commit"])

    def test_repo_info_for_github_pages(self):
        git(self.site, "remote", "set-url", "origin", "https://github.com/someone/someone.github.io.git")
        self.assertEqual(deploy.repo_info(self.site)["site_url"], "https://someone.github.io/")
        git(self.site, "remote", "set-url", "origin", "https://github.com/someone/blog.git")
        self.assertEqual(deploy.repo_info(self.site)["site_url"], "https://someone.github.io/blog/")


if __name__ == "__main__":
    unittest.main()
