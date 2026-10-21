"""Import a live website by URL into an editable project ("링크로 가져오기").

What it does:
  1. Crawl pages of the same site (same host), breadth first, up to `max_pages`.
  2. Download every same-site asset they use: CSS, JS, images (src/srcset), video/audio,
     fonts and images referenced from CSS (url(), @import), favicons.
  3. Save them under matching paths ("/about/" -> about/index.html, "/a/b.css" -> a/b.css)
     and rewrite same-site links in HTML and CSS to relative paths, so the copy works when
     opened locally and after deploying it anywhere. Links to other sites (CDNs, fonts,
     social links) are left untouched; same-site pages beyond the limit keep their full URL.
  4. Optional "rendered" mode for sites drawn by JavaScript: each page is opened in a
     headless browser (cdp.py) and the finished DOM is saved, with <script> tags removed
     so the content is not drawn twice and becomes directly editable.

Only for sites you own or have the right to copy.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import posixpath
import re
import time
import urllib.error
import urllib.request
from collections import deque
from html.parser import HTMLParser
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import projects

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SiteEditor-Import/1.0"
MAX_FILE = 25 * 1024 * 1024
MAX_TOTAL = 150 * 1024 * 1024
MAX_ASSETS = 800
PAGE_EXT = {"", ".html", ".htm", ".php", ".asp", ".aspx", ".jsp", ".cfm", ".shtml"}
FILE_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".webm", ".mp3", ".zip", ".docx", ".pptx",
            ".xlsx", ".txt", ".csv", ".json"}
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "#", "sms:", "blob:")
URL_ATTRS = ("href", "src", "poster", "data-src", "data-background", "action")
WIN_BAD = re.compile(r'[<>:"\\|?*\x00-\x1f]')


class ImportError_(RuntimeError):
    pass


def normalize(url: str) -> str:
    url = url.strip()
    m = re.match(r"^([a-z][a-z0-9+.-]*):(?!\d)", url, re.I)  # a scheme (but not "host:8080")
    if m and m.group(1).lower() not in ("http", "https"):
        raise ImportError_("http:// 또는 https:// 주소를 입력하세요")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ImportError_("http:// 또는 https:// 주소를 입력하세요")
    return urldefrag(url)[0]


def fetch(url: str, timeout: float = 20) -> tuple[str, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ImportError_(f"파일이 너무 큽니다: {url}")
            return r.geturl(), (r.headers.get("Content-Type") or "").lower(), data
    except urllib.error.HTTPError as e:
        raise ImportError_(f"HTTP {e.code}: {url}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ImportError_(f"접속할 수 없습니다: {url} ({getattr(e, 'reason', e)})") from None


def decode(data: bytes, ctype: str) -> str:
    m = re.search(r"charset=([\w-]+)", ctype)
    enc = m.group(1) if m else None
    if not enc:
        head = data[:2048].decode("ascii", "ignore")
        m = re.search(r"<meta[^>]+charset=[\"']?([\w-]+)", head, re.I)
        enc = m.group(1) if m else "utf-8"
    try:
        return data.decode(enc, "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


def is_html(ctype: str, data: bytes) -> bool:
    return "html" in ctype or (not ctype and data.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")))


def local_path(url: str, html: bool) -> str:
    u = urlparse(url)
    path = unquote(u.path) or "/"
    if path.endswith("/"):
        path += "index.html"
    elif html and posixpath.splitext(path)[1].lower() not in (".html", ".htm"):
        path += "/index.html"  # "/about" -> about/index.html, so "/about" links keep working on static hosts
    parts = [WIN_BAD.sub("_", p).strip(" .") or "_" for p in path.strip("/").split("/") if p not in ("", ".", "..")]
    rel = "/".join(parts) or "index.html"
    if u.query:  # style.css?v=3 -> style-<hash>.css (keeps versions apart, valid file name)
        stem, ext = posixpath.splitext(rel)
        rel = f"{stem}-{hashlib.sha1(u.query.encode()).hexdigest()[:6]}{ext}"
    return rel


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages, self.assets, self.styles = [], [], []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "style":
            self._in_style = True
        for k in URL_ATTRS:
            v = a.get(k, "").strip()
            if not v:
                continue
            if tag == "a" and k == "href" or tag == "form" and k == "action":
                self.pages.append(v)
            elif tag == "link" and k == "href":
                rel = a.get("rel", "").lower()
                if any(x in rel for x in ("stylesheet", "icon", "preload", "manifest", "apple-touch")):
                    self.assets.append(v)
                elif "alternate" not in rel and "canonical" not in rel:
                    self.assets.append(v)
            elif k in ("src", "poster", "data-src", "data-background") or tag in ("iframe",):
                (self.pages if tag == "iframe" else self.assets).append(v)
        for k in ("srcset", "data-srcset"):
            for cand in (a.get(k) or "").split(","):
                part = cand.strip().split(" ")[0]
                if part:
                    self.assets.append(part)
        if a.get("style"):
            self.styles.append(a["style"])
        if tag == "meta" and a.get("property", "").lower() in ("og:image",) and a.get("content"):
            self.assets.append(a["content"])

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)


CSS_URL = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\s+(['\"])([^'\"]+)\1", re.I)


def css_refs(css: str) -> list[str]:
    return [m.group(2).strip() for m in CSS_URL.finditer(css)] + [m.group(2).strip() for m in CSS_IMPORT.finditer(css)]


class Site:
    def __init__(self, start: str, max_pages: int, rendered: bool, log):
        self.start = start
        self.host = urlparse(start).netloc.lower()
        self.max_pages, self.rendered, self.log = max_pages, rendered, log
        self.files: dict[str, tuple[str, bytes]] = {}    # local rel -> (url, data)
        self.url_to_local: dict[str, str] = {}          # absolute url (no fragment) -> local rel
        self.page_kind: dict[str, bool] = {}            # local rel -> is html
        self.total = 0
        self.browser = None

    def same_site(self, url: str) -> bool:
        u = urlparse(url)
        return u.scheme in ("http", "https") and u.netloc.lower() == self.host

    def resolve(self, ref: str, base: str) -> str | None:
        ref = ref.strip()
        if not ref or ref.lower().startswith(SKIP_SCHEMES):
            return None
        return urldefrag(urljoin(base, ref))[0]

    def _store(self, url: str, final: str, data: bytes, html: bool) -> str:
        self.total += len(data)
        if self.total > MAX_TOTAL:
            raise ImportError_("가져올 내용이 150MB를 넘습니다. 페이지 수를 줄여 보세요")
        rel = local_path(final, html)
        if rel in self.files and self.files[rel][0] != final:  # two URLs -> same name
            stem, ext = posixpath.splitext(rel)
            rel = f"{stem}-{hashlib.sha1(final.encode()).hexdigest()[:6]}{ext}"
        self.files[rel] = (final, data)
        self.page_kind[rel] = html
        self.url_to_local[url] = self.url_to_local[final] = rel
        return rel

    def get_page(self, url: str) -> tuple[str, str, bytes] | None:
        if self.rendered:
            from cdp import Browser
            if self.browser is None:
                self.browser = Browser()
            r = self.browser.render(url)
            html = re.sub(r"<script\b(?![^>]*application/ld\+json)[^>]*>.*?</script\s*>", "", r["html"], flags=re.S | re.I)
            for res in r.get("resources") or []:
                if self.same_site(res):
                    self._asset_queue.append((res, url))
            return r["url"], "text/html; charset=utf-8", html.encode("utf-8")
        final, ctype, data = fetch(url)
        if not is_html(ctype, data):
            return None
        return final, ctype, data

    def crawl(self) -> None:
        self._asset_queue: deque = deque()
        queue, seen = deque([self.start]), {self.start}
        pages_done = 0
        try:
            while queue and pages_done < self.max_pages:
                url = queue.popleft()
                try:
                    got = self.get_page(url)
                except ImportError_ as e:
                    self.log(f"건너뜀 {e}")
                    continue
                if got is None:  # a link that turned out to be a file: treat it as an asset
                    self._asset_queue.append((url, url))
                    continue
                final, ctype, data = got
                if not self.same_site(final):
                    self.log(f"다른 사이트로 이동해서 건너뜀: {final}")
                    continue
                rel = self._store(url, final, data, True)
                pages_done += 1
                self.log(f"페이지 {pages_done}: {final} -> {rel}")
                text = decode(data, ctype)
                p = _Refs()
                p.feed(text)
                for ref in p.pages:
                    u = self.resolve(ref, final)
                    if not u or not self.same_site(u) or u in seen:
                        continue
                    seen.add(u)
                    ext = posixpath.splitext(urlparse(u).path)[1].lower()
                    if ext in PAGE_EXT:
                        queue.append(u)
                    elif ext in FILE_EXT:  # linked documents and images: copy them too
                        self._asset_queue.append((u, final))
                for ref in p.assets + [r for s in p.styles for r in css_refs(s)]:
                    u = self.resolve(ref, final)
                    if u and self.same_site(u):
                        self._asset_queue.append((u, final))
                time.sleep(0.05)
            self.fetch_assets()
        finally:
            if self.browser:
                self.browser.close()
        if not any(self.page_kind.values()):
            raise ImportError_("이 주소에서 HTML 페이지를 받지 못했습니다")

    def fetch_assets(self) -> None:
        done, count = set(self.url_to_local), 0
        while self._asset_queue and count < MAX_ASSETS:
            url, _ = self._asset_queue.popleft()
            if url in done:
                continue
            done.add(url)
            try:
                final, ctype, data = fetch(url)
            except ImportError_ as e:
                self.log(f"건너뜀 {e}")
                continue
            if not self.same_site(final):
                continue
            rel = self._store(url, final, data, False)
            count += 1
            if "css" in ctype or rel.endswith(".css"):
                for ref in css_refs(decode(data, ctype)):
                    u = self.resolve(ref, final)
                    if u and self.same_site(u) and u not in done:
                        self._asset_queue.append((u, final))
        self.log(f"자원 {count}개 (CSS · JS · 이미지 · 폰트)")

    # -- rewriting ---------------------------------------------------------
    def _rel_link(self, target_abs: str, frag: str, from_rel: str) -> str | None:
        local = self.url_to_local.get(target_abs)
        if local is None:
            return None
        link = posixpath.relpath(local, posixpath.dirname(from_rel) or ".")
        return link + (("#" + frag) if frag else "")

    def _map(self, value: str, base: str, from_rel: str) -> str:
        v = htmllib.unescape(value.strip())  # attribute text may carry &amp; etc.
        if not v or v.lower().startswith(SKIP_SCHEMES):
            return value
        absu = urljoin(base, v)
        target, frag = urldefrag(absu)
        if not self.same_site(target):
            return value  # other sites: untouched
        mapped = self._rel_link(target, frag, from_rel)
        return mapped if mapped is not None else absu  # same site but not downloaded: keep it working online

    def rewrite_css(self, css: str, base: str, from_rel: str) -> str:
        css = CSS_URL.sub(lambda m: f"url({m.group(1)}{self._map(m.group(2), base, from_rel)}{m.group(1)})", css)
        return CSS_IMPORT.sub(lambda m: f"@import {m.group(1)}{self._map(m.group(2), base, from_rel)}{m.group(1)}", css)

    def rewrite_html(self, html: str, base: str, from_rel: str) -> str:
        bm = re.search(r"<base\s[^>]*href=([\"'])(.*?)\1[^>]*>", html, re.I)
        if bm:  # links are made relative below, so <base> would break them
            base = urljoin(base, bm.group(2))
            html = html[:bm.start()] + html[bm.end():]

        def attr_sub(m):
            name, q, val = m.group(1), m.group(2), m.group(3)
            if name.lower() in ("srcset", "data-srcset"):
                new = ", ".join(" ".join([self._map(c.strip().split(" ")[0], base, from_rel)] + c.strip().split(" ")[1:])
                                for c in val.split(",") if c.strip())
            elif name.lower() == "style":
                new = self.rewrite_css(val, base, from_rel)
            else:
                new = self._map(val, base, from_rel)
            return f"{m.group(0)[:m.start(3) - m.start(0)]}{new}{q}"

        attr_re = re.compile(r"\b(href|src|poster|data-src|data-background|action|srcset|data-srcset|style)\s*=\s*([\"'])(.*?)\2",
                             re.I | re.S)

        def tag_sub(m):
            tag = m.group(0)
            new = attr_re.sub(attr_sub, tag)
            if new != tag:  # rewritten resources no longer match a Subresource-Integrity hash
                new = re.sub(r"\s+integrity\s*=\s*([\"']).*?\1", "", new, flags=re.I | re.S)
            if re.match(r"<meta\b", tag, re.I) and re.search(r"og:image", tag, re.I):
                new = re.sub(r"(\bcontent\s*=\s*)([\"'])(.*?)\2",
                             lambda mm: mm.group(1) + mm.group(2) + self._map(mm.group(3), base, from_rel) + mm.group(2), new)
            return new

        html = re.sub(r"<[a-zA-Z][^<>]*>", tag_sub, html)
        return re.sub(r"(<style\b[^>]*>)(.*?)(</style>)", lambda m: m.group(1) + self.rewrite_css(m.group(2), base, from_rel) + m.group(3),
                      html, flags=re.S | re.I)

    def write(self, name: str) -> dict:
        up = projects.start_upload(name)
        try:
            for rel, (url, data) in self.files.items():
                if self.page_kind[rel]:
                    ctype = "text/html; charset=utf-8" if self.rendered else ""
                    text = decode(data, ctype)
                    data = self.rewrite_html(text, url, rel).encode("utf-8")
                elif rel.endswith(".css"):
                    data = self.rewrite_css(decode(data, ""), url, rel).encode("utf-8")
                projects.upload_file(up["upload"], rel, data)
            p = projects.finish_upload(up["upload"])
        except Exception:
            import shutil
            shutil.rmtree(up["folder"], ignore_errors=True)
            raise
        return projects.set_meta(p["id"], source_url=self.start, imported=time.time())


def import_site(url: str, name: str | None = None, max_pages: int = 20, rendered: bool = False, log=print) -> dict:
    start = normalize(url)
    site = Site(start, max(1, min(int(max_pages), 200)), rendered, log)
    log(f"가져오기 시작: {start}" + (" (화면 그대로)" if rendered else ""))
    site.crawl()
    pages = sum(site.page_kind.values())
    log(f"저장 중: 페이지 {pages}개, 파일 {len(site.files)}개, {site.total // 1024} KB")
    p = site.write(name or urlparse(start).netloc)
    log("완료")
    return p
