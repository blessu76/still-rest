"""Tests for scripts/check_sitemap.py — run: python3 -m unittest discover -s tests"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import check_sitemap  # noqa: E402


class CheckSitemap(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(REPO / "sitemap.xml", self.tmp / "sitemap.xml")
        for l in ["en", "ko", "ja", "zh", "es", "pt", "id", "ru", "vi", "fr", "de"]:
            (self.tmp / l).mkdir()
            (self.tmp / l / "index.html").write_text("x")
            for page in ("faq", "about"):
                (self.tmp / l / page).mkdir()
                (self.tmp / l / page / "index.html").write_text("x")
        (self.tmp / "index.html").write_text("x")
        for page in ("privacy", "terms"):
            (self.tmp / page).mkdir()
            (self.tmp / page / "index.html").write_text("x")
        j = REPO / "journal"
        if j.is_dir():  # journal pages exist in the repo once the journal is built; mirror them
            shutil.copytree(j, self.tmp / "journal")
            shutil.copytree(REPO / "content", self.tmp / "content")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def errs(self):
        return check_sitemap.check(self.tmp)[0]

    def edit(self, old, new):
        p = self.tmp / "sitemap.xml"
        s = p.read_text(encoding="utf-8")
        self.assertIn(old, s)
        p.write_text(s.replace(old, new, 1), encoding="utf-8")

    def test_committed_sitemap_is_clean(self):
        self.assertEqual(self.errs(), [])

    def test_missing_language_page_is_reported(self):
        s = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        a = s.index("<url>\n    <loc>https://still.ipe.rest/de/</loc>")
        b = s.index("</url>", a) + len("</url>\n")
        (self.tmp / "sitemap.xml").write_text(s[:a] + s[b:], encoding="utf-8")
        self.assertTrue(any("missing from sitemap: https://still.ipe.rest/de/" in e for e in self.errs()), self.errs())

    def test_query_string_urls_are_rejected(self):
        self.edit("<loc>https://still.ipe.rest/ko/</loc>", "<loc>https://still.ipe.rest/?lang=ko</loc>")
        self.assertTrue(any("query" in e for e in self.errs()), self.errs())

    def test_legal_pages_are_required_in_the_sitemap(self):
        s = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        for page in ("privacy", "terms"):
            self.assertIn("<loc>https://still.ipe.rest/%s/</loc>" % page, s)
            a = s.index("<loc>https://still.ipe.rest/%s/</loc>" % page)
            a = s.rindex("<url>", 0, a)
            b = s.index("</url>", a) + len("</url>")
            (self.tmp / "sitemap.xml").write_text(s[:a] + s[b:], encoding="utf-8")
            self.assertIn("missing from sitemap: https://still.ipe.rest/%s/" % page, self.errs())
            (self.tmp / "sitemap.xml").write_text(s, encoding="utf-8")

    def test_unbuilt_page_is_reported(self):
        (self.tmp / "ja" / "index.html").unlink()
        self.assertTrue(any("no built page for https://still.ipe.rest/ja/" in e for e in self.errs()), self.errs())

    def test_non_reciprocal_hreflang_is_reported(self):
        # make /ko/ declare itself as "ja" -> /ja/ lists ko under "ko", not "ja"
        s = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        a = s.index("<loc>https://still.ipe.rest/ko/</loc>")
        b = s.index("</url>", a)
        block = s[a:b].replace('hreflang="ko" href="https://still.ipe.rest/ko/"', 'hreflang="ja" href="https://still.ipe.rest/ko/"')
        (self.tmp / "sitemap.xml").write_text(s[:a] + block + s[b:], encoding="utf-8")
        self.assertTrue(any("duplicate hreflang" in e or "not reciprocal" in e for e in self.errs()), self.errs())

    def test_x_default_required(self):
        s = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        a = s.index("<loc>https://still.ipe.rest/fr/</loc>")
        b = s.index("</url>", a)
        block = s[a:b].replace('hreflang="x-default"', 'hreflang="xx"')
        (self.tmp / "sitemap.xml").write_text(s[:a] + block + s[b:], encoding="utf-8")
        self.assertTrue(any("no x-default" in e for e in self.errs()), self.errs())

    def test_broken_xml_is_reported(self):
        (self.tmp / "sitemap.xml").write_text("<urlset>", encoding="utf-8")
        self.assertTrue(self.errs())




class CommittedSitemapMatchesPages(unittest.TestCase):
    """every sitemap <loc> is a real page of this repo whose own <link rel="canonical"> is exactly that URL (slash included)"""

    def test_every_loc_is_the_canonical_of_its_page(self):
        root = check_sitemap.ET.parse(REPO / "sitemap.xml").getroot()
        locs = [(u.findtext("s:loc", namespaces=check_sitemap.NS) or "").strip() for u in root.findall("s:url", check_sitemap.NS)]
        self.assertGreater(len(locs), 30)
        self.assertIn(check_sitemap.SITE + "/privacy/", locs)
        self.assertIn(check_sitemap.SITE + "/terms/", locs)
        for loc in locs:
            rel = loc[len(check_sitemap.SITE) + 1:]
            page = REPO / rel / "index.html"
            self.assertTrue(page.is_file(), loc)
            found = re.findall(r'<link rel="canonical" href="([^"]*)"', page.read_text(encoding="utf-8"))
            self.assertEqual(found, [loc], loc)

    def test_legal_pages_have_changefreq_and_priority(self):
        root = check_sitemap.ET.parse(REPO / "sitemap.xml").getroot()
        rows = {u.findtext("s:loc", namespaces=check_sitemap.NS): u for u in root.findall("s:url", check_sitemap.NS)}
        for page in ("privacy", "terms"):
            u = rows["%s/%s/" % (check_sitemap.SITE, page)]
            self.assertEqual(u.findtext("s:changefreq", namespaces=check_sitemap.NS), "yearly")
            self.assertEqual(u.findtext("s:priority", namespaces=check_sitemap.NS), "0.3")
            self.assertRegex(u.findtext("s:lastmod", namespaces=check_sitemap.NS), r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
