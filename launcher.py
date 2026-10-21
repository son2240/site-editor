"""Open the site editor with one double-click.

    pythonw launcher.py              open (start the server if needed, focus the window if open)
    pythonw launcher.py --background start the server quietly, no window (Windows startup)
    python  launcher.py --install    desktop + Start menu shortcuts
    python  launcher.py --uninstall  remove the shortcuts (and the startup entry)

The server runs once per user. Its port and the random access token are kept in
~/.site-editor/session.json, which only this user can read, so the launcher can open
the window without asking for anything.
"""
from __future__ import annotations

import ctypes
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import credstore  # noqa: E402

APP_NAME = "사이트 편집기"
PORT = int(os.environ.get("SITE_EDITOR_PORT") or 8770)
SESSION = credstore.HOME / "session.json"


# -- session -------------------------------------------------------------------
def read_session() -> dict | None:
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_session(port: int, token: str) -> None:
    credstore.HOME.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    try:
        os.chmod(SESSION, 0o600)
    except OSError:
        pass


def new_token() -> str:
    return secrets.token_urlsafe(18)


def ping(port: int = PORT, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=timeout) as r:
            return json.loads(r.read()).get("app") == "site-editor"
    except (OSError, ValueError):
        return False


def url(path: str = "/") -> str | None:
    s = read_session()
    if not s:
        return None
    return f"http://127.0.0.1:{s['port']}{path}?t={s['token']}"


# -- windows -------------------------------------------------------------------
def focus_existing_window() -> bool:
    """Bring an open editor window to the front (Windows). Returns True if one was found."""
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith(APP_NAME):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(cb, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets SetForegroundWindow work from a background process
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return True


def _app_browser() -> str | None:
    """A Chromium browser that can open a page as an app window (no tabs, no address bar)."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        shutil.which("msedge") or "", shutil.which("google-chrome") or "", shutil.which("chromium") or "",
    ]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def open_window(target: str) -> None:
    exe = _app_browser()
    if exe:
        subprocess.Popen([exe, f"--app={target}", "--window-size=1440,900"], close_fds=True)
    else:
        webbrowser.open(target)


# -- server --------------------------------------------------------------------
def _pythonw() -> str:
    w = Path(sys.executable).with_name("pythonw.exe")
    return str(w) if w.exists() else sys.executable


def start_server() -> None:
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log = credstore.HOME / "server.log"
    credstore.HOME.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen([_pythonw(), str(HERE / "editor.py"), "--app", "--no-browser", "--port", str(PORT)],
                         stdout=out, stderr=out, stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
                         cwd=str(HERE))
    for _ in range(60):
        if ping():
            return
        time.sleep(0.25)
    raise SystemExit(f"the editor did not start; see {log}")


def ensure_server() -> None:
    if not ping():
        start_server()


def open_app() -> None:
    if ping() and focus_existing_window():
        return
    ensure_server()
    target = url("/")
    if target:
        open_window(target)


# -- shortcuts -------------------------------------------------------------------
def _shell_folder(name: str) -> Path:
    """Desktop / Programs / Startup folder of the current user (handles OneDrive desktops)."""
    ps = f"[Environment]::GetFolderPath('{name}')"
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    if not out:
        raise SystemExit(f"cannot find the {name} folder")
    return Path(out)


def make_shortcut(lnk: Path, args: str = "", minimized: bool = False) -> None:
    icon = HERE / "static" / "app.ico"
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SE_LNK);"
        "$s.TargetPath = $env:SE_TARGET; $s.Arguments = $env:SE_ARGS; $s.WorkingDirectory = $env:SE_DIR;"
        "$s.Description = $env:SE_DESC; if ($env:SE_ICON) { $s.IconLocation = $env:SE_ICON };"
        "if ($env:SE_MIN -eq '1') { $s.WindowStyle = 7 }; $s.Save()"
    )
    env = dict(os.environ, SE_LNK=str(lnk), SE_TARGET=_pythonw(), SE_ARGS=f'"{HERE / "launcher.py"}" {args}'.strip(),
               SE_DIR=str(HERE), SE_DESC="HTML 사이트를 편집하고 배포합니다", SE_ICON=str(icon) if icon.exists() else "",
               SE_MIN="1" if minimized else "0")
    lnk.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, check=True, capture_output=True)


def shortcut_paths() -> dict[str, Path]:
    return {"desktop": _shell_folder("Desktop") / f"{APP_NAME}.lnk",
            "start_menu": _shell_folder("Programs") / f"{APP_NAME}.lnk",
            "startup": _shell_folder("Startup") / f"{APP_NAME} (대기).lnk"}


def install() -> dict:
    paths = shortcut_paths()
    make_shortcut(paths["desktop"])
    make_shortcut(paths["start_menu"])
    return {k: str(v) for k, v in paths.items() if k != "startup"}


def set_startup(enabled: bool) -> bool:
    """Optional: start the server quietly when this user signs in to Windows."""
    lnk = shortcut_paths()["startup"]
    if enabled:
        make_shortcut(lnk, "--background", minimized=True)
    elif lnk.exists():
        lnk.unlink()
    return lnk.exists()


def startup_enabled() -> bool:
    try:
        return shortcut_paths()["startup"].exists()
    except SystemExit:
        return False


def uninstall() -> None:
    for p in shortcut_paths().values():
        if p.exists():
            p.unlink()


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--install" in args:
        done = install()
        print("바로가기를 만들었습니다:\n  " + "\n  ".join(done.values()))
        return 0
    if "--uninstall" in args:
        uninstall()
        print("바로가기를 지웠습니다.")
        return 0
    if "--background" in args:
        ensure_server()
        return 0
    open_app()
    return 0


if __name__ == "__main__":
    sys.exit(main())
