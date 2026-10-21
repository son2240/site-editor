"""Read and write a site data file of the form `window.SITE = { ... };`.

Reading accepts a hand-written JS object literal (comments, unquoted keys,
single-quoted strings, trailing commas). Writing always produces strict JSON inside
the assignment, so the file stays valid JavaScript and stays easy to diff.
"""
from __future__ import annotations

import json
import re

ASSIGN_RE = re.compile(r"^\s*window\.(?P<name>[A-Za-z_$][\w$]*)\s*=\s*", re.M)  # at line start, not in a comment
HEADER = """// =====================================================================
//  Site content. Edit it with the site editor (projects/site_editor),
//  or by hand: it is plain JSON after `window.SITE =`.
//  Text is written as { "ko": "...", "en": "..." } for both languages.
//  Sections whose list is empty ([]) are hidden on the site.
// =====================================================================
"""


class DataError(ValueError):
    pass


def _to_json(src: str) -> str:
    """Convert a JS object literal to JSON text (subset: what a data file needs)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":  # string
            q, j, buf = c, i + 1, []
            while j < n and src[j] != q:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if src[j] == "\n":
                    raise DataError("unterminated string")
                buf.append(src[j])
                j += 1
            if j >= n:
                raise DataError("unterminated string")
            body = "".join(buf)
            if q == "'":
                body = body.replace("\\'", "'").replace('"', '\\"')
            out.append('"' + body + '"')
            i = j + 1
        elif src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                raise DataError("unterminated comment")
            i = end + 2
        elif c.isalpha() or c in "_$":  # bare word: key, true/false/null
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word = src[i:j]
            k = j
            while k < n and src[k] in " \t\r\n":
                k += 1
            if k < n and src[k] == ":" and word not in ("true", "false", "null"):
                out.append(json.dumps(word))
            elif word in ("true", "false", "null"):
                out.append(word)
            else:
                raise DataError(f"unsupported expression: {word}")
            i = j
        elif c == ",":  # drop trailing commas
            k = i + 1
            while k < n and src[k] in " \t\r\n":
                k += 1
            while src.startswith("//", k) or src.startswith("/*", k):
                if src.startswith("//", k):
                    k = src.find("\n", k)
                    k = n if k < 0 else k
                else:
                    k = src.find("*/", k) + 2
                while k < n and src[k] in " \t\r\n":
                    k += 1
            if k < n and src[k] in "]}":
                i += 1
                continue
            out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse(text: str) -> tuple[str, dict]:
    """(variable name, data) from the file text."""
    m = ASSIGN_RE.search(text)
    if not m:
        raise DataError("no `window.NAME = {...}` assignment found")
    body = text[m.end():].strip()
    if body.endswith(";"):
        body = body[:-1]
    try:
        data = json.loads(_to_json(body))
    except json.JSONDecodeError as e:
        raise DataError(f"cannot parse data: {e}") from None
    if not isinstance(data, dict):
        raise DataError("data must be an object")
    return m.group("name"), data


def dump(name: str, data: dict) -> str:
    return HEADER + f"window.{name} = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
