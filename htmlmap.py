"""Map elements of an HTML file to exact byte ranges of its source.

The visual editor works on the live page, but it must change the *source* without
reformatting it. This module numbers every element inside <body> in document order
(`data-se-id`), remembers where each element's start tag, inner content and end tag
are in the original text, and applies edits by splicing only those ranges. Everything
else in the file stays byte-for-byte identical.

Edits supported:
  inner   replace an element's inner HTML (text edited in place)
  move    move an element before/after a sibling (block reordering)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
RAW = {"script", "style", "textarea", "title"}
_BLOCKS = {"address", "article", "aside", "blockquote", "div", "dl", "fieldset", "footer", "form", "h1", "h2", "h3",
           "h4", "h5", "h6", "header", "hr", "main", "nav", "ol", "p", "pre", "section", "table", "ul", "figure"}
CLOSED_BY = {"li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "p": _BLOCKS, "tr": {"tr"},
             "td": {"td", "th", "tr"}, "th": {"td", "th", "tr"}, "option": {"option", "optgroup"}}


@dataclass
class Node:
    id: int
    tag: str
    start: int            # offset of "<tag"
    start_end: int        # offset just after ">" of the start tag
    end_start: int = -1   # offset of "</tag" (or start_end for void elements)
    end: int = -1         # offset just after the end tag
    parent: int | None = None
    children: list[int] = field(default_factory=list)

    @property
    def closed(self) -> bool:
        return self.end >= 0


class _Mapper(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_offsets = [0]
        for m in re.finditer("\n", text):
            self.line_offsets.append(m.end())
        self.nodes: list[Node] = []
        self.stack: list[int] = []
        self.in_body = False

    def _pos(self) -> int:
        line, col = self.getpos()
        return self.line_offsets[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self._pos()
        raw = self.get_starttag_text() or ""
        if tag == "body":
            self.in_body = True
            return
        if not self.in_body:
            return
        # implied end tags (<li>a<li>b, <p>x<div>): the open element ends where this one starts
        while self.stack and tag in CLOSED_BY.get(self.nodes[self.stack[-1]].tag, ()):
            m = self.nodes[self.stack.pop()]
            m.end_start = m.end = start
        n = Node(id=len(self.nodes), tag=tag, start=start, start_end=start + len(raw),
                 parent=self.stack[-1] if self.stack else None)
        if n.parent is not None:
            self.nodes[n.parent].children.append(n.id)
        self.nodes.append(n)
        if tag in VOID or raw.endswith("/>"):
            n.end_start = n.end = n.start_end
        else:
            self.stack.append(n.id)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "body":
            self.in_body = False
            return
        pos = self._pos()
        # close up to the matching open element (tolerates missing end tags like </p>)
        for i in range(len(self.stack) - 1, -1, -1):
            n = self.nodes[self.stack[i]]
            if n.tag == tag:
                end = self.text.find(">", pos) + 1
                for j in self.stack[i + 1:]:  # implicitly closed children end where this one starts
                    m = self.nodes[j]
                    m.end_start = m.end = pos
                n.end_start, n.end = pos, end
                del self.stack[i:]
                return


def parse(text: str) -> list[Node]:
    m = _Mapper(text)
    m.feed(text)
    m.close()
    for i in m.stack:  # unclosed at EOF
        n = m.nodes[i]
        n.end_start = n.end = len(text)
    return m.nodes


def instrument(text: str) -> str:
    """Add data-se-id="N" to every body element's start tag (preview only, never saved)."""
    nodes = parse(text)
    out, last = [], 0
    for n in nodes:
        tag_end = n.start + 1 + len(n.tag)
        out.append(text[last:tag_end])
        out.append(f' data-se-id="{n.id}"')
        last = tag_end
    out.append(text[last:])
    return "".join(out)


def inject_head(text: str, snippet: str) -> str:
    """Insert `snippet` right before </head> (or at the start if there is no head)."""
    i = text.lower().rfind("</head>")
    return text[:i] + snippet + text[i:] if i >= 0 else snippet + text


ID_ATTR_RE = re.compile(r' data-se-id="(\d+)"')


class EditError(ValueError):
    pass


def strip_ids(text: str) -> str:
    """Remove exactly the attributes instrument() added."""
    return ID_ATTR_RE.sub("", text)


def _by_id(text: str) -> dict[int, Node]:
    out = {}
    for n in parse(text):
        m = ID_ATTR_RE.search(text, n.start, n.start_end)
        if m:
            out[int(m.group(1))] = n
    return out


def apply_instrumented(inst: str, edits: list[dict]) -> str:
    """Apply edits one after another on instrumented text, finding elements by their
    data-se-id each time. Ids survive moves and inner edits, so later edits can address
    elements an earlier edit moved."""
    for e in edits:
        nodes = _by_id(inst)
        n = nodes.get(e.get("id"))
        if n is None:
            raise EditError(f"no element {e.get('id')}")
        if e["op"] == "inner":
            if n.tag in VOID or n.tag in RAW:
                raise EditError(f"<{n.tag}> has no editable content")
            html = str(e["html"])
            if re.search(r"<\s*(script|style|iframe|object|embed)\b|\son\w+\s*=|javascript:", html, re.I):
                raise EditError("scripts and event handlers are not allowed in edited text")
            inst = inst[:n.start_end] + html + inst[n.end_start:]
        elif e["op"] == "move":
            t = nodes.get(e.get("target"))
            if t is None or n.parent != t.parent or n is t:
                raise EditError("elements can only move among their siblings")
            # carry the element's own line break + indentation along, so the file stays tidy
            a, ta = _line_start(inst, n.start), _line_start(inst, t.start)
            chunk = inst[a:n.end]
            at = ta if e.get("where", "before") == "before" else t.end
            if a == n.start or ta == t.start:  # inline elements: move just the element
                a, chunk = n.start, inst[n.start:n.end]
                at = t.start if e.get("where", "before") == "before" else t.end
            if a < at:
                inst = inst[:a] + inst[n.end:at] + chunk + inst[at:]
            else:
                inst = inst[:at] + chunk + inst[at:a] + inst[n.end:]
        else:
            raise EditError(f"unknown op {e['op']}")
    return inst


def apply(text: str, edits: list[dict]) -> str:
    """Saved file after edits (ids refer to instrument(text))."""
    return strip_ids(apply_instrumented(instrument(text), edits)) if edits else text


def _line_start(text: str, pos: int) -> int:
    """Start of the whitespace run (including one preceding newline) before `pos`,
    or `pos` itself if the element does not start its own line."""
    i = pos
    while i > 0 and text[i - 1] in " \t":
        i -= 1
    return i - 1 if i > 0 and text[i - 1] == "\n" else pos
