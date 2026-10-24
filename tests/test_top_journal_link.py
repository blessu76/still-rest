"""Regression: every public page has a Journal link at the TOP (header / top bar), not only in the footer.
Run: python3 -m unittest discover -s tests"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LANGS = "en ko ja zh es pt id ru vi fr de".split()
UI = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
HOME = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
HAS_JOURNAL = (REPO / "journal/index.html").is_file()
LIST_LANGS = {l for l in LANGS if (REPO / "journal" / l / "index.html").is_file()}


def pages():
    """(label, lang or None, html) for every generated/hand-written public page."""
    out = [("/", "en", REPO / "index.html")]
    for l in LANGS:
        out += [("/%s/" % l, l, REPO / l / "index.html"), ("/%s/faq/" % l, l, REPO / l / "faq" / "index.html"),
                ("/%s/about/" % l, l, REPO / l / "about" / "index.html")]
    out.append(("/journal/", "en", REPO / "journal" / "index.html"))
    for f in sorted((REPO / "journal").glob("*/**/index.html")):
        rel = f.relative_to(REPO).as_posix()
        lang = rel.split("/")[1]
        if lang in LANGS:
            out.append(("/" + rel[:-len("index.html")], lang, f))
    return [(label, lang, f.read_text(encoding="utf-8")) for label, lang, f in out]


def top_journal_link(h):
    """the first <a href="/journal/..."> of the body, plus whether anything of the page body comes before it."""
    body = h[h.index("<body>"):]
    m = re.search(r'<a [^>]*href="(/journal/[^"]*)"[^>]*>(.*?)</a>', body, re.S)
    assert m, "no Journal link in body"
    before = body[:m.start()]
    return m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip(), before


class TopJournalLink(unittest.TestCase):
    def test_every_page_links_the_journal_before_its_content(self):
        self.assertTrue(HAS_JOURNAL)
        for label, lang, h in pages():
            href, text, before = top_journal_link(h)
            # the FIRST journal link is already in the top area: before main content, any section, the hero and the footer
            for marker in ("<main", "<section", '<header class="hero', "<footer", 'class="foot-links"'):
                self.assertNotIn(marker, before, (label, marker))
            want = "/journal/%s/" % lang if lang in LIST_LANGS else "/journal/"
            self.assertEqual(href, want, label)
            self.assertTrue((REPO / href.strip("/") / "index.html").is_file(), (label, href))
            label_text = (UI[lang] if lang in UI else UI["en"])["journal"]
            self.assertEqual(text, label_text, label)
            self.assertEqual(label_text, HOME[lang]["foot_journal"], label)  # same word as the footer link

    def test_home_top_link_is_a_visible_pill_not_the_hidden_footer(self):
        for l in LANGS:
            h = (REPO / l / "index.html").read_text(encoding="utf-8")
            self.assertRegex(h, r'<a class="topnav" href="/journal/(%s/)?" data-i18n="foot_journal">' % l)
            self.assertNotIn("data-journal-top", h)

    def test_legal_pages_link_the_journal_in_their_top_bar(self):
        for name in ("privacy", "terms"):
            h = (REPO / name / "index.html").read_text(encoding="utf-8")
            top = h[h.index('<header class="topbar">'):h.index("</header>")]
            self.assertIn('href="/journal/" data-t="journal"', top, name)
            self.assertIn('jhref:"/journal/ko/"', h, name)  # the KO toggle points at the Korean list

    def test_journal_css_tops_are_not_muted_grey(self):
        css = (REPO / "assets/journal.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.bar-nav a\{color:var\(--ink\)")


if __name__ == "__main__":
    unittest.main()
