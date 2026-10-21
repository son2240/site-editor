"""Deploy targets: settings, secret storage, folder pipeline with backup + rollback, FTP and SFTP transports."""
import ftplib
import shutil
import tempfile
import unittest
from pathlib import Path

import _env  # noqa: F401
import credstore
import targets


def make_site():
    site = Path(tempfile.mkdtemp(prefix="tgt-site-"))
    (site / "index.html").write_text("<h1>v1</h1>\n", encoding="utf-8")
    (site / "assets").mkdir()
    (site / "assets" / "app.css").write_text("h1{}\n", encoding="utf-8")
    (site / ".git").mkdir()          # ignored by the file pipeline
    (site / ".git" / "config").write_text("x", encoding="utf-8")
    return site


class Settings(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(credstore.HOME, ignore_errors=True)
        self.site = make_site()

    def test_password_goes_to_secret_store_not_settings(self):
        t = targets.save(self.site, {"type": "ftp", "name": "host", "host": "ftp.example.com", "user": "me",
                                     "remote_path": "/www", "site_url": "https://example.com"}, password="s3cret-pw")
        raw = (credstore.HOME / "targets.json").read_text(encoding="utf-8")
        self.assertNotIn("s3cret-pw", raw)
        self.assertTrue(t["has_password"])
        self.assertNotIn("password", t)
        self.assertEqual(credstore.get_secret(f"target:{t['id']}"), "s3cret-pw")
        self.assertEqual(t["site_url"], "https://example.com/")
        targets.delete(t["id"])
        self.assertIsNone(credstore.get_secret(f"target:{t['id']}"))

    def test_validation(self):
        bad = [{"type": "ftp", "host": "bad host", "user": "me"},
               {"type": "sftp", "host": "h", "user": "me", "auth": "key", "key_file": "/no/such/key"},
               {"type": "ftp", "host": "h", "user": "me", "remote_path": "/www/../etc"},
               {"type": "folder", "folder": str(self.site / "inside")},
               {"type": "folder", "folder": "x", "site_url": "ftp://nope"},
               {"type": "rsync"}]
        for b in bad:
            with self.assertRaises(targets.TargetError, msg=str(b)):
                targets.save(self.site, b)


class FolderPipeline(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(credstore.HOME, ignore_errors=True)
        self.site = make_site()
        self.dest = Path(tempfile.mkdtemp(prefix="tgt-dest-"))
        (self.dest / "index.html").write_text("<h1>old server copy</h1>\n", encoding="utf-8")
        (self.dest / "keep.txt").write_text("not ours\n", encoding="utf-8")
        self.t = targets.get(targets.save(self.site, {"type": "folder", "folder": str(self.dest)})["id"])

    def deploy(self):
        r = targets.review(self.t)
        return targets.run_deploy(self.t, "msg", r["change_id"], log=lambda s: None)

    def test_first_deploy_backs_up_existing_server_files(self):
        r = targets.review(self.t)
        self.assertTrue(r["first_deploy"])
        self.assertEqual([f["path"] for f in r["files"]], ["assets/app.css", "index.html"])  # .git ignored
        self.deploy()
        self.assertEqual((self.dest / "index.html").read_text(encoding="utf-8"), "<h1>v1</h1>\n")
        self.assertTrue((self.dest / "keep.txt").exists())  # files we never deployed are left alone
        self.assertEqual(targets.review(self.t)["files"], [])

    def test_second_deploy_shows_a_diff_and_rollback_restores(self):
        self.deploy()
        (self.site / "index.html").write_text("<h1>v2</h1>\n", encoding="utf-8")
        (self.site / "new.html").write_text("new\n", encoding="utf-8")
        (self.site / "assets" / "app.css").unlink()
        r = targets.review(self.t)
        self.assertEqual({f["path"]: f["status"] for f in r["files"]},
                         {"index.html": "modified", "new.html": "added", "assets/app.css": "deleted"})
        self.assertIn("-<h1>v1</h1>", r["diff"])
        self.assertIn("+<h1>v2</h1>", r["diff"])
        self.assertTrue(r["can_rollback"])
        self.deploy()
        self.assertFalse((self.dest / "assets" / "app.css").exists())
        targets.rollback(self.t, log=lambda s: None)
        self.assertEqual((self.dest / "index.html").read_text(encoding="utf-8"), "<h1>v1</h1>\n")
        self.assertFalse((self.dest / "new.html").exists())
        self.assertTrue((self.dest / "assets" / "app.css").exists())
        # one step only: the next rollback undoes the first deploy, then nothing is left
        targets.rollback(self.t, log=lambda s: None)
        self.assertEqual((self.dest / "index.html").read_text(encoding="utf-8"), "<h1>old server copy</h1>\n")
        with self.assertRaises(targets.TargetError):
            targets.rollback(self.t, log=lambda s: None)

    def test_reviewed_change_is_enforced_and_secrets_block(self):
        r = targets.review(self.t)
        (self.site / "index.html").write_text("<h1>changed after review</h1>\n", encoding="utf-8")
        with self.assertRaises(targets.TargetError):
            targets.run_deploy(self.t, "", r["change_id"], log=lambda s: None)
        fake = "sk-" + "ant-abcdefghijklmnopqrstuvwxyz0123"  # built at run time: no key-shaped text in the source
        (self.site / "leak.txt").write_text(f"key {fake}\n", encoding="utf-8")
        r = targets.review(self.t)
        self.assertEqual([s["kind"] for s in r["secrets"]], ["openai/anthropic key"])
        with self.assertRaises(targets.TargetError):
            targets.run_deploy(self.t, "", r["change_id"], log=lambda s: None)


class FakeFTP:
    """Just enough of ftplib.FTP for the transport."""
    def __init__(self, t):
        self.files, self.dirs, self.log = {}, {"/"}, []

    def connect(self, host, port): self.log.append(("connect", host, port))
    def login(self, user, pw): self.log.append(("login", user, bool(pw)))
    def set_pasv(self, v): pass
    def quit(self): pass
    def close(self): pass
    def pwd(self): return "/"

    def mkd(self, d):
        if d in self.dirs:
            raise ftplib.error_perm("550 exists")
        self.dirs.add(d)

    def storbinary(self, cmd, f): self.files[cmd[5:]] = f.read()

    def retrbinary(self, cmd, cb):
        p = cmd[5:]
        if p not in self.files:
            raise ftplib.error_perm("550 not found")
        cb(self.files[p])

    def delete(self, p): self.files.pop(p, None)


class Transports(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(credstore.HOME, ignore_errors=True)
        self.site = make_site()

    def test_ftp_transport(self):
        t = targets.get(targets.save(self.site, {"type": "ftp", "host": "ftp.example.com", "user": "me", "remote_path": "/www"},
                                     password="pw")["id"])
        fake = FakeFTP(t)
        with targets.FtpTransport(t, ftp_factory=lambda _: fake) as tr:
            tr.put(self.site / "assets" / "app.css", "assets/app.css")
            self.assertFalse(tr.get("missing.html", self.site / "x.tmp"))
            self.assertTrue(tr.get("assets/app.css", self.site / "back.tmp"))
            tr.delete("assets/app.css")
        self.assertIn(("login", "me", True), fake.log)
        self.assertIn("/www/assets", fake.dirs)
        self.assertEqual(fake.files, {})

    def test_sftp_commands_never_contain_the_password(self):
        t = targets.get(targets.save(self.site, {"type": "sftp", "host": "example.com", "port": 2222, "user": "me",
                                                 "remote_path": "/srv/site", "auth": "password"}, password="pw-123")["id"])
        calls = []

        def runner(cmd, input=None, env=None, **kw):
            calls.append((cmd, input, env))
            class P:  # noqa: D401 - tiny stand-in for CompletedProcess
                returncode, stdout, stderr = 0, "/srv/site\n", ""
            return P()

        with targets.SftpTransport(t, runner=runner) as tr:
            tr.put(self.site / "index.html", "a/b/index.html")
            tr.delete("old.html")
        cmd, batch, env = calls[-1]
        self.assertIn("me@example.com", cmd)
        self.assertIn("2222", cmd)
        self.assertNotIn("pw-123", " ".join(cmd) + batch)
        self.assertEqual(env["SITE_EDITOR_SECRET"], f"target:{t['id']}")
        self.assertIn('-mkdir "/srv/site/a"', batch)
        self.assertIn('put "', batch)
        self.assertIn('-rm "/srv/site/old.html"', batch)

    def test_sftp_key_auth_uses_batch_mode(self):
        key = self.site / "id_test"
        key.write_text("dummy", encoding="utf-8")
        t = targets.get(targets.save(self.site, {"type": "sftp", "host": "example.com", "user": "me",
                                                 "remote_path": "/srv", "auth": "key", "key_file": str(key)})["id"])
        cmd, env = targets.SftpTransport(t).command()
        self.assertIn("BatchMode=yes", cmd)
        self.assertIn(str(key), cmd)
        self.assertNotIn("SSH_ASKPASS", {k for k in env if k == "SSH_ASKPASS" and env[k] != __import__("os").environ.get(k)})


if __name__ == "__main__":
    unittest.main()
