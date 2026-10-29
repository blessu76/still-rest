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
        shutil.copy(REPO / "robots.txt", self.tmp / "robots.txt")
        pages = ["index.html", "privacy/index.html", "terms/index.html"] + [
            "%s/%s" % (l, f) for l in ["en", "ko", "ja", "zh", "es", "pt", "id", "ru", "vi", "fr", "de"] for f in ("index.html", "faq/index.html", "about/index.html")]
        for rel in pages:  # the real pages: check() compares each one's head with its sitemap row
            (self.tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, self.tmp / rel)
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


    # ---- SEO guide v1 P0-4 / P0-5 / P0-6 -------------------------------------------------------------------------------------------
    def sub_page(self, rel, old, new):
        p = self.tmp / rel
        t = p.read_text(encoding="utf-8")
        self.assertIn(old, t)
        p.write_text(t.replace(old, new, 1), encoding="utf-8")

    def test_every_url_needs_a_lastmod_that_is_a_date(self):
        self.edit("<loc>https://still.ipe.rest/privacy/</loc>\n    <lastmod>2026-10-27</lastmod>", "<loc>https://still.ipe.rest/privacy/</loc>\n")
        self.assertIn("https://still.ipe.rest/privacy/: no lastmod", self.errs())
        self.edit("<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>2026-10-27</lastmod>", "<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>yesterday</lastmod>")
        self.assertTrue(any("terms/: lastmod is not a date" in e for e in self.errs()), self.errs())

    def test_a_lastmod_after_today_is_reported(self):
        self.edit("<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>2026-10-27</lastmod>", "<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>2026-10-30</lastmod>")
        urls = {"https://still.ipe.rest/terms/": []}
        last = {"https://still.ipe.rest/terms/": "2026-10-30"}
        clock = check_sitemap.parse_when
        self.assertEqual(check_sitemap.check_lastmod(urls, last, clock("2026-10-30 00:00")), [])  # the day itself is fine (KST)
        self.assertEqual(check_sitemap.check_lastmod(urls, last, clock("2026-10-29 23:59")),
                         ["https://still.ipe.rest/terms/: lastmod 2026-10-30 is after today (2026-10-29)"])
        self.assertEqual(check_sitemap.check_lastmod(urls, {"https://still.ipe.rest/terms/": "2026-10-30T09:00:00+09:00"}, clock("2026-10-30 09:00")), [])

    def test_the_default_clock_is_the_real_one(self):
        self.edit("<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>2026-10-27</lastmod>", "<loc>https://still.ipe.rest/terms/</loc>\n    <lastmod>2099-01-01</lastmod>")
        self.assertTrue(any("after today" in e for e in self.errs()), self.errs())

    def test_page_canonical_must_be_its_own_url(self):
        self.sub_page("ja/index.html", '<link rel="canonical" href="https://still.ipe.rest/ja/">', '<link rel="canonical" href="https://still.ipe.rest/en/">')
        self.assertTrue(any(e.startswith("https://still.ipe.rest/ja/: canonical is") for e in self.errs()), self.errs())

    def test_a_noindex_page_must_not_be_in_the_sitemap(self):
        self.sub_page("ja/faq/index.html", '<meta name="robots" content="index', '<meta name="robots" content="noindex')
        self.assertIn("https://still.ipe.rest/ja/faq/: is in the sitemap but noindex", self.errs())

    def test_html_and_sitemap_must_carry_the_same_hreflang_set(self):
        self.sub_page("de/index.html", '<link rel="alternate" hreflang="fr" href="https://still.ipe.rest/fr/">\n', "")
        errs = self.errs()
        self.assertTrue(any(e.startswith("https://still.ipe.rest/de/: html hreflang set differs") and "('fr'" in e for e in errs), errs)

    def test_a_journal_post_lastmod_is_its_json_ld_date_modified(self):
        posts = sorted((self.tmp / "journal").glob("ko/*/index.html"))
        self.assertTrue(posts)
        slug = posts[0].parent.name
        self.sub_page("journal/ko/%s/index.html" % slug, '"dateModified": "2026-', '"dateModified": "2025-')
        self.assertTrue(any("sitemap lastmod" in e and "!= JSON-LD dateModified 2025-" in e for e in self.errs()), self.errs())

    def test_robots_txt_must_point_at_the_sitemap(self):
        self.assertEqual(check_sitemap.check_robots(self.tmp), [])
        (self.tmp / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
        self.assertTrue(any("robots.txt: no `Sitemap:" in e for e in self.errs()), self.errs())
        (self.tmp / "robots.txt").unlink()
        self.assertIn("robots.txt: missing", self.errs())

    def test_the_journal_never_names_a_private_language(self):
        # vi has only draft posts and id is on hold: neither is a journal URL nor an hreflang target of one
        s = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        root = check_sitemap.ET.fromstring(s.encode("utf-8"))
        journal_rows = [u for u in root.findall("s:url", check_sitemap.NS) if "/journal/" in u.findtext("s:loc", namespaces=check_sitemap.NS)]
        self.assertTrue(journal_rows)
        for u in journal_rows:
            self.assertNotRegex(u.findtext("s:loc", namespaces=check_sitemap.NS), r"/journal/(vi|id)/")
            for l in u.findall("x:link", check_sitemap.NS):
                self.assertNotIn(l.get("hreflang"), ("vi", "id"))
                self.assertNotRegex(l.get("href"), r"/journal/(vi|id)/")

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


class LiveCheck(unittest.TestCase):
    """--live: 200 at that very address; a redirect or an error is a failure"""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/ok/":
                    self.send_response(200)
                    self.end_headers()
                elif self.path == "/moved/":
                    self.send_response(301)
                    self.send_header("Location", "/ok/")
                    self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *a):
                pass

        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_only_a_direct_200_passes(self):
        self.assertEqual(check_sitemap.live([self.base + "/ok/"]), [])
        errs = check_sitemap.live([self.base + "/moved/", self.base + "/gone/"])
        self.assertEqual(len(errs), 2)
        self.assertIn("HTTP 301 (redirect", errs[0])
        self.assertIn("HTTP 404", errs[1])


if __name__ == "__main__":
    unittest.main()
