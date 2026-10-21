"""Site editor app: a home screen of projects, visual + form editing, and deploy.

    start.cmd / desktop shortcut      -> launcher.py (one server per user, one app window)
    python editor.py --site FOLDER    -> open one folder directly (it joins the home screen)

Home (/): recent projects with live thumbnails, new from template, open a folder on
this PC, upload a folder or zip, search, rename, duplicate, remove from list, delete
(tool-managed copies only, into a recoverable trash), export zip, settings.

Project (/p/<id>/): Design (click, resize with handles, drag blocks, type in place with a
floating toolbar), Content form, Files, History; autosave with undo across saves; deploy
to the project's own targets (GitHub Pages / SFTP / FTP(S) / folder) after review.

Safety: binds to 127.0.0.1, checks Host, pages need the session cookie (SameSite=Strict,
set from the launcher's one-time URL token), every API call needs the token header.
Passwords go straight to the OS credential store and never come back to the browser.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import credstore
import deploy
import htmlmap
import importer
import jsdata
import launcher
import projects
import styles
import targets
import thumbs

HERE = Path(__file__).resolve().parent
TEXT_EXT = {".html", ".htm", ".css", ".js", ".md", ".json", ".txt", ".xml"}
HTML_EXT = {".html", ".htm"}
IMAGE_EXT = {".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff", ".gif": b"GIF8", ".webp": b"RIFF"}
MAX_UPLOAD = 3 * 1024 * 1024
MAX_BODY = 6 * 1024 * 1024
SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
KEEP_SNAPSHOTS = 400


class Editor:
    def __init__(self, site: Path, data_file: str = "content.js", history_dir: Path | None = None):
        self.site = site.resolve()
        if not self.site.is_dir():
            raise SystemExit(f"{self.site} is not a folder")
        self.is_git = (self.site / ".git").exists()
        self.data_file = data_file
        self.history = (history_dir or HERE / ".history") / self.site.name
        self.jobs: dict = {"state": "idle", "log": []}
        self.draft: str | None = None              # unsaved data file text (preview only)
        self.draft_html: dict[str, list] = {}      # unsaved HTML edits per page (preview only)
        self.lock = threading.Lock()

    # -- paths -------------------------------------------------------------
    def resolve(self, rel: str) -> Path:
        p = (self.site / unquote(rel).lstrip("/")).resolve()
        if p != self.site and self.site not in p.parents:
            raise PermissionError("path outside the site")
        if ".git" in p.relative_to(self.site).parts:
            raise PermissionError("the .git folder is not editable")
        return p

    def rel(self, p: Path) -> str:
        return p.relative_to(self.site).as_posix()

    # -- history -----------------------------------------------------------
    def snapshot(self, path: Path, reason: str) -> str | None:
        if not path.exists():
            return None
        rel = self.rel(path)
        self.history.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
        name = f"{stamp}__{rel.replace('/', '~')}"
        while (self.history / name).exists():
            name = name.replace("__", "_x__", 1)
        shutil.copy2(path, self.history / name)
        (self.history / (name + ".meta")).write_text(json.dumps({"path": rel, "reason": reason}), encoding="utf-8")
        metas = sorted(self.history.glob("*.meta"))
        for old in metas[:-KEEP_SNAPSHOTS]:  # autosave makes many snapshots: keep the newest ones
            (self.history / old.name[:-5]).unlink(missing_ok=True)
            old.unlink(missing_ok=True)
        return name

    def list_history(self) -> list[dict]:
        if not self.history.exists():
            return []
        out = []
        for meta in sorted(self.history.glob("*.meta"), reverse=True)[:150]:
            info = json.loads(meta.read_text(encoding="utf-8"))
            sid = meta.name[:-5]
            out.append({"id": sid, "path": info["path"], "reason": info.get("reason", ""),
                        "at": sid.split("__")[0], "size": (self.history / sid).stat().st_size})
        return out

    def restore(self, sid: str) -> dict:
        if "/" in sid or "\\" in sid or ".." in sid:
            raise PermissionError("bad snapshot id")
        meta = json.loads((self.history / (sid + ".meta")).read_text(encoding="utf-8"))
        dst = self.resolve(meta["path"])
        self.snapshot(dst, f"before restoring {sid}")
        shutil.copy2(self.history / sid, dst)
        return {"restored": meta["path"]}

    def discard(self, rel: str) -> dict:
        """Put a file back to the last committed version (git sites), keeping a snapshot."""
        if not self.is_git:
            raise PermissionError("this site is not a git repository; use History to restore a snapshot")
        p = self.resolve(rel)
        self.snapshot(p, "before discarding local changes")
        if deploy.git(self.site, "ls-files", "--", rel).strip():
            deploy.git(self.site, "checkout", "HEAD", "--", rel)
        elif p.exists():
            p.unlink()
        return {"discarded": rel}

    # -- content -----------------------------------------------------------
    def read_content(self) -> dict:
        p = self.resolve(self.data_file)
        if not p.exists():
            return {"available": False}
        name, data = jsdata.parse(p.read_text(encoding="utf-8"))
        return {"available": True, "name": name, "data": data, "file": self.data_file}

    def set_draft(self, data, name: str = "SITE", html: dict | None = None) -> dict:
        if data is None:
            self.draft = None
        elif isinstance(data, dict):
            self.draft = jsdata.dump(name, data)
        elif data != "keep":
            raise ValueError("content must be an object")
        if html is not None:
            page, edits = html.get("page"), html.get("edits") or []
            self.resolve(page)
            if edits:
                self.draft_html[page] = edits
            else:
                self.draft_html.pop(page, None)
        return {"draft": self.draft is not None, "html_pages": sorted(self.draft_html)}

    # -- pages, styles -----------------------------------------------------
    def pages(self) -> list[str]:
        out = []
        for p in sorted(self.site.rglob("*")):
            r = p.relative_to(self.site)
            if p.is_file() and p.suffix.lower() in HTML_EXT and not ({".git", "node_modules"} & set(r.parts)):
                out.append(r.as_posix())
        return sorted(out, key=lambda s: (s != "index.html", s))

    def read_styles(self) -> dict:
        p = self.site / styles.FILE
        rules = styles.parse(p.read_text(encoding="utf-8")) if p.exists() else []
        return {"rules": rules, "warnings": styles.warnings(rules), "fonts": sorted(styles.FONT_IMPORTS)}

    def plan(self, body: dict) -> dict[str, str]:
        """New text for every file the save would change: {rel: text}."""
        out: dict[str, str] = {}
        if "data" in body and body["data"] is not None:
            text = jsdata.dump(body.get("name", "SITE"), body["data"])
            jsdata.parse(text)
            out[self.data_file] = text
        if "rules" in body and body["rules"] is not None:
            rules = styles.validate(body["rules"])
            css_path = self.site / styles.FILE
            if rules or css_path.exists():
                out[styles.FILE] = styles.render(rules)
            if rules:
                for page in self.pages():
                    p = self.resolve(page)
                    html = p.read_text(encoding="utf-8")
                    linked = styles.ensure_link(html)
                    if linked != html:
                        out[page] = linked
        if body.get("page") and body.get("html_edits"):
            page = body["page"]
            p = self.resolve(page)
            if p.suffix.lower() not in HTML_EXT:
                raise ValueError("HTML edits need an .html page")
            base = out.get(page, p.read_text(encoding="utf-8"))
            # edits address ids of the saved file; the <link> (if added) is in <head>, outside <body>
            out[page] = htmlmap.apply(base, body["html_edits"])
        # drop no-op entries
        return {k: v for k, v in out.items() if not (self.site / k).exists()
                or (self.site / k).read_text(encoding="utf-8") != v}

    def preview_diff(self, body: dict) -> dict:
        changes = self.plan(body)
        parts = []
        for rel, new in sorted(changes.items()):
            p = self.site / rel
            old = p.read_text(encoding="utf-8").splitlines(True) if p.exists() else []
            parts.append("".join(difflib.unified_diff(old, new.splitlines(True), f"saved/{rel}", f"new/{rel}")))
        warn = styles.warnings(styles.validate(body.get("rules") or [])) if body.get("rules") else []
        return {"files": sorted(changes), "diff": "\n".join(parts), "warnings": warn}

    def save_all(self, body: dict, reason: str = "saved from editor") -> dict:
        """Write the planned files. Returns the snapshot ids of the previous versions and the
        files that did not exist before: everything restore_many() needs to undo this save."""
        with self.lock:
            changes = self.plan(body)
            snaps, created = [], []
            for rel, text in changes.items():
                p = self.resolve(rel)
                sid = self.snapshot(p, reason)
                if sid:
                    snaps.append(sid)
                else:
                    created.append(rel)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8", newline="\n")
            if "data" in body:
                self.draft = None
            if body.get("page"):
                self.draft_html.pop(body["page"], None)
        return {"saved": sorted(changes), "snapshots": snaps, "created": created, "at": time.time()}

    def restore_many(self, ids: list[str], created: list[str]) -> dict:
        """Undo one save: put back the previous versions and remove files that the save created."""
        with self.lock:
            for sid in ids:
                self.restore(sid)
            for rel in created:
                p = self.resolve(rel)
                if p.exists():
                    self.snapshot(p, "before undo removed it")
                    p.unlink()
        return {"restored": len(ids), "removed": len(created)}

    # -- files -------------------------------------------------------------
    def list_files(self) -> list[str]:
        out = []
        for p in sorted(self.site.rglob("*")):
            r = p.relative_to(self.site)
            if p.is_file() and ".git" not in r.parts and p.suffix.lower() in TEXT_EXT:
                out.append(r.as_posix())
        return out

    def read_file(self, rel: str) -> dict:
        p = self.resolve(rel)
        if p.suffix.lower() not in TEXT_EXT:
            raise PermissionError("not an editable text file")
        return {"path": rel, "text": p.read_text(encoding="utf-8")}

    def write_file(self, rel: str, text: str) -> dict:
        p = self.resolve(rel)
        if p.suffix.lower() not in TEXT_EXT:
            raise PermissionError("not an editable text file")
        if rel == self.data_file:
            jsdata.parse(text)
        if rel == styles.FILE:
            styles.validate(styles.parse(text))
        with self.lock:
            self.snapshot(p, "file saved")
            p.write_text(text, encoding="utf-8", newline="\n")
        return {"saved": rel}

    def upload(self, name: str, b64: str) -> dict:
        data = base64.b64decode(b64, validate=True)
        if len(data) > MAX_UPLOAD:
            raise ValueError("image is larger than 3 MB")
        stem, ext = Path(name).stem, Path(name).suffix.lower()
        if ext not in IMAGE_EXT or not data.startswith(IMAGE_EXT[ext]):
            raise ValueError("only real PNG, JPG, GIF or WEBP images are accepted")
        stem = SAFE_NAME.sub("-", stem).strip("-.")[:60] or "image"
        folder = self.resolve("assets/img")
        folder.mkdir(parents=True, exist_ok=True)
        target, i = folder / f"{stem}{ext}", 1
        while target.exists():
            target, i = folder / f"{stem}-{i}{ext}", i + 1
        target.write_bytes(data)
        return {"path": self.rel(target)}

    # -- targets & deploy ----------------------------------------------------
    def targets(self) -> list[dict]:
        items = targets.for_site(self.site)
        if self.is_git and not any(t["type"] == "git" for t in items):
            info = deploy.repo_info(self.site)
            targets.save(self.site, {"type": "git", "name": "GitHub Pages" if info["owner"] else "git push",
                                     "site_url": info["site_url"] or ""})
            items = targets.for_site(self.site)
        return [targets.public(t) for t in items]

    def target(self, tid: str) -> dict:
        t = targets.get(tid)
        if t.get("site") != str(self.site):
            raise PermissionError("that target belongs to another site")
        return t

    def _run_job(self, fn, *args) -> dict:
        with self.lock:
            if self.jobs["state"] == "running":
                raise RuntimeError("a deploy or rollback is already running")
            self.jobs = {"state": "running", "log": [], "result": None, "error": None}
        job = self.jobs

        def run():
            try:
                job["result"] = fn(*args, log=lambda s: job["log"].append(str(s)))
                job["state"] = "done"
            except Exception as e:  # noqa: BLE001 - shown in the UI
                job["error"], job["state"] = str(e), "failed"

        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    def start_deploy(self, tid: str, message: str, change_id: str) -> dict:
        return self._run_job(targets.run_deploy, self.target(tid), message, change_id)

    def start_rollback(self, tid: str) -> dict:
        return self._run_job(targets.rollback, self.target(tid))


class App:
    """All projects in one local server: the home screen at /, each project at /p/<id>/."""

    def __init__(self, token: str, port: int):
        self.token, self.port = token, port
        self.editors: dict[str, Editor] = {}
        self.lock = threading.Lock()
        self.import_job: dict = {"state": "idle", "log": []}

    def start_import(self, url: str, name: str | None, max_pages: int, rendered: bool) -> dict:
        importer.normalize(url)  # reject bad addresses before starting
        with self.lock:
            if self.import_job["state"] == "running":
                raise RuntimeError("다른 사이트를 가져오는 중입니다")
            job = self.import_job = {"state": "running", "log": [], "result": None, "error": None}

        def run():
            try:
                job["result"] = importer.import_site(url, name or None, max_pages, rendered, log=lambda m: job["log"].append(str(m)))
                job["state"] = "done"
            except Exception as e:  # noqa: BLE001 - shown in the home screen
                job["error"], job["state"] = str(e), "failed"

        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    def editor(self, pid: str) -> Editor:
        p = projects.get(pid)
        with self.lock:
            ed = self.editors.get(pid)
            if ed is None or str(ed.site) != str(Path(p["path"]).resolve()):
                ed = Editor(Path(p["path"]))
                self.editors[pid] = ed
        return ed


COOKIE = "se_token"
PID_RE = re.compile(r"^/p/([0-9a-f]{6,32})(/.*)?$")


def make_handler(app: App):
    static = HERE / "static"
    token, port = app.token, app.port
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    head_snippet = ('<style id="__se_live"></style>'
                    '<script src="/static/bridge.js" defer></script>')
    csp = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
           "https://cdn.jsdelivr.net; font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
           "script-src 'self' 'unsafe-inline'; frame-src 'self'; connect-src 'self'")

    class Handler(BaseHTTPRequestHandler):
        server_version = "SiteEditor"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet: request lines may contain the token
            pass

        # -- plumbing ----------------------------------------------------------
        def _send(self, code, body: bytes, ctype: str, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            if self.headers.get("Host") not in allowed_hosts:
                self._send(403, b"bad host", "text/plain")
                return False
            return True

        def _cookie_ok(self) -> bool:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == COOKIE and secrets.compare_digest(v, token):
                    return True
            return False

        def _api_ok(self) -> bool:
            if secrets.compare_digest(self.headers.get("X-Editor-Token", ""), token):
                return True
            self._json({"error": "bad or missing token"}, 403)
            return False

        def _body_bytes(self, limit=MAX_BODY) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("request too large")
            return self.rfile.read(n) if n else b""

        def _body(self) -> dict:
            return json.loads(self._body_bytes() or b"{}")

        def _page(self, name: str, base: str = "", title: str = ""):
            html = (static / name).read_text(encoding="utf-8")
            html = html.replace("__TOKEN__", token).replace("__BASE__", base).replace("__SITE__", title)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": csp})

        # -- GET ---------------------------------------------------------------
        def do_GET(self):
            if not self._host_ok():
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/ping":
                return self._json({"app": "site-editor"})
            if u.path.startswith("/static/"):
                return self._static(u.path[len("/static/"):])
            if "t" in q and secrets.compare_digest(q["t"], token):  # first visit: trade the URL token for a cookie
                return self._send(302, b"", "text/plain", {"Location": u.path or "/",
                                  "Set-Cookie": f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/"})
            if u.path.startswith("/api/"):
                if not self._api_ok():
                    return
                return self._api("GET", u.path, q)
            m = PID_RE.match(u.path)
            if m and (m.group(2) or "").startswith("/thumb/"):
                # home-screen thumbnails: the site runs in a sandbox (opaque origin, no access to the editor)
                try:
                    ed = app.editor(m.group(1))
                except projects.ProjectError:
                    return self._send(404, b"not found", "text/plain")
                return self._serve_site(ed, m.group(2)[len("/thumb/"):], "disk",
                                        extra={"Content-Security-Policy": "sandbox allow-scripts"})
            if not self._cookie_ok():
                return self._send(403, "Open the editor from its shortcut (or the URL printed by editor.py).".encode(),
                                  "text/plain; charset=utf-8")
            if u.path in ("/", "/index.html"):
                return self._page("home.html")
            m = PID_RE.match(u.path)
            if m:
                pid, rest = m.group(1), m.group(2) or "/"
                if rest == "/" or rest == "":
                    try:
                        p = projects.get(pid)
                    except projects.ProjectError:
                        return self._send(302, b"", "text/plain", {"Location": "/"})
                    projects.touch(pid)
                    return self._page("editor.html", base=f"/p/{pid}", title=p["name"])
                if rest == "/thumb.png":
                    try:
                        p = projects.describe(projects.get(pid))
                    except projects.ProjectError:
                        return self._send(404, b"not found", "text/plain")
                    shot = thumbs.get(pid, p["path"], f"http://127.0.0.1:{port}/p/{pid}/thumb/{p['entry'] or 'index.html'}") \
                        if p["exists"] and p["entry"] else None
                    if not shot:
                        return self._send(404, b"no thumbnail", "text/plain")
                    return self._send(200, shot.read_bytes(), "image/png")
                if rest == "/export.zip":
                    name, data = projects.export_zip(pid)
                    return self._send(200, data, "application/zip",
                                      {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
                for prefix, mode in (("/design/", "design"), ("/preview/", "preview"), ("/site/", "disk")):
                    if rest.startswith(prefix) or rest == prefix.rstrip("/"):
                        return self._serve_site(app.editor(pid), rest[len(prefix):], mode)
            self._send(404, b"not found", "text/plain")

        def _static(self, name: str):
            p = (static / unquote(name)).resolve()
            if static.resolve() not in p.parents or not p.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, p.read_bytes(), ctype)

        def _serve_site(self, ed: Editor, rel: str, mode: str, extra=None):
            rel = unquote(rel) or "index.html"
            if mode != "disk" and ed.draft is not None and rel == ed.data_file:
                return self._send(200, ed.draft.encode("utf-8"), "application/javascript; charset=utf-8")
            if mode == "design" and rel == styles.FILE:
                return self._send(200, b"", "text/css; charset=utf-8")  # live rules come from the editor instead
            try:
                p = ed.resolve(rel)
                if p.is_dir():
                    p, rel = p / "index.html", (rel.rstrip("/") + "/index.html").lstrip("/")
                data = p.read_bytes()
            except (PermissionError, OSError):
                return self._send(404, b"not found", "text/plain")
            if mode == "design" and p.suffix.lower() in HTML_EXT:
                try:
                    inst = htmlmap.instrument(data.decode("utf-8"))
                    if ed.draft_html.get(rel):
                        inst = htmlmap.apply_instrumented(inst, ed.draft_html[rel])
                except (UnicodeDecodeError, htmlmap.EditError) as e:
                    return self._send(500, f"cannot open this page for design: {e}".encode(), "text/plain; charset=utf-8")
                return self._send(200, htmlmap.inject_head(inst, head_snippet).encode("utf-8"), "text/html; charset=utf-8")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            return self._send(200, data, ctype, extra)

        # -- POST --------------------------------------------------------------
        def do_POST(self):
            if not self._host_ok():
                return
            u = urlparse(self.path)
            if not u.path.startswith("/api/") or not self._api_ok():
                return
            self._api("POST", u.path, {k: v[0] for k, v in parse_qs(u.query).items()})

        def _api(self, method: str, path: str, q: dict):
            try:
                m = re.match(r"^/api/p/([0-9a-f]{6,32})(/.*)$", path)
                if m:
                    return self._project_api(method, app.editor(m.group(1)), m.group(1), m.group(2), q)
                return self._home_api(method, path, q)
            except (KeyError, ValueError, PermissionError, RuntimeError, OSError, jsdata.DataError, deploy.DeployError,
                    htmlmap.EditError, styles.StyleError, targets.TargetError, projects.ProjectError,
                    importer.ImportError_) as e:
                return self._json({"error": str(e)}, 400)

        def _home_api(self, method, path, q):
            if method == "GET":
                if path == "/api/projects":
                    items = projects.list_all(q.get("q", ""))
                    tmap = {}
                    for t in targets.load_all():
                        tmap.setdefault(t.get("site"), []).append({"type": t["type"], "name": t.get("name")})
                    for it in items:
                        it["targets"] = tmap.get(str(Path(it["path"]).resolve()), [])
                    return self._json({"projects": items, "storage": str(projects.storage_root())})
                if path == "/api/projects/import":
                    return self._json(app.import_job)
                if path == "/api/settings":
                    return self._json({"storage": str(projects.storage_root()), "startup": launcher.startup_enabled(),
                                       "secret_store": credstore.backend(), "templates":
                                       {k: v[0] for k, v in projects.TEMPLATES.items()}})
            else:
                if path == "/api/projects/upload-file":  # raw bytes, not JSON
                    projects.upload_file(q["upload"], q["path"], self._body_bytes(projects.MAX_UPLOAD_BYTES))
                    return self._json({"ok": True})
                if path == "/api/projects/upload-zip":
                    return self._json(projects.upload_zip(q.get("name") or "업로드한 사이트",
                                                          self._body_bytes(projects.MAX_UPLOAD_BYTES)))
                b = self._body()
                if path == "/api/projects/new":
                    return self._json(projects.create(b["name"], b.get("template", "blank")))
                if path == "/api/projects/open":
                    folder = b.get("path") or projects.pick_folder()
                    if not folder:
                        return self._json({"cancelled": True})
                    return self._json(projects.add_folder(folder))
                if path == "/api/projects/import":
                    return self._json(app.start_import(b["url"], b.get("name"), int(b.get("max_pages") or 20),
                                                       bool(b.get("rendered"))))
                if path == "/api/projects/upload-start":
                    return self._json(projects.start_upload(b["name"]))
                if path == "/api/projects/upload-finish":
                    return self._json(projects.finish_upload(b["upload"]))
                if path == "/api/projects/rename":
                    return self._json(projects.rename(b["id"], b["name"]))
                if path == "/api/projects/duplicate":
                    return self._json(projects.duplicate(b["id"], b.get("name")))
                if path == "/api/projects/remove":
                    app.editors.pop(b["id"], None)
                    return self._json(projects.remove(b["id"]))
                if path == "/api/projects/delete":
                    app.editors.pop(b["id"], None)
                    return self._json(projects.delete(b["id"], b.get("confirm", "")))
                if path == "/api/projects/reveal":
                    folder = projects.get(b["id"])["path"]
                    if os.name == "nt":
                        os.startfile(folder)  # noqa: S606 - opens Explorer on the user's own folder
                    return self._json({"ok": True})
                if path == "/api/install":
                    return self._json(launcher.install())
                if path == "/api/settings":
                    s = projects.settings()
                    if "startup" in b:
                        launcher.set_startup(bool(b["startup"]))
                    if b.get("storage"):
                        root = Path(b["storage"]).expanduser()
                        root.mkdir(parents=True, exist_ok=True)
                        s["storage"] = str(root.resolve())
                    projects.save_settings(s)
                    return self._json({"ok": True, "startup": launcher.startup_enabled(), "storage": str(projects.storage_root())})
            return self._json({"error": "unknown endpoint"}, 404)

        def _project_api(self, method, ed: Editor, pid: str, sub: str, q: dict):
            if method == "GET":
                if sub == "/content":
                    return self._json(ed.read_content())
                if sub == "/pages":
                    return self._json({"pages": ed.pages()})
                if sub == "/styles":
                    return self._json(ed.read_styles())
                if sub == "/files":
                    return self._json({"files": ed.list_files(), "data_file": ed.data_file})
                if sub == "/file":
                    return self._json(ed.read_file(q["path"]))
                if sub == "/history":
                    return self._json({"items": ed.list_history()})
                if sub == "/targets":
                    return self._json({"targets": ed.targets(), "is_git": ed.is_git})
                if sub == "/review":
                    return self._json(targets.review(ed.target(q["target"])))
                if sub == "/job":
                    return self._json(ed.jobs)
                if sub == "/info":
                    p = projects.get(pid)
                    return self._json({**p, "is_git": ed.is_git})
                return self._json({"error": "unknown endpoint"}, 404)
            b = self._body()
            if sub == "/save":
                return self._json(ed.save_all(b, "autosave" if b.get("auto") else "saved from editor"))
            if sub == "/restore-many":
                return self._json(ed.restore_many(b.get("ids") or [], b.get("created") or []))
            if sub == "/preview-diff":
                return self._json(ed.preview_diff(b))
            if sub == "/draft":
                return self._json(ed.set_draft(b.get("data", "keep"), b.get("name", "SITE"), b.get("html")))
            if sub == "/file":
                return self._json(ed.write_file(b["path"], b["text"]))
            if sub == "/upload":
                return self._json(ed.upload(b["name"], b["data"]))
            if sub == "/restore":
                return self._json(ed.restore(b["id"]))
            if sub == "/discard":
                return self._json(ed.discard(b["path"]))
            if sub == "/targets":
                pw = b.pop("password", None) or None
                return self._json(targets.save(ed.site, b, pw))
            if sub == "/targets/delete":
                ed.target(b["id"])
                targets.delete(b["id"])
                return self._json({"deleted": b["id"]})
            if sub == "/targets/test":
                return self._json({"message": targets.test_connection(ed.target(b["id"]))})
            if sub == "/deploy":
                if b.get("confirm") is not True:
                    return self._json({"error": "deploy needs explicit confirmation"}, 400)
                return self._json(ed.start_deploy(b["target"], b.get("message", ""), b["change_id"]))
            if sub == "/rollback":
                if b.get("confirm") is not True:
                    return self._json({"error": "rollback needs explicit confirmation"}, 400)
                return self._json(ed.start_rollback(b["target"]))
            return self._json({"error": "unknown endpoint"}, 404)

    return Handler


def serve(port: int, token: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(App(token, port)))


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Visual editor and deploy tool for HTML sites")
    ap.add_argument("--site", help="open this folder as a project (it is added to the home screen)")
    ap.add_argument("--app", action="store_true", help="run as the background app server (used by launcher.py)")
    ap.add_argument("--port", type=int, default=launcher.PORT)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    if launcher.ping(a.port):
        print("The editor is already running; opening it.")
        if a.site:
            p = projects.add_folder(a.site)
            launcher.open_window(launcher.url(f"/p/{p['id']}/"))
        else:
            launcher.open_app()
        return 0
    token = launcher.new_token()
    try:
        srv = serve(a.port, token)
    except OSError as e:
        print(f"cannot listen on 127.0.0.1:{a.port}: {e}", file=sys.stderr)
        return 1
    launcher.write_session(a.port, token)
    path = "/"
    if a.site:
        path = f"/p/{projects.add_folder(a.site)['id']}/"
    url = f"http://127.0.0.1:{a.port}{path}?t={token}"
    print(f"Site editor\nOpen: {url}\n(Ctrl+C to stop)", flush=True)
    if not a.no_browser:
        threading.Timer(0.5, lambda: launcher.open_window(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
