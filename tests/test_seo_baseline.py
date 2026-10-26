"""SEO baseline regressions (live audit 2026-10-26): head meta of the legal pages, non-blocking Google Fonts, og:type on every list, no
duplicate title/description between pages, meta descriptions within 160 characters, a real 404.html.
Run: python3 -m unittest discover -s tests"""
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from site_common import LANGS, ORG_ID, SITE, font_links, meta_desc  # noqa: E402
from test_build_journal import Base, run  # noqa: E402
from test_journal_paging import series  # noqa: E402

SOURCES = ("content", "scripts", "tests", ".git", ".github")
LD = re.compile(r'<script type="application/ld\+json">\n(.*?)\n</script>', re.S)
NOSCRIPT = re.compile(r"<noscript>.*?</noscript>", re.S)


def pages_of(root):
    """{relative path: html} of every page under root (not the build sources)."""
    root = Path(root)
    out = {}
    for f in sorted(root.rglob("*.html")):
        rel = f.relative_to(root)
        if rel.parts[0] not in SOURCES:
            out[str(rel)] = f.read_text(encoding="utf-8")
    return out


def tag(page, pattern):
    m = re.search(pattern, page, re.S)
    return html.unescape(m.group(1)) if m else None


def title_of(page):
    return tag(page, r"<title>(.*?)</title>")


def desc_of(page):
    return tag(page, r'<meta name="description" content="(.*?)">')


def indexable(page):
    return "noindex" not in (tag(page, r'<meta name="robots" content="(.*?)">') or "")


def blocking_font_links(page):
    """Google Fonts <link rel=stylesheet> outside <noscript> that is not the media=print/onload kind (= render blocking)."""
    bad = []
    for m in re.finditer(r"<link\b[^>]*>", NOSCRIPT.sub("", page)):
        t = m.group(0)
        if "fonts.googleapis.com/css" in t and "stylesheet" in t and not ('media="print"' in t and "onload=" in t):
            bad.append(t)
    return bad


class Checks:
    """the same checks on any set of built pages; subclasses provide self.pages."""

    def test_fonts_never_block_rendering(self):
        for rel, p in self.pages.items():
            self.assertEqual(blocking_font_links(p), [], rel)
            if "fonts.googleapis.com/css" in p:
                self.assertIn('<link rel="preconnect" href="https://fonts.googleapis.com">', p, rel)
                self.assertIn('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>', p, rel)
                self.assertRegex(p, r'<noscript><link rel="stylesheet" href="https://fonts\.googleapis\.com/css[^"]*display=swap"></noscript>', rel)
                self.assertIn("display=swap", p, rel)

    def test_descriptions_fit_160(self):
        for rel, p in self.pages.items():
            for pat in (r'<meta name="description" content="(.*?)">', r'<meta property="og:description" content="(.*?)">',
                        r'<meta name="twitter:description" content="(.*?)">'):
                d = tag(p, pat)
                if d is not None:
                    self.assertLessEqual(len(d), 160, "%s: %s" % (rel, pat))

    def test_every_indexable_page_has_og_type_and_one_h1(self):
        for rel, p in self.pages.items():
            if not indexable(p):
                continue
            self.assertRegex(p, r'<meta property="og:type" content="(website|article)">', rel)
            self.assertEqual(len(re.findall(r"<h1[ >]", p)), 1, rel)

    def test_no_title_or_description_repeats_between_pages(self):
        titles, descs = defaultdict(list), defaultdict(list)
        for rel, p in self.pages.items():
            if indexable(p):
                titles[title_of(p)].append(rel)
                descs[desc_of(p)].append(rel)
        self.assertEqual({k: v for k, v in titles.items() if len(v) > 1}, {})
        self.assertEqual({k: v for k, v in descs.items() if len(v) > 1}, {})

    def test_lists_are_websites(self):
        lists = [r for r in self.pages if re.fullmatch(r"journal/(([a-z]{2}/)?(page/\d+/)?)index\.html", r)]
        self.assertTrue(lists)
        for rel in lists:
            self.assertIn('<meta property="og:type" content="website">', self.pages[rel], rel)


class Committed(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = pages_of(REPO)

    def test_privacy_and_terms_have_the_full_head(self):
        for name, title_en, title_ko in (("privacy", "Privacy Policy — still()", "개인정보 처리방침 — still()"), ("terms", "Terms of Use — still()", "이용약관 — still()")):
            p = self.pages["%s/index.html" % name]
            url = "%s/%s/" % (SITE, name)
            self.assertIn('<link rel="canonical" href="%s">' % url, p)
            self.assertIn('<link rel="alternate" hreflang="en" href="%s">' % url, p)
            self.assertIn('<link rel="alternate" hreflang="x-default" href="%s">' % url, p)
            for prop, val in (("og:type", "website"), ("og:url", url), ("og:title", title_en), ("og:image", SITE + "/og-image.png"), ("og:site_name", "still()")):
                self.assertIn('<meta property="%s" content="%s">' % (prop, val), p, (name, prop))
            d = desc_of(p)
            self.assertEqual(tag(p, r'<meta property="og:description" content="(.*?)">'), d)
            self.assertEqual(tag(p, r'<meta name="twitter:description" content="(.*?)">'), d)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', p)
            self.assertIn('<meta name="twitter:title" content="%s">' % title_en, p)
            self.assertIn('<meta name="twitter:image" content="%s/og-image.png">' % SITE, p)
            ld = [json.loads(x) for x in LD.findall(p)]
            self.assertEqual(len(ld), 1)
            self.assertEqual(ld[0]["@type"], "WebPage")
            self.assertEqual(ld[0]["url"], url)
            self.assertEqual(ld[0]["publisher"]["@id"], ORG_ID)
            self.assertEqual(ld[0]["description"], d)
            # exactly one h1, outside the language blocks; the language switch rewrites it
            self.assertEqual(len(re.findall(r"<h1[ >]", p)), 1)
            self.assertRegex(p, r'<h1 data-t="h1">%s</h1>' % re.escape(title_en))
            self.assertIn('title:"%s"' % title_ko, p)
            self.assertIn("querySelector('[data-t=\"h1\"]')", p)

    def test_404_page(self):
        p = (REPO / "404.html").read_text(encoding="utf-8")
        self.assertRegex(p, r'<meta name="robots" content="noindex[^"]*">')
        self.assertNotIn("<link rel=\"canonical\"", p)
        self.assertIn('href="/"', p)
        self.assertIn('href="/journal/"', p)
        for l in LANGS:  # a line (home link) per language
            self.assertIn('<li lang="%s">' % l, p)
            self.assertIn('href="/%s/"' % l, p)
        self.assertEqual(len(re.findall(r"<h1[ >]", p)), 1)
        self.assertEqual(blocking_font_links(p), [])
        self.assertNotIn("/404.html", (REPO / "sitemap.xml").read_text(encoding="utf-8"))  # a 404 is never submitted

    def test_font_helper_is_the_markup_the_pages_use(self):
        links = font_links()
        self.assertIn('media="print" onload="this.media=\'all\'"', links)
        self.assertIn("<noscript>", links)
        for rel in ("index.html", "en/index.html", "journal/index.html", "en/faq/index.html"):
            self.assertIn(links, self.pages[rel], rel)


class Meta(unittest.TestCase):
    def test_meta_desc(self):
        self.assertEqual(meta_desc("Short one."), "Short one.")
        long = "First sentence here. " * 12  # 252 chars
        cut = meta_desc(long)
        self.assertLessEqual(len(cut), 160)
        self.assertTrue(cut.endswith("here."))  # whole sentences only
        self.assertEqual(meta_desc("word " * 80)[-1], "…")  # no sentence boundary -> a word boundary + ellipsis
        self.assertLessEqual(len(meta_desc("word " * 80)), 160)
        self.assertLessEqual(len(meta_desc("가" * 400)), 160)
        self.assertEqual(meta_desc("한 문장입니다。" * 30)[-1], "。")


class FullSiteBuilt(Checks, unittest.TestCase):
    """the whole site as the deploy runner builds it (every scheduled post open, far in the future), so every post and language is covered."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO, cls.tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_journal.py"), "--root", str(cls.tmp / "s"), "--now", "2099-01-01 00:00"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.pages = pages_of(cls.tmp / "s")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)


class PagedLists(Checks, Base):
    """21 posts in two languages -> 3 pages per list: page numbers, languages and the hub each keep their own title and description."""

    def setUp(self):
        super().setUp()
        series(self.tmp, 21, langs=("ko", "en"))
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.pages = {rel: p for rel, p in pages_of(self.tmp).items() if rel.startswith("journal/")}  # the fixture's other pages are stubs

    def test_list_titles_name_the_scope_and_the_page(self):
        self.assertEqual(title_of(self.pages["journal/index.html"]), "Journal — still() · All languages")
        self.assertEqual(title_of(self.pages["journal/en/index.html"]), "Journal — still() · English")
        self.assertEqual(title_of(self.pages["journal/ko/page/2/index.html"]), "저널 — still() · 한국어 · 2페이지")
        self.assertEqual(title_of(self.pages["journal/page/3/index.html"]), "Journal — still() · All languages · Page 3")


if __name__ == "__main__":
    unittest.main()
