"""Project list for the home screen (like a document list in Google Docs).

A project is a site folder. It is either
  * linked:  an existing folder somewhere on this PC ("열기"), never moved or deleted by
             the tool; "remove" only takes it off the list, or
  * managed: a copy inside the tool's storage folder ("새로 만들기", "업로드", "복제"),
             which the tool may delete, and even then only into a recoverable trash.

The list lives in ~/.site-editor/projects.json (names, paths, dates; no secrets).
Deploy targets stay keyed by the folder path (targets.py), so every project
remembers its own servers.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import credstore

HOME = credstore.HOME
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".history", ".site-editor"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000
NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_lock = threading.Lock()


class ProjectError(ValueError):
    pass


# -- storage -------------------------------------------------------------------
def settings() -> dict:
    try:
        return json.loads((HOME / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "settings.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def storage_root() -> Path:
    root = settings().get("storage") or str(Path.home() / "Documents" / "SiteEditor Projects")
    return Path(root)


def _load() -> list[dict]:
    try:
        return json.loads((HOME / "projects.json").read_text(encoding="utf-8")).get("projects", [])
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = HOME / "projects.json.tmp"
    tmp.write_text(json.dumps({"projects": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, HOME / "projects.json")


def _now() -> float:
    return round(time.time(), 3)


def _clean_name(name: str) -> str:
    name = NAME_RE.sub("", str(name or "")).strip().strip(".")
    if not name:
        raise ProjectError("이름을 입력하세요")
    return name[:80]


def _unique_dir(base: Path, name: str) -> Path:
    p, i = base / name, 2
    while p.exists():
        p, i = base / f"{name} ({i})", i + 1
    return p


# -- queries -------------------------------------------------------------------
def last_modified(path: Path) -> float | None:
    newest = None
    count = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            count += 1
            if count > MAX_FILES:
                return newest
            try:
                m = os.stat(os.path.join(root, f)).st_mtime
            except OSError:
                continue
            newest = m if newest is None or m > newest else newest
    return newest


def entry_page(path: Path) -> str | None:
    if (path / "index.html").is_file():
        return "index.html"
    pages = sorted(p.relative_to(path).as_posix() for p in path.rglob("*.htm*")
                   if p.is_file() and not (SKIP_DIRS & set(p.relative_to(path).parts)))
    return pages[0] if pages else None


def describe(p: dict) -> dict:
    path = Path(p["path"])
    exists = path.is_dir()
    return {**p, "exists": exists, "modified": last_modified(path) if exists else None,
            "entry": entry_page(path) if exists else None, "is_git": exists and (path / ".git").exists()}


def list_all(query: str = "") -> list[dict]:
    q = query.strip().lower()
    items = [describe(p) for p in _load()]
    if q:
        items = [p for p in items if q in p["name"].lower() or q in p["path"].lower()]
    return sorted(items, key=lambda p: -(p.get("opened") or p.get("added") or 0))


def get(pid: str) -> dict:
    for p in _load():
        if p["id"] == pid:
            return p
    raise ProjectError("프로젝트를 찾을 수 없습니다")


def find_by_path(path: Path) -> dict | None:
    path = str(Path(path).resolve())
    return next((p for p in _load() if p["path"] == path), None)


# -- changes -------------------------------------------------------------------
def add_folder(path: str | Path, name: str | None = None, managed: bool = False) -> dict:
    path = Path(path).expanduser().resolve()
    if not path.is_dir():
        raise ProjectError(f"폴더가 없습니다: {path}")
    if entry_page(path) is None:
        raise ProjectError("이 폴더에는 HTML 파일이 없습니다. 사이트의 index.html 이 있는 폴더를 고르세요")
    with _lock:
        items = _load()
        old = next((p for p in items if p["path"] == str(path)), None)
        if old:
            return old
        p = {"id": uuid.uuid4().hex[:10], "name": _clean_name(name or path.name), "path": str(path),
             "managed": managed, "added": _now(), "opened": None}
        items.append(p)
        _save(items)
        return p


def set_meta(pid: str, **fields) -> dict:
    """Extra display info (e.g. where an imported site came from)."""
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pid:
                p.update({k: v for k, v in fields.items() if k in ("source_url", "imported")})
                _save(items)
                return p
    raise ProjectError("프로젝트를 찾을 수 없습니다")


def touch(pid: str) -> None:
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pid:
                p["opened"] = _now()
        _save(items)


def rename(pid: str, name: str) -> dict:
    with _lock:
        items = _load()
        for p in items:
            if p["id"] == pid:
                p["name"] = _clean_name(name)  # the display name only: folders and deploy targets stay put
                _save(items)
                return p
    raise ProjectError("프로젝트를 찾을 수 없습니다")


def remove(pid: str) -> dict:
    """Take a project off the list. Files are not touched."""
    with _lock:
        items = _load()
        p = next((x for x in items if x["id"] == pid), None)
        if not p:
            raise ProjectError("프로젝트를 찾을 수 없습니다")
        _save([x for x in items if x["id"] != pid])
        return p


def delete(pid: str, confirm_name: str) -> dict:
    """Managed projects only: move the folder into ~/.site-editor/trash (recoverable)."""
    p = get(pid)
    if not p.get("managed"):
        raise ProjectError("PC에서 연 폴더는 지우지 않습니다. 목록에서 빼기만 할 수 있습니다")
    if confirm_name != p["name"]:
        raise ProjectError("확인을 위해 프로젝트 이름을 정확히 입력하세요")
    src = Path(p["path"])
    trash = HOME / "trash" / f"{time.strftime('%Y%m%d-%H%M%S')}-{p['id']}"
    trash.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(trash))
    remove(pid)
    return {"trashed": str(trash)}


def _copytree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_DIRS))


def duplicate(pid: str, name: str | None = None) -> dict:
    p = get(pid)
    name = _clean_name(name or f"{p['name']} 사본")
    dst = _unique_dir(storage_root(), name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _copytree(Path(p["path"]), dst)
    return add_folder(dst, name, managed=True)


TEMPLATES = {
    "blank": ("빈 사이트", {
        "index.html": """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="top"><strong>{name}</strong></header>
  <main>
    <section class="hero">
      <h1>제목을 두 번 클릭해 바꾸세요</h1>
      <p>여기에 소개 글을 씁니다. 블록을 끌어 순서를 바꾸고, 손잡이로 크기를 바꿀 수 있습니다.</p>
    </section>
    <section class="block">
      <h2>두 번째 블록</h2>
      <p>필요 없으면 파일 탭에서 지우세요.</p>
    </section>
  </main>
  <footer class="foot">© {name}</footer>
</body>
</html>
""",
        "style.css": """* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; line-height: 1.7; color: #16181d; }
.top, .foot { padding: 1rem 1.25rem; border-bottom: 1px solid #e3e6eb; }
.foot { border-top: 1px solid #e3e6eb; border-bottom: 0; color: #5b6270; font-size: .9rem; }
main { max-width: 60rem; margin: 0 auto; padding: 0 1.25rem; }
.hero { padding: 4rem 0 2rem; }
.hero h1 { font-size: 2.4rem; line-height: 1.25; margin: 0 0 1rem; }
.block { padding: 2rem 0; border-top: 1px solid #e3e6eb; }
""",
    }),
}


EXAMPLES = Path(__file__).resolve().parent / "examples"
TEMPLATES["example-ko"] = ("예시 사이트 (카페)", EXAMPLES / "cafe-ko")
TEMPLATES["example-en"] = ("Example site (café)", EXAMPLES / "cafe-en")


def create(name: str, template: str = "blank") -> dict:
    if template not in TEMPLATES:
        raise ProjectError("알 수 없는 서식입니다")
    name = _clean_name(name)
    dst = _unique_dir(storage_root(), name)
    src = TEMPLATES[template][1]
    if isinstance(src, Path):  # a ready-made example site: copy it as is
        dst.parent.mkdir(parents=True, exist_ok=True)
        _copytree(src, dst)
    else:
        dst.mkdir(parents=True)
        for rel, text in src.items():
            (dst / rel).write_text(text.replace("{name}", name), encoding="utf-8", newline="\n")
    return add_folder(dst, name, managed=True)


def safe_rel(rel: str) -> str:
    p = PurePosixPath(str(rel).replace("\\", "/"))
    if p.is_absolute() or not p.parts or any(part in ("..", "") or ":" in part for part in p.parts):
        raise ProjectError(f"잘못된 파일 경로: {rel}")
    if SKIP_DIRS & set(p.parts):
        return ""
    return p.as_posix()


def start_upload(name: str) -> dict:
    """An empty managed folder that upload_file() fills; registered when finish_upload() finds a page."""
    name = _clean_name(name)
    dst = _unique_dir(storage_root(), name)
    dst.mkdir(parents=True)
    token = uuid.uuid4().hex[:12]
    (dst / ".site-editor-upload").write_text(json.dumps({"token": token, "name": name, "bytes": 0}), encoding="utf-8")
    return {"upload": token, "folder": str(dst)}


def _upload_dir(token: str) -> Path:
    root = storage_root()
    for d in root.iterdir() if root.exists() else []:
        marker = d / ".site-editor-upload"
        if marker.is_file() and json.loads(marker.read_text(encoding="utf-8")).get("token") == token:
            return d
    raise ProjectError("업로드를 찾을 수 없습니다")


def upload_file(token: str, rel: str, data: bytes) -> None:
    d = _upload_dir(token)
    rel = safe_rel(rel)
    if not rel:
        return
    marker = d / ".site-editor-upload"
    info = json.loads(marker.read_text(encoding="utf-8"))
    info["bytes"] += len(data)
    if info["bytes"] > MAX_UPLOAD_BYTES:
        raise ProjectError("업로드가 200MB를 넘습니다")
    marker.write_text(json.dumps(info), encoding="utf-8")
    target = (d / rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _flatten_single_dir(d: Path) -> None:
    """A folder uploaded as 'site/index.html' becomes 'index.html' at the top."""
    while True:
        kids = [k for k in d.iterdir() if k.name != ".site-editor-upload"]
        if len(kids) == 1 and kids[0].is_dir() and not (d / "index.html").exists():
            inner = kids[0]
            for k in list(inner.iterdir()):
                shutil.move(str(k), str(d / k.name))
            inner.rmdir()
        else:
            return


def finish_upload(token: str) -> dict:
    d = _upload_dir(token)
    info = json.loads((d / ".site-editor-upload").read_text(encoding="utf-8"))
    (d / ".site-editor-upload").unlink()
    _flatten_single_dir(d)
    if entry_page(d) is None:
        shutil.rmtree(d, ignore_errors=True)
        raise ProjectError("올린 파일에 HTML 페이지가 없습니다")
    return add_folder(d, info["name"], managed=True)


def upload_zip(name: str, data: bytes) -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ProjectError("zip 이 200MB를 넘습니다")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ProjectError("zip 파일이 아닙니다") from None
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise ProjectError("파일이 너무 많습니다")
    if sum(i.file_size for i in infos) > MAX_UPLOAD_BYTES * 2:
        raise ProjectError("압축을 풀면 너무 큽니다")
    up = start_upload(name)
    try:
        for i in infos:
            rel = safe_rel(i.filename)  # rejects ../ and absolute paths (zip slip)
            if rel:
                upload_file(up["upload"], rel, zf.read(i))
        return finish_upload(up["upload"])
    except Exception:
        shutil.rmtree(up["folder"], ignore_errors=True)
        raise


def export_zip(pid: str) -> tuple[str, bytes]:
    p = get(pid)
    root = Path(p["path"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for f in sorted(files):
                full = Path(dirpath, f)
                zf.write(full, full.relative_to(root).as_posix())
    safe = re.sub(r"[^\w.-]+", "-", p["name"]).strip("-") or "site"
    return f"{safe}.zip", buf.getvalue()


def pick_folder() -> str | None:
    """Native 'choose folder' dialog on this PC (the browser cannot give us a folder path)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        raise ProjectError("이 PC의 Python 에 폴더 선택 창(tkinter)이 없습니다. 경로를 직접 입력하세요") from None
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        path = filedialog.askdirectory(title="사이트 폴더 고르기 (index.html 이 있는 폴더)", mustexist=True)
    finally:
        root.destroy()
    return path or None
