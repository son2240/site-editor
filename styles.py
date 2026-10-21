"""Design changes as real CSS rules in one file the tool owns: `site-editor.css`.

Visual edits (size, font, color, spacing, width...) are stored as rules
`selector { prop: value }`, optionally only for phones (`@media (max-width: 720px)`),
instead of inline style attributes. The site's own CSS files are never rewritten;
this file is linked last in <head>, so its rules win and can be removed at any time.

Units are kept relative where possible (rem for type and spacing, % for widths), so
layouts stay responsive. `warnings()` flags values that may break small screens.
"""
from __future__ import annotations

import re

FILE = "site-editor.css"
LINK = f'<link rel="stylesheet" href="{FILE}" data-site-editor>'
MOBILE_QUERY = "(max-width: 720px)"
HEADER = ("/* site-editor.css: written by the site editor (projects/site_editor).\n"
          "   Safe to edit by hand; delete this file and its <link> to undo all visual changes. */\n")
ALLOWED_PROPS = {
    "font-family", "font-size", "font-weight", "font-style", "line-height", "letter-spacing", "text-align",
    "text-decoration", "text-transform", "color", "background-color", "background",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "width", "max-width", "min-width", "height", "min-height", "max-height",
    "border-radius", "border", "border-width", "border-style", "border-color", "box-shadow", "opacity",
    "display", "gap", "justify-content", "align-items", "flex-direction", "order", "aspect-ratio", "object-fit",
}
FONT_IMPORTS = {
    "Noto Sans KR": "Noto+Sans+KR:wght@400;500;700",
    "Nanum Gothic": "Nanum+Gothic:wght@400;700",
    "Nanum Myeongjo": "Nanum+Myeongjo:wght@400;700",
    "Gowun Dodum": "Gowun+Dodum",
    "IBM Plex Sans KR": "IBM+Plex+Sans+KR:wght@400;500;700",
    "Inter": "Inter:wght@400;500;700",
    "Playfair Display": "Playfair+Display:wght@400;700",
}
SELECTOR_RE = re.compile(r"^[A-Za-z0-9#.\-_ >:()*\[\]=\"'+~,]+$")
VALUE_BAD = re.compile(r"[{};<>]|expression\(|url\(\s*['\"]?\s*javascript:", re.I)


class StyleError(ValueError):
    pass


def validate(rules: list[dict]) -> list[dict]:
    out = []
    for r in rules or []:
        sel, media = str(r.get("selector", "")).strip(), r.get("media", "")
        if not sel or len(sel) > 300 or not SELECTOR_RE.match(sel):
            raise StyleError(f"bad selector: {sel!r}")
        if media not in ("", "mobile"):
            raise StyleError(f"bad media: {media!r}")
        props = {}
        for k, v in (r.get("props") or {}).items():
            if k not in ALLOWED_PROPS:
                raise StyleError(f"property not allowed: {k}")
            v = str(v).strip()
            if not v:
                continue
            if VALUE_BAD.search(v) or len(v) > 200:
                raise StyleError(f"bad value for {k}")
            props[k] = v
        if props:
            out.append({"selector": sel, "media": media, "props": props})
    return out


def render(rules: list[dict]) -> str:
    rules = validate(rules)
    fonts = sorted({f.strip().strip("'\"") for r in rules for f in r["props"].get("font-family", "").split(",")}
                   & set(FONT_IMPORTS))
    parts = [HEADER]
    if fonts:
        fam = "&".join("family=" + FONT_IMPORTS[f] for f in fonts)
        parts.append(f"@import url(\"https://fonts.googleapis.com/css2?{fam}&display=swap\");\n")

    def block(rs, indent=""):
        s = ""
        for r in rs:
            body = "".join(f"{indent}  {k}: {v};\n" for k, v in r["props"].items())
            s += f"\n{indent}{r['selector']} {{\n{body}{indent}}}\n"
        return s

    parts.append(block([r for r in rules if not r["media"]]))
    mobile = [r for r in rules if r["media"] == "mobile"]
    if mobile:
        parts.append(f"\n@media {MOBILE_QUERY} {{" + block(mobile, "  ") + "}\n")
    return "".join(parts)


_RULE_RE = re.compile(r"([^{}@]+?)\{([^{}]*)\}", re.S)


def parse(css: str) -> list[dict]:
    """Read back a file written by render() (tolerates hand edits in the same shape)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@import\s+url\([^)]*\)[^;\n]*;|@import\s+[\"'][^\"']*[\"'][^;\n]*;", "", css)  # URLs may contain ';'
    rules = []

    def collect(chunk, media):
        for m in _RULE_RE.finditer(chunk):
            props = {}
            for decl in m.group(2).split(";"):
                if ":" in decl:
                    k, v = decl.split(":", 1)
                    if k.strip():
                        props[k.strip()] = v.strip()
            rules.append({"selector": " ".join(m.group(1).split()), "media": media, "props": props})

    mm = re.search(r"@media\s*\(max-width:\s*720px\)\s*\{(.*)\}\s*$", css, re.S)
    collect(css[:mm.start()] if mm else css, "")
    if mm:
        collect(mm.group(1), "mobile")
    return rules


def ensure_link(html: str) -> str:
    if "data-site-editor" in html or f'href="{FILE}"' in html:
        return html
    i = html.lower().rfind("</head>")
    if i < 0:
        return LINK + "\n" + html
    return html[:i] + "  " + LINK + "\n" + html[i:]


def warnings(rules: list[dict]) -> list[str]:
    out = []
    for r in rules:
        for k, v in r["props"].items():
            m = re.match(r"^(-?\d+(?:\.\d+)?)px$", v)
            if k in ("width", "min-width") and m and float(m.group(1)) > 360:
                out.append(f"{r['selector']}: {k} {v} is wider than a phone screen; prefer % or max-width")
            if k in ("height", "max-height") and m:
                out.append(f"{r['selector']}: fixed {k} {v} can cut off text; prefer min-height")
            if k in ("margin-left", "margin-right") and m and abs(float(m.group(1))) > 200:
                out.append(f"{r['selector']}: large {k} {v} may push content off small screens")
            if k == "font-size" and m and float(m.group(1)) > 72:
                out.append(f"{r['selector']}: very large font-size {v}")
    return out
