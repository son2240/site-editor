"""Tiny Chrome DevTools Protocol client (stdlib only) for a headless Edge/Chrome.

Used to import sites whose pages are drawn by JavaScript: the page is opened in a
headless browser with its own temporary profile, and we read the finished DOM and the
list of resources it loaded. The browser listens on 127.0.0.1 only and is closed after.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from urllib.parse import urlparse

import launcher


class CDPError(RuntimeError):
    pass


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class WebSocket:
    """Just enough RFC 6455 for CDP: text frames, client masking, ping/pong."""

    def __init__(self, url: str, timeout: float = 30):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("websocket handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise CDPError("websocket handshake refused")
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def send(self, text: str) -> None:
        data = text.encode()
        mask = os.urandom(4)
        n = len(data)
        hdr = bytes([0x81])
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CDPError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> str:
        parts = []
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 0x9:  # ping
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if op == 0x8:
                raise CDPError("websocket closed by browser")
            parts.append(payload)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    def __init__(self):
        exe = launcher._app_browser()
        if not exe:
            raise CDPError("Edge 나 Chrome 이 없어 스크립트로 그려지는 페이지는 가져올 수 없습니다")
        self.port = _free_port()
        self.profile = tempfile.mkdtemp(prefix="site-editor-cdp-")
        self.proc = subprocess.Popen(
            [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions", "--mute-audio",
             f"--remote-debugging-port={self.port}", "--remote-debugging-address=127.0.0.1",
             f"--user-data-dir={self.profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        info = None
        for _ in range(80):
            try:
                info = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=1).read())
                break
            except (OSError, ValueError):
                time.sleep(0.25)
        if not info:
            self.close()
            raise CDPError("headless browser did not start")
        self.ws = WebSocket(info["webSocketDebuggerUrl"])
        self.seq = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None, session: str | None = None, timeout: float = 30) -> dict:
        self.seq += 1
        msg = {"id": self.seq, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.seq:
                if "error" in m:
                    raise CDPError(f"{method}: {m['error'].get('message')}")
                return m.get("result", {})
            self.events.append(m)
        raise CDPError(f"{method}: timed out")

    def render(self, url: str, settle: float = 1.5, timeout: float = 30) -> dict:
        """Open `url`, wait for load + `settle` seconds, return {html, url, resources}."""
        tid = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        sid = self.call("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        try:
            self.call("Page.enable", session=sid)
            self.call("Page.navigate", {"url": url}, session=sid)
            deadline = time.time() + timeout
            while time.time() < deadline:
                r = self.call("Runtime.evaluate", {"expression": "document.readyState", "returnByValue": True}, session=sid)
                if r.get("result", {}).get("value") == "complete":
                    break
                time.sleep(0.3)
            time.sleep(settle)  # let scripts finish drawing
            js = ("JSON.stringify({html: '<!doctype html>\\n' + document.documentElement.outerHTML, url: location.href,"
                  " resources: performance.getEntriesByType('resource').map(e => e.name)})")
            r = self.call("Runtime.evaluate", {"expression": js, "returnByValue": True}, session=sid)
            return json.loads(r["result"]["value"])
        finally:
            try:
                self.call("Target.closeTarget", {"targetId": tid}, timeout=5)
            except CDPError:
                pass

    def close(self) -> None:
        try:
            if getattr(self, "ws", None):
                try:
                    self.call("Browser.close", timeout=5)
                except (CDPError, OSError):
                    pass
                self.ws.close()
        finally:
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()  # only the browser this module started
            shutil.rmtree(self.profile, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
