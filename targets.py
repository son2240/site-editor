"""Deploy targets: where a site is published, and how.

Types:
  git     GitHub Pages or any git remote: commit + push (see deploy.py)
  sftp    SSH file transfer via the system OpenSSH client (key file or password)
  ftp     FTP or FTPS (explicit TLS) via ftplib
  folder  copy into a local or network folder (also used by the tests)

Target settings (host, port, user, remote path, key file path, site URL) are kept in
~/.site-editor/targets.json on this PC. Passwords go to the OS credential store
(credstore.py). Nothing here is ever written into the site repository.

File-based targets (sftp/ftp/folder) share one pipeline:
  review   compare local files with what this tool last deployed (manifest of hashes)
  deploy   confirm the reviewed change id -> secret scan -> download the remote files
           about to be replaced into a local backup -> upload / delete -> update the
           manifest -> fetch the live URLs and compare bytes
  rollback undo the last deploy: put the backed-up files back, delete files it added
"""
from __future__ import annotations

import difflib
import ftplib
import hashlib
import json
import os
import posixpath
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import credstore
import deploy

HOME = credstore.HOME
TYPES = ("git", "sftp", "ftp", "folder")
IGNORE_DIRS = {".git", ".history", "__pycache__", "node_modules", ".venv", ".site-editor"}
IGNORE_FILES = re.compile(r"(^|/)(\.DS_Store|Thumbs\.db|desktop\.ini|.*\.tmp|.*~|.*\.swp)$", re.I)
PUBLIC_FIELDS = ("id", "name", "type", "site", "site_url", "host", "port", "user", "remote_path",
                 "auth", "key_file", "tls", "folder", "passive")
MAX_FILES = 5000


class TargetError(RuntimeError):
    pass


# -- target settings ----------------------------------------------------------
def _settings_path() -> Path:
    return HOME / "targets.json"


def load_all() -> list[dict]:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8")).get("targets", [])
    except (OSError, ValueError):
        return []


def _save_all(items: list[dict]) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    _settings_path().write_text(json.dumps({"targets": items}, ensure_ascii=False, indent=1), encoding="utf-8")


def public(t: dict) -> dict:
    out = {k: t[k] for k in PUBLIC_FIELDS if k in t}
    out["has_password"] = t["type"] in ("sftp", "ftp") and credstore.has_secret(_secret_key(t))
    out["secret_store"] = credstore.backend()
    return out


def for_site(site: Path) -> list[dict]:
    site = str(Path(site).resolve())
    return [t for t in load_all() if t.get("site") == site]


def get(target_id: str) -> dict:
    for t in load_all():
        if t["id"] == target_id:
            return t
    raise TargetError(f"no target {target_id}")


def _secret_key(t: dict) -> str:
    return f"target:{t['id']}"


def save(site: Path, data: dict, password: str | None = None) -> dict:
    """Create or update a target. `password` (if given) goes to the credential store only."""
    typ = data.get("type")
    if typ not in TYPES:
        raise TargetError(f"unknown type {typ!r}")
    t = {"id": data.get("id") or uuid.uuid4().hex[:10], "type": typ, "site": str(Path(site).resolve()),
         "name": str(data.get("name") or typ).strip()[:60], "site_url": str(data.get("site_url") or "").strip()}
    if t["site_url"] and not re.match(r"^https?://", t["site_url"]):
        raise TargetError("site URL must start with http:// or https://")
    if t["site_url"] and not t["site_url"].endswith("/"):
        t["site_url"] += "/"
    if typ in ("sftp", "ftp"):
        host = str(data.get("host") or "").strip()
        if not re.match(r"^[A-Za-z0-9.\-]+$", host):
            raise TargetError("host must be a host name or IP address")
        port = int(data.get("port") or (22 if typ == "sftp" else 21))
        user = str(data.get("user") or "").strip()
        if not user or re.search(r"[\s@:]", user):
            raise TargetError("user name is required (no spaces, @ or :)")
        remote = str(data.get("remote_path") or "").strip() or "/"
        if ".." in remote.split("/"):
            raise TargetError("remote path must not contain ..")
        t.update(host=host, port=port, user=user, remote_path=remote)
    if typ == "sftp":
        t["auth"] = data.get("auth") if data.get("auth") in ("key", "password") else "key"
        if t["auth"] == "key":
            kf = str(data.get("key_file") or "").strip()
            if not kf or not Path(kf).expanduser().is_file():
                raise TargetError("key file not found")
            t["key_file"] = str(Path(kf).expanduser())
    if typ == "ftp":
        t["tls"] = bool(data.get("tls", True))
        t["passive"] = bool(data.get("passive", True))
    if typ == "folder":
        folder = str(data.get("folder") or "").strip()
        if not folder:
            raise TargetError("folder is required")
        t["folder"] = str(Path(folder).expanduser().resolve())
        if Path(t["folder"]) == Path(t["site"]) or Path(t["site"]) in Path(t["folder"]).parents:
            raise TargetError("the target folder must be outside the site folder")
    items = [x for x in load_all() if x["id"] != t["id"]]
    items.append(t)
    _save_all(items)
    if password:
        credstore.set_secret(_secret_key(t), password)
    return public(t)


def delete(target_id: str) -> None:
    t = get(target_id)
    credstore.delete_secret(_secret_key(t))
    _save_all([x for x in load_all() if x["id"] != target_id])


# -- transports ------------------------------------------------------------------
class FolderTransport:
    def __init__(self, t: dict):
        self.root = Path(t["folder"])

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc):
        return False

    def get(self, rel: str, local: Path) -> bool:
        src = self.root / rel
        if not src.is_file():
            return False
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, local)
        return True

    def put(self, local: Path, rel: str) -> None:
        dst = self.root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dst)

    def delete(self, rel: str) -> None:
        (self.root / rel).unlink(missing_ok=True)

    def test(self) -> str:
        return f"folder ok: {len(list(self.root.iterdir()))} entries"


class FtpTransport:
    def __init__(self, t: dict, ftp_factory=None):
        self.t, self.factory, self.ftp = t, ftp_factory, None

    def __enter__(self):
        t = self.t
        pw = credstore.get_secret(_secret_key(t)) or ""
        if self.factory:
            self.ftp = self.factory(t)
        elif t.get("tls", True):
            self.ftp = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=30)
        else:
            self.ftp = ftplib.FTP(timeout=30)
        self.ftp.connect(t["host"], int(t["port"]))
        self.ftp.login(t["user"], pw)
        if isinstance(self.ftp, ftplib.FTP_TLS):
            self.ftp.prot_p()  # encrypt file transfers too, not only the login
        self.ftp.set_pasv(t.get("passive", True))
        return self

    def __exit__(self, *exc):
        try:
            self.ftp.quit()
        except Exception:  # noqa: BLE001
            self.ftp.close()
        return False

    def _path(self, rel: str) -> str:
        return posixpath.join(self.t["remote_path"], rel)

    def _mkdirs(self, rdir: str) -> None:
        cur = ""
        for part in [p for p in rdir.split("/") if p]:
            cur += "/" + part
            try:
                self.ftp.mkd(cur)
            except ftplib.error_perm:
                pass  # exists

    def get(self, rel: str, local: Path) -> bool:
        local.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(local, "wb") as f:
                self.ftp.retrbinary("RETR " + self._path(rel), f.write)
            return True
        except ftplib.error_perm:
            local.unlink(missing_ok=True)
            return False

    def put(self, local: Path, rel: str) -> None:
        self._mkdirs(posixpath.dirname(self._path(rel)))
        with open(local, "rb") as f:
            self.ftp.storbinary("STOR " + self._path(rel), f)

    def delete(self, rel: str) -> None:
        try:
            self.ftp.delete(self._path(rel))
        except ftplib.error_perm:
            pass

    def test(self) -> str:
        return "ftp ok: " + self.ftp.pwd()


class SftpTransport:
    """Batches commands for the system `sftp` (OpenSSH). Passwords are passed through
    SSH_ASKPASS (askpass.py reads them from the credential store), never on the command line."""

    def __init__(self, t: dict, runner=None):
        self.t, self.run = t, runner or subprocess.run
        self.ops: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None and self.ops:
            self.flush()
        return False

    def _q(self, s: str) -> str:
        return '"' + s.replace("\\", "/").replace('"', '\\"') + '"'

    def _path(self, rel: str) -> str:
        return posixpath.join(self.t["remote_path"], rel)

    def command(self) -> tuple[list[str], dict]:
        t = self.t
        cmd = [shutil.which("sftp") or "sftp", "-P", str(t["port"]), "-o", "StrictHostKeyChecking=accept-new",
               "-o", "ConnectTimeout=20"]
        env = dict(os.environ)
        if t.get("auth") == "key":
            cmd += ["-i", t["key_file"], "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes"]
        else:
            helper = Path(__file__).with_name("askpass.cmd" if os.name == "nt" else "askpass.py")
            env.update(SSH_ASKPASS=str(helper), SSH_ASKPASS_REQUIRE="force", DISPLAY=env.get("DISPLAY", ":0"),
                       SITE_EDITOR_SECRET=_secret_key(t), SITE_EDITOR_PYTHON=sys.executable)
            cmd += ["-o", "BatchMode=no", "-o", "PreferredAuthentications=password,keyboard-interactive"]
        cmd.append(f"{t['user']}@{t['host']}")
        return cmd, env

    def _exec(self, lines: list[str]) -> str:
        cmd, env = self.command()
        p = self.run(cmd, input="\n".join(lines + ["bye"]) + "\n", capture_output=True, text=True, env=env, timeout=600)
        errors = [ln for ln in (p.stderr or "").splitlines()
                  if re.search(r"denied|not found|No such file|Couldn't|failure|error", ln, re.I)
                  and not ln.startswith("Warning: Permanently added")]
        if p.returncode != 0 or errors:
            raise TargetError("sftp: " + ("; ".join(errors[:3]) or f"exit code {p.returncode}"))
        return p.stdout

    def flush(self) -> None:
        ops, self.ops = self.ops, []
        self._exec(ops)

    def get(self, rel: str, local: Path) -> bool:
        local.parent.mkdir(parents=True, exist_ok=True)
        cmd, env = self.command()
        self.run(cmd, input=f"-get {self._q(self._path(rel))} {self._q(str(local))}\nbye\n",
                     capture_output=True, text=True, env=env, timeout=600)
        return local.is_file()

    def put(self, local: Path, rel: str) -> None:
        parts = posixpath.dirname(self._path(rel)).split("/")
        for i in range(2, len(parts) + 1):
            self.ops.append(f"-mkdir {self._q('/'.join(parts[:i]))}")
        self.ops.append(f"put {self._q(str(local))} {self._q(self._path(rel))}")

    def delete(self, rel: str) -> None:
        self.ops.append(f"-rm {self._q(self._path(rel))}")

    def test(self) -> str:
        out = self._exec([f"cd {self._q(self.t['remote_path'])}", "pwd"])
        return "sftp ok: " + out.strip().splitlines()[-1] if out.strip() else "sftp ok"


def transport(t: dict):
    return {"folder": FolderTransport, "ftp": FtpTransport, "sftp": SftpTransport}[t["type"]](t)


def test_connection(t: dict) -> str:
    if t["type"] == "git":
        info = deploy.repo_info(Path(t["site"]))
        deploy.git(Path(t["site"]), "ls-remote", "--heads", "origin")
        return f"git ok: {info['remote']}"
    with transport(t) as tr:
        return tr.test()


# -- file pipeline -------------------------------------------------------------
def _state(t: dict) -> Path:
    return HOME / "state" / t["id"]


def local_files(site: Path) -> dict[str, str]:
    out = {}
    for root, dirs, files in os.walk(site):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS)
        for f in sorted(files):
            rel = Path(root, f).relative_to(site).as_posix()
            if IGNORE_FILES.search(rel):
                continue
            out[rel] = hashlib.sha256(Path(root, f).read_bytes()).hexdigest()
            if len(out) > MAX_FILES:
                raise TargetError(f"more than {MAX_FILES} files: is --site the right folder?")
    return out


def _manifest(t: dict) -> dict[str, str]:
    try:
        return json.loads((_state(t) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def review(t: dict) -> dict:
    if t["type"] == "git":
        r = deploy.review(Path(t["site"]))
        r["target"] = public(t)
        return r
    site = Path(t["site"])
    now, before = local_files(site), _manifest(t)
    files = [{"path": p, "status": "added"} for p in now if p not in before] + \
            [{"path": p, "status": "modified"} for p in now if p in before and before[p] != now[p]] + \
            [{"path": p, "status": "deleted"} for p in before if p not in now]
    files.sort(key=lambda f: f["path"])
    h = hashlib.sha256(json.dumps([[f["path"], f["status"], now.get(f["path"])] for f in files]).encode())
    diff, deployed = [], _state(t) / "deployed"
    for f in files:
        new, old = site / f["path"], deployed / f["path"]
        if f["status"] == "added" and not before:
            continue  # first deploy: the file list is the diff
        a = old.read_text(encoding="utf-8", errors="replace").splitlines(True) if old.is_file() and _texty(old) else []
        b = new.read_text(encoding="utf-8", errors="replace").splitlines(True) if new.is_file() and _texty(new) else []
        if (old.is_file() and not _texty(old)) or (new.is_file() and not _texty(new)):
            diff.append(f"Binary file {f['path']} {f['status']}\n")
            continue
        diff.extend(difflib.unified_diff(a, b, f"deployed/{f['path']}", f"local/{f['path']}"))
    text = "".join(diff)
    return {"files": files, "diff": text[:deploy.MAX_DIFF_CHARS], "diff_truncated": len(text) > deploy.MAX_DIFF_CHARS,
            "change_id": h.hexdigest()[:16], "secrets": deploy.scan(site, files), "target": public(t),
            "first_deploy": not before, "repo": {"site_url": t.get("site_url"), "remote": _where(t), "branch": "-"},
            "head": "-", "unpushed_commits": [], "can_rollback": _last_backup(t) is not None}


def _texty(p: Path) -> bool:
    return p.stat().st_size < 2_000_000 and b"\0" not in p.read_bytes()[:4096]


def _where(t: dict) -> str:
    if t["type"] == "folder":
        return t["folder"]
    return f"{t['type']}://{t['user']}@{t['host']}:{t['port']}{t['remote_path']}"


def _last_backup(t: dict) -> Path | None:
    b = _state(t) / "backups"
    metas = sorted(b.glob("*/meta.json")) if b.exists() else []
    return metas[-1].parent if metas else None


def run_deploy(t: dict, message: str, change_id: str, log=print) -> dict:
    if t["type"] == "git":
        return deploy.deploy(Path(t["site"]), message, change_id, log=log)
    r = review(t)
    if not r["files"]:
        raise TargetError("nothing to deploy")
    if r["change_id"] != change_id:
        raise TargetError("the files changed after you reviewed them; review again")
    if r["secrets"]:
        raise TargetError("secret-looking content found: " + ", ".join(f"{s['path']} ({s['kind']})" for s in r["secrets"]))
    site, state = Path(t["site"]), _state(t)
    base_stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
    while True:  # unique and sortable even for two deploys in the same second
        stamp = f"{base_stamp}-{n:03d}"
        bdir = state / "backups" / stamp
        try:
            bdir.mkdir(parents=True)
            break
        except FileExistsError:
            n += 1
    before = _manifest(t)
    meta = {"at": stamp, "message": message, "added": [], "replaced": [], "deleted": [], "manifest_before": before}
    log(f"connect: {_where(t)}")
    with transport(t) as tr:
        for f in r["files"]:  # 1. back up what is on the server now
            if f["status"] in ("modified", "deleted") or (f["status"] == "added" and not before):
                if tr.get(f["path"], bdir / "files" / f["path"]):
                    meta["replaced" if f["status"] != "deleted" else "deleted"].append(f["path"])
                elif f["status"] != "deleted":
                    meta["added"].append(f["path"])
            elif f["status"] == "added":
                meta["added"].append(f["path"])
        log(f"backup: {len(meta['replaced']) + len(meta['deleted'])} file(s) saved locally")
        (bdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        for f in r["files"]:  # 2. upload / delete
            if f["status"] == "deleted":
                tr.delete(f["path"])
            else:
                tr.put(site / f["path"], f["path"])
        log(f"upload: {sum(f['status'] != 'deleted' for f in r['files'])} file(s), delete: "
            f"{sum(f['status'] == 'deleted' for f in r['files'])}")
    now = local_files(site)  # 3. remember what is deployed
    deployed = state / "deployed"
    for f in r["files"]:
        dst = deployed / f["path"]
        if f["status"] == "deleted":
            dst.unlink(missing_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(site / f["path"], dst)
    (state / "manifest.json").write_text(json.dumps(now, indent=1), encoding="utf-8")
    result = {"ok": True, "site_url": t.get("site_url"), "verified": [], "backup": stamp}
    if t.get("site_url"):  # 4. check the live site
        paths = [f["path"] for f in r["files"] if f["status"] != "deleted"][:8]
        result["verified"] = verify_urls(t["site_url"], site, paths, log)
        result["ok"] = all(v["match"] for v in result["verified"])
    log("done" if result["ok"] else "uploaded, but the live site does not match yet (cache?)")
    return result


def verify_urls(site_url: str, site: Path, paths: list[str], log, wait_sec: int = 90) -> list[dict]:
    out, deadline = [], time.time() + wait_sec
    for p in paths:
        want, match, url = (site / p).read_bytes(), False, site_url + p
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"{url}?v={int(time.time())}", headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    match = resp.read() == want
            except OSError:
                match = False
            if match:
                break
            time.sleep(4)
        log(f"live {'OK ' if match else 'DIFF'} {p}")
        out.append({"path": p, "url": url, "match": match})
    return out


def rollback(t: dict, log=print) -> dict:
    """Undo the last deploy of this target (one step)."""
    if t["type"] == "git":
        site = Path(t["site"])
        if deploy.review(site)["files"]:
            raise TargetError("save or discard your local edits before rolling back")
        last = deploy.git(site, "log", "-1", "--format=%h %s").strip()
        log(f"revert: {last}")
        deploy.git(site, "revert", "--no-edit", "HEAD")
        r = deploy.review(site)
        return deploy.deploy(site, "", r["change_id"], log=log)
    bdir = _last_backup(t)
    if bdir is None:
        raise TargetError("no deploy to roll back")
    meta = json.loads((bdir / "meta.json").read_text(encoding="utf-8"))
    log(f"rollback deploy {meta['at']} on {_where(t)}")
    with transport(t) as tr:
        for p in meta["replaced"] + meta["deleted"]:
            tr.put(bdir / "files" / p, p)
        for p in meta["added"]:
            tr.delete(p)
    state = _state(t)
    (state / "manifest.json").write_text(json.dumps(meta["manifest_before"], indent=1), encoding="utf-8")
    deployed = state / "deployed"
    for p in meta["replaced"] + meta["deleted"]:
        (deployed / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bdir / "files" / p, deployed / p)
    for p in meta["added"]:
        (deployed / p).unlink(missing_ok=True)
    os.replace(bdir / "meta.json", bdir / "meta.rolled-back.json")  # one step: this backup is used up
    log(f"restored {len(meta['replaced']) + len(meta['deleted'])} file(s), removed {len(meta['added'])}")
    return {"ok": True, "rolled_back": meta["at"]}
