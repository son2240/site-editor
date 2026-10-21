"""Visual editing back end: HTML source mapping, CSS rules, unified save, design preview route."""
import tempfile
import unittest
from pathlib import Path

import _env  # noqa: F401
import editor
import htmlmap
import styles

PAGE = """<!doctype html>
<html><head>
  <meta charset="utf-8"><title>Demo</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header id="top"><h1 class="title">Hello <em>world</em></h1></header>
  <main>
    <section id="a"><p>First</p></section>
    <section id="b"><p>Second</p></section>
  </main>
  <script>var x = "<p>not an element</p>";</script>
</body></html>
"""


def ids(text):
    return {text[n.start:n.start_end]: n.id for n in htmlmap.parse(text)}


class HtmlMap(unittest.TestCase):
    def test_instrument_round_trip_is_exact(self):
        inst = htmlmap.instrument(PAGE)
        self.assertIn('data-se-id="0"', inst)
        self.assertEqual(htmlmap.strip_ids(inst), PAGE)

    def test_script_content_is_not_parsed_as_elements(self):
        tags = [n.tag for n in htmlmap.parse(PAGE)]
        self.assertEqual(tags.count("p"), 2)

    def test_inner_edit_touches_only_that_element(self):
        h1 = next(n for n in htmlmap.parse(PAGE) if n.tag == "h1")
        out = htmlmap.apply(PAGE, [{"op": "inner", "id": h1.id, "html": 'Hi <span style="font-size:2rem">there</span>'}])
        self.assertEqual(out, PAGE.replace("Hello <em>world</em>", 'Hi <span style="font-size:2rem">there</span>'))

    def test_move_keeps_lines_tidy(self):
        nodes = htmlmap.parse(PAGE)
        a = next(n for n in nodes if 'id="a"' in PAGE[n.start:n.start_end])
        b = next(n for n in nodes if 'id="b"' in PAGE[n.start:n.start_end])
        out = htmlmap.apply(PAGE, [{"op": "move", "id": b.id, "target": a.id, "where": "before"}])
        self.assertIn('<main>\n    <section id="b"><p>Second</p></section>\n    <section id="a"><p>First</p></section>\n  </main>', out)

    def test_sequential_edits_follow_moved_elements(self):
        nodes = htmlmap.parse(PAGE)
        a = next(n for n in nodes if 'id="a"' in PAGE[n.start:n.start_end])
        b = next(n for n in nodes if 'id="b"' in PAGE[n.start:n.start_end])
        pa = a.children[0]
        out = htmlmap.apply(PAGE, [{"op": "move", "id": a.id, "target": b.id, "where": "after"},
                                   {"op": "inner", "id": pa, "html": "First (edited)"}])
        self.assertLess(out.index("Second"), out.index("First (edited)"))

    def test_rejects_scripts_and_bad_moves(self):
        h1 = next(n for n in htmlmap.parse(PAGE) if n.tag == "h1")
        with self.assertRaises(htmlmap.EditError):
            htmlmap.apply(PAGE, [{"op": "inner", "id": h1.id, "html": "<img src=x onerror=alert(1)>"}])
        with self.assertRaises(htmlmap.EditError):
            htmlmap.apply(PAGE, [{"op": "move", "id": h1.id, "target": 99999}])
        with self.assertRaises(htmlmap.EditError):  # not siblings
            htmlmap.apply(PAGE, [{"op": "move", "id": h1.id, "target": h1.id + 3}])

    def test_implied_end_tags(self):
        src = "<body><ul><li>a<li>b</ul></body>"
        self.assertEqual(htmlmap.apply(src, [{"op": "inner", "id": 1, "html": "A"}]), "<body><ul><li>A<li>b</ul></body>")


class Styles(unittest.TestCase):
    RULES = [{"selector": "#top h1.title", "media": "", "props": {"font-size": "2.5rem", "font-family": "'Gowun Dodum', sans-serif"}},
             {"selector": "#a", "media": "mobile", "props": {"padding-top": "1rem", "width": "100%"}}]

    def test_render_parse_round_trip_and_font_import(self):
        css = styles.render(self.RULES)
        self.assertIn("fonts.googleapis.com", css)
        self.assertIn("@media (max-width: 720px)", css)
        self.assertEqual(styles.parse(css), self.RULES)

    def test_font_import_with_semicolons_parses_back(self):
        rules = [{"selector": "#headline", "media": "", "props": {"font-family": "'IBM Plex Sans KR', sans-serif"}}]
        css = styles.render(rules)
        self.assertIn("wght@400;500;700", css)
        self.assertEqual(styles.parse(css), rules)

    def test_validation(self):
        for bad in ([{"selector": "#a", "props": {"position": "fixed"}}],
                    [{"selector": "#a", "props": {"color": "red; } body { display:none"}}],
                    [{"selector": "</style><script>", "props": {"color": "red"}}],
                    [{"selector": "#a", "props": {"background": "url(javascript:alert(1))"}}]):
            with self.assertRaises(styles.StyleError):
                styles.validate(bad)

    def test_warnings_for_fixed_sizes(self):
        w = styles.warnings([{"selector": "#a", "media": "", "props": {"width": "900px", "height": "300px"}}])
        self.assertEqual(len(w), 2)
        self.assertEqual(styles.warnings(self.RULES), [])

    def test_link_is_added_once(self):
        once = styles.ensure_link(PAGE)
        self.assertEqual(styles.ensure_link(once), once)
        self.assertLess(once.index("style.css"), once.index(styles.FILE))  # last in <head>: editor rules win


class SaveAll(unittest.TestCase):
    def setUp(self):
        self.site = Path(tempfile.mkdtemp(prefix="visual-test-"))
        (self.site / "index.html").write_text(PAGE, encoding="utf-8")
        (self.site / "about.html").write_text(PAGE.replace("Demo", "About"), encoding="utf-8")
        self.ed = editor.Editor(self.site, history_dir=self.site.parent / (self.site.name + "-hist"))

    def test_plan_and_save_rules_and_html(self):
        h1 = next(n for n in htmlmap.parse(PAGE) if n.tag == "h1")
        body = {"rules": Styles.RULES, "page": "index.html",
                "html_edits": [{"op": "inner", "id": h1.id, "html": "New title"}]}
        diff = self.ed.preview_diff(body)
        self.assertEqual(diff["files"], ["about.html", "index.html", styles.FILE])
        self.assertFalse((self.site / styles.FILE).exists())  # preview writes nothing
        self.ed.save_all(body)
        index = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("New title", index)
        self.assertIn(styles.LINK, index)
        self.assertIn(styles.LINK, (self.site / "about.html").read_text(encoding="utf-8"))
        self.assertEqual(self.ed.read_styles()["rules"], Styles.RULES)
        self.assertEqual(len(self.ed.list_history()), 2)  # both existing pages snapshotted before writing

    def test_removing_all_rules_keeps_an_empty_file(self):
        self.ed.save_all({"rules": Styles.RULES})
        self.ed.save_all({"rules": []})
        self.assertEqual(self.ed.read_styles()["rules"], [])

    def test_non_git_site_works_without_discard(self):
        self.assertFalse(self.ed.is_git)
        with self.assertRaises(PermissionError):
            self.ed.discard("index.html")


if __name__ == "__main__":
    unittest.main()
