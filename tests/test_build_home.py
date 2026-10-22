"""Tests for scripts/build_home.py (11 static home pages) — run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LANGS = "en ko ja zh es pt id ru vi fr de".split()
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}


class BuildHome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        for f in ("sitemap.xml", "llms.txt"):
            shutil.copy(REPO / f, cls.tmp / f)
        shutil.copytree(REPO / "content/home", cls.tmp / "content/home")
        cls.build()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    @classmethod
    def build(cls):
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_home.py"), "--root", str(cls.tmp)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def page(self, lang=None):
        return (self.tmp / (lang + "/index.html" if lang else "index.html")).read_text(encoding="utf-8")

    def test_every_language_is_a_static_page(self):
        for l in LANGS:
            h = self.page(l)
            self.assertIn('<html lang="%s" dir="ltr">' % l, h, l)
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/%s/">' % l, h, l)
            got = dict(re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', h))
            self.assertEqual(set(got), set(LANGS) | {"x-default"}, l)
            self.assertEqual(got["x-default"], "https://still.ipe.rest/")
            self.assertTrue(all(got[x] == "https://still.ipe.rest/%s/" % x for x in LANGS), l)
            self.assertNotIn("?lang=", h, l)  # no query-parameter language anywhere (not even the legacy redirect: root only)
            self.assertEqual(h.count('rel="canonical"'), 1)
            self.assertNotIn("{{", h)
            self.assertIn('<meta property="og:locale" content="', h)
            self.assertIn("og:locale:alternate", h)
            self.assertIn("cloudflareinsights", h)  # cookieless analytics kept
            self.assertIn('href="/privacy"', h)  # footer link to the privacy page keeps working
            self.assertIn('<option value="%s" selected>' % l, h)

    def test_text_follows_the_language(self):
        titles = {re.search(r"<title>(.*?)</title>", self.page(l)).group(1) for l in LANGS}
        self.assertEqual(len(titles), len(LANGS))
        self.assertIn("ko_KR", self.page("ko"))
        self.assertIn("고요히", self.page("ko"))
        self.assertIn("Be still. A Bible for the hard days.", self.page("en"))
        self.assertNotIn("Be still. A Bible for the hard days.", self.page("ko"))
        self.assertIn('"inLanguage": "ja"', self.page("ja"))

    def test_strings_cover_every_template_key(self):
        strings = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
        tpl = (REPO / "content/home/template.html").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n(?:-ph)?="([^"]+)"', tpl)) | {"meta_title", "meta_desc"}
        self.assertEqual(list(strings), LANGS)
        for l in LANGS:
            self.assertFalse(keys - set(strings[l]), "%s lacks %s" % (l, sorted(keys - set(strings[l]))))

    def test_root_is_x_default_without_forced_redirect(self):
        h = self.page()
        self.assertIn('<link rel="canonical" href="https://still.ipe.rest/">', h)
        self.assertIn('<html lang="en" dir="ltr">', h)
        self.assertIn('id="langHint" hidden', h)  # hint only: hidden until JS decides, never a redirect
        self.assertNotIn('http-equiv="refresh"', h)
        self.assertNotIn("langHint", self.page("ja"))  # only the root has the hint
        self.assertNotIn("langHint", self.page("en"))

    def test_legacy_query_redirect_is_first_script_of_root_only(self):
        h = self.page()
        self.assertIn("get('lang')", h)
        self.assertLess(h.index("get('lang')"), h.index("<title>"))  # top of <head>, before anything renders
        self.assertIn("location.replace('/'+l+'/'+location.hash)", h)
        self.assertIn(r"/^(" + "|".join(LANGS) + r")$/", h)  # only known language codes are followed
        for l in LANGS:
            self.assertNotIn("get('lang')", self.page(l))

    def test_sitemap_has_home_in_every_language(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        rows = {u.find("s:loc", NS).text: u for u in root.findall("s:url", NS)}
        self.assertEqual(len(rows), 12)  # "/" + 11 languages
        for loc, u in rows.items():
            self.assertEqual(len(u.findall("x:link", NS)), 12, loc)  # 11 languages + x-default
            self.assertIsNotNone(u.find("s:lastmod", NS))
            self.assertEqual(len(u.findall("{http://www.google.com/schemas/sitemap-image/1.1}image"), ), 1)
        for l in LANGS:
            self.assertIn("https://still.ipe.rest/%s/" % l, rows)
        self.assertIn("https://still.ipe.rest/", rows)
        self.assertFalse([l for l in rows if "?lang=" in l])
        self.assertIn("https://still.ipe.rest/ja/", (self.tmp / "llms.txt").read_text(encoding="utf-8"))

    def test_idempotent(self):
        before = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}
        self.build()
        self.assertEqual(before, {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()})

    def test_committed_pages_are_up_to_date(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_home.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class Robots(unittest.TestCase):
    def test_ai_bots_allowed_and_sitemap_listed(self):
        txt = (REPO / "robots.txt").read_text(encoding="utf-8")
        for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
            self.assertRegex(txt, r"User-agent: %s\nAllow: /\n" % bot)
        self.assertNotRegex(txt, r"(?m)^Disallow:\s*/\s*$")
        self.assertIn("Sitemap: https://still.ipe.rest/sitemap.xml", txt)


if __name__ == "__main__":
    unittest.main()
