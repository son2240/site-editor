"""Where server passwords live: the OS credential store, never the repository.

Order of preference:
  1. `keyring` (Windows Credential Manager, macOS Keychain, Secret Service on Linux)
  2. a JSON file only the current user can read: ~/.site-editor/secrets.json
     (used only if keyring is missing; reported to the UI as "file")

Values are written by the user in the editor screen and read only at deploy time.
They are never returned to the browser, printed or logged.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

SERVICE = "site-editor"
HOME = Path(os.environ.get("SITE_EDITOR_HOME") or Path.home() / ".site-editor")

try:
    import keyring  # type: ignore
    from keyring.errors import PasswordDeleteError  # type: ignore
except Exception:  # noqa: BLE001 - optional dependency
    keyring = None


def backend() -> str:
    if keyring is not None and os.environ.get("SITE_EDITOR_NO_KEYRING") != "1":
        try:
            name = type(keyring.get_keyring()).__name__
            if "fail" not in name.lower() and "null" not in name.lower():
                return "keyring"
        except Exception:  # noqa: BLE001
            pass
    return "file"


def _file() -> Path:
    return HOME / "secrets.json"


def _read_file() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_file(d: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    p = _file()
    p.write_text(json.dumps(d), encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600 (on Windows the profile folder is already per-user)
    except OSError:
        pass


def set_secret(key: str, value: str) -> str:
    if backend() == "keyring":
        keyring.set_password(SERVICE, key, value)
        return "keyring"
    d = _read_file()
    d[key] = value
    _write_file(d)
    return "file"


def get_secret(key: str) -> str | None:
    if backend() == "keyring":
        return keyring.get_password(SERVICE, key)
    return _read_file().get(key)


def has_secret(key: str) -> bool:
    return bool(get_secret(key))


def delete_secret(key: str) -> None:
    if backend() == "keyring":
        try:
            keyring.delete_password(SERVICE, key)
        except PasswordDeleteError:
            pass
        return
    d = _read_file()
    d.pop(key, None)
    _write_file(d)
