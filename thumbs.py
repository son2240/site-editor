"""Home-screen thumbnails: a real screenshot of each project's first page.

Taken with the PC's own Edge/Chrome in headless mode (no window), from the sandboxed
/p/<id>/thumb/ route, and cached in ~/.site-editor/thumbs/<id>.png until a file of the
project changes. Without such a browser the home screen shows a plain placeholder.
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import credstore
import launcher
import projects

DIR = credstore.HOME / "thumbs"
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def path_for(pid: str) -> Path:
    return DIR / f"{pid}.png"


def fresh(pid: str, project_path: str) -> bool:
    p = path_for(pid)
    if not p.exists():
        return False
    newest = projects.last_modified(Path(project_path)) or 0
    return p.stat().st_mtime >= newest


def render(pid: str, url: str, timeout: float = 25) -> Path | None:
    exe = launcher._app_browser()
    if not exe:
        return None
    with _guard:
        lock = _locks.setdefault(pid, threading.Lock())
    with lock:
        DIR.mkdir(parents=True, exist_ok=True)
        out, tmp = path_for(pid), DIR / f"{pid}.tmp.png"
        tmp.unlink(missing_ok=True)
        profile = DIR / "browser-profile"  # separate profile: never touches the user's own browser data
        subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
                          "--disable-extensions", f"--user-data-dir={profile}", "--window-size=1200,780",
                          "--virtual-time-budget=2500", f"--screenshot={tmp}", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.time() + timeout
        last = -1
        while time.time() < deadline:  # the browser writes the file a few seconds after it starts
            if tmp.exists():
                size = tmp.stat().st_size
                if size and size == last:
                    tmp.replace(out)
                    return out
                last = size
            time.sleep(0.4)
        return None


def get(pid: str, project_path: str, url: str) -> Path | None:
    if fresh(pid, project_path):
        return path_for(pid)
    made = render(pid, url)
    return made or (path_for(pid) if path_for(pid).exists() else None)
