"""List Korean interface strings that have no English translation in static/i18n.js.

    python tests/i18n_check.py        (also used by test_i18n.py)
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
H = re.compile(r"[가-힣]")


def load_dict():
    src = (HERE / "static" / "i18n.js").read_text(encoding="utf-8")
    keys = set()
    for m in re.finditer(r'^\s*"((?:[^"\\]|\\.)*)":\s*\[', src, re.M):
        keys.add(m.group(1))  # compare as written in the source (escapes included)
    for m in re.finditer(r'(?:,|\{)\s*"((?:[^"\\]|\\.)*)":\s*\[', src):
        keys.add(m.group(1))  # compare as written in the source (escapes included)
    pats = []
    for m in re.finditer(r"\[/(\^.*?\$)/,", src):
        try:
            pats.append(re.compile(m.group(1).replace("\\/", "/")))
        except re.error:
            pass
    return keys, pats


class _Markup(HTMLParser):
    def __init__(self, out):
        super().__init__()
        self.out, self.skip = out, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        for k, v in attrs:
            if k in ("title", "placeholder", "aria-label") and v and H.search(v):
                self.out.append(v.strip())

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip and H.search(d):
            self.out.append(d.strip())


def strings() -> list[str]:
    out: list[str] = []
    for name in ("editor.html", "home.html"):
        s = (HERE / "static" / name).read_text(encoding="utf-8")
        _Markup(out).feed(s)
        for js in re.findall(r"<script>(.*?)</script>", s, re.S):
            out += [m.group(1) for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', js) if H.search(m.group(1))]
    b = (HERE / "static" / "bridge.js").read_text(encoding="utf-8")
    out += [m.group(1) for m in re.finditer(r'(?<![=\w])"((?:[^"\\\n]|\\.)*)"', b) if H.search(m.group(1)) and "<" not in m.group(1)]
    out += [m.group(1).strip() for m in re.finditer(r">([^<>]*[가-힣][^<>]*)<", b) if "{" not in m.group(1)]
    out += re.findall(r'title="([^"]*[가-힣][^"]*)"', b)
    return [x for x in dict.fromkeys(out) if x and "__SITE__" not in x]


# pieces that are always joined with other text first; the joined text is what gets translated
FRAGMENTS = {"바깥 여백", "안쪽 여백", "개", " 추가", " · 비어 있으면 숨김", "사이트 편집기 · ", " 사본", " 중…", "분 전", "시간 전"}


def missing() -> list[str]:
    keys, pats = load_dict()
    bad = []
    for s in strings():
        if s in FRAGMENTS:
            continue
        cands = {s, s.strip()}
        if s.endswith((": ", ":", " ")) or s.startswith((" ", "(")):  # a fragment joined with a value at run time
            cands |= {s + "x", s + "1", "x" + s, s.strip() + " x"}
        if any(c in keys for c in cands) or any(p.match(c) for p in pats for c in cands):
            continue
        bad.append(s)
    return bad


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    m = missing()
    print(f"{len(m)} untranslated")
    for s in m:
        print(" ", repr(s))
