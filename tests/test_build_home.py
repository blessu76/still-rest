"""Tests for scripts/build_home.py (11 static home pages) — run: python3 -m unittest discover -s tests"""
import html
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
            self.assertIn('<a href="/privacy/" data-i18n="foot_privacy">', h)  # footer links use the canonical (slash) form
            self.assertIn('<a href="/terms/" data-i18n="foot_terms">', h)
            self.assertNotIn('href="/privacy"', h)
            self.assertNotIn('href="/terms"', h)
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

    def test_accessibility_labels_and_structured_data_follow_the_language(self):
        strings = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
        for l in LANGS:
            h = self.page(l)
            for k in ("aria_lang", "aria_verse_card", "aria_save", "aria_listen", "aria_email", "aria_footer", "aria_close", "og_image_alt"):
                self.assertTrue(strings[l].get(k), "%s lacks %s" % (l, k))
            for k in ("aria_lang", "aria_verse_card", "aria_save", "aria_listen", "aria_email", "aria_footer"):
                self.assertIn('aria-label="%s"' % html.escape(strings[l][k]), h, "%s %s" % (l, k))
            self.assertIn('<meta property="og:image:alt" content="%s">' % html.escape(strings[l]["og_image_alt"]), h, l)
            ld = json.loads(re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', h, re.S).group(1))
            app = ld["@graph"][0]
            self.assertEqual(app["inLanguage"], l)
            self.assertEqual(app["description"], strings[l].get("ld_desc") or strings[l]["meta_desc"], l)
            if l != "en":
                for english in ("Language", "Footer", "Email address", "Save this verse", "Example verse card", "Listen with calm music"):
                    self.assertNotIn('aria-label="%s"' % english, h, "%s still has English %r" % (l, english))
                self.assertNotIn("A private, on-device AI companion", h, l)
        self.assertNotIn('aria-label="×"', self.page(None))  # the hint's close button is labelled in English too, never a bare ×
        self.assertIn('CLOSE = "Close"', self.page(None))
        self.assertNotIn("CLOSE", self.page("ko"))  # hint is root only

    def test_language_switch_is_plain_links_too(self):
        for l in [None] + LANGS:
            h = self.page(l)
            nav = re.search(r'<nav class="foot-langs".*?</nav>', h, re.S).group(0)
            self.assertEqual(re.findall(r'<a href="/(\w+)/" hreflang="\1" lang="\1"', nav), LANGS, l)
            self.assertEqual(re.findall(r'<a href="/(\w+)/"[^>]*aria-current', nav), [l] if l else [], l)

    def test_sitemap_has_home_in_every_language(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        rows = {u.find("s:loc", NS).text: u for u in root.findall("s:url", NS) if "/journal/" not in u.find("s:loc", NS).text and u.find("x:link", NS) is not None and u.find("{http://www.google.com/schemas/sitemap-image/1.1}image") is not None}  # home rows (info pages have alternates but no image, legal pages neither)
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

    def test_journal_link_is_hidden_until_there_is_a_post(self):
        for l in [None] + LANGS:  # no post in the repo -> no Journal link anywhere on the home pages, section stays hidden
            h = self.page(l)
            self.assertNotIn("data-journal-link", h, l)
            self.assertNotIn("foot_journal", h, l)
            foot = h[h.index('<nav class="foot-links"'):h.index("</nav>", h.index('<nav class="foot-links"'))]
            self.assertNotIn("/journal/", foot, l)
            self.assertIn('<section class="journal" id="journal" hidden>', h, l)

    def test_journal_link_appears_with_cards(self):
        sys.path.insert(0, str(REPO / "scripts"))
        import build_home
        tpl = (REPO / "content/home/template.html").read_text(encoding="utf-8")
        strings = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
        shown = build_home.render_page(tpl, strings, "ko", False, '<article class="j-card">x</article>', "/journal/ko/")
        self.assertIn('<a href="/journal/ko/" data-i18n="foot_journal">저널</a>', shown)
        self.assertNotIn("data-journal-link", shown)
        self.assertNotIn(" hidden>", re.search(r'<section class="journal"[^>]*>', shown).group(0))
        gone = build_home.render_page(tpl, strings, "ko", False, "", "/journal/ko/")
        self.assertNotIn("저널</a>", gone)
        self.assertIn("개인정보</a>", gone)  # the other footer links stay

    def test_sitemap_lists_legal_pages(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        locs = {u.find("s:loc", NS).text for u in root.findall("s:url", NS) if "/journal/" not in u.find("s:loc", NS).text}
        self.assertEqual(len(locs), 36)  # 12 home + 22 faq/about + privacy + terms
        self.assertLessEqual({"https://still.ipe.rest/privacy/", "https://still.ipe.rest/terms/"}, locs)
        self.assertFalse({"https://still.ipe.rest/privacy", "https://still.ipe.rest/terms"} & locs)

    def test_legal_pages_canonical_has_trailing_slash(self):
        for page in ("privacy", "terms"):
            h = (REPO / page / "index.html").read_text(encoding="utf-8")
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/%s/">' % page, h)
            self.assertNotRegex(h, r'href="/(privacy|terms)"')  # internal links use the slash form too

    def test_idempotent(self):
        before = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}
        self.build()
        self.assertEqual(before, {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()})

    def test_committed_pages_are_up_to_date(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_home.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class HomeStamp(unittest.TestCase):
    """sitemap lastmod of the home pages follows the home copy by itself (content/home/stamp.json = hash of template + i18n)"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for f in ("sitemap.xml", "llms.txt"):
            shutil.copy(REPO / f, self.tmp / f)
        shutil.copytree(REPO / "content/home", self.tmp / "content/home")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_home.py"), "--root", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def stamp(self):
        return json.loads((self.tmp / "content/home/stamp.json").read_text(encoding="utf-8"))

    def lastmods(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        return {u.find("s:loc", NS).text: u.find("s:lastmod", NS).text for u in root.findall("s:url", NS) if "/journal/" not in u.find("s:loc", NS).text and u.find("{http://www.google.com/schemas/sitemap-image/1.1}image") is not None}  # home rows only

    def test_unchanged_copy_keeps_its_date(self):
        stamp = self.stamp()
        stamp["date"] = "2026-01-02"  # pretend the copy was last changed long ago
        (self.tmp / "content/home/stamp.json").write_text(json.dumps(stamp), encoding="utf-8")
        self.build()
        self.assertEqual(self.stamp()["date"], "2026-01-02")
        self.assertEqual(set(self.lastmods().values()), {"2026-01-02"})

    def test_changed_copy_gets_todays_date(self):
        import datetime
        f = self.tmp / "content/home/i18n.json"
        d = json.loads(f.read_text(encoding="utf-8"))
        d["en"]["hero_sub"] += " (edited)"
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        stamp = self.stamp()
        stamp["date"] = "2026-01-02"
        (self.tmp / "content/home/stamp.json").write_text(json.dumps(stamp), encoding="utf-8")
        self.build()
        today = datetime.date.today().isoformat()
        self.assertEqual(self.stamp()["date"], today)
        self.assertNotEqual(self.stamp()["hash"], stamp["hash"])
        self.assertEqual(set(self.lastmods().values()), {today})

    def test_check_reports_a_copy_change_that_was_not_built(self):
        f = self.tmp / "content/home/template.html"
        f.write_text(f.read_text(encoding="utf-8") + "<!-- touched -->\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_home.py"), "--root", str(self.tmp), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("out of date", r.stderr)


class DeployWorkflow(unittest.TestCase):
    """rsync excludes are anchored to the repo root — an unanchored 'content' would also drop any nested content/ dir."""

    def rsync_cmd(self):
        y = (REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        m = re.search(r"^\s*rsync .*$", y, re.M)
        self.assertIsNotNone(m)
        return m.group(0).strip()

    def test_excludes_are_anchored_to_the_root(self):
        ex = re.findall(r"--exclude='([^']+)'", self.rsync_cmd())
        self.assertEqual(set(ex), {"/.git", "/.github", "/content", "/scripts", "/tests"})

    @unittest.skipUnless(shutil.which("rsync"), "rsync not installed")
    def test_nested_dirs_with_the_same_name_survive(self):
        src, dst = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        try:
            for rel in ("content/x", "scripts/x", "tests/x", ".git/x", ".github/x", "journal/en/content/keep", "a/scripts/keep", "index.html"):
                f = src / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("x")
            cmd = self.rsync_cmd().replace('"$RUNNER_TEMP/site/"', str(dst) + "/")
            r = subprocess.run(cmd, shell=True, cwd=src, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = {str(p.relative_to(dst)) for p in dst.rglob("*") if p.is_file()}
            self.assertEqual(got, {"index.html", "journal/en/content/keep", "a/scripts/keep"})
        finally:
            shutil.rmtree(src)
            shutil.rmtree(dst)


class Robots(unittest.TestCase):
    def test_ai_bots_allowed_and_sitemap_listed(self):
        txt = (REPO / "robots.txt").read_text(encoding="utf-8")
        for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
            self.assertRegex(txt, r"User-agent: %s\nAllow: /\n" % bot)
        self.assertNotRegex(txt, r"(?m)^Disallow:\s*/\s*$")
        self.assertIn("Sitemap: https://still.ipe.rest/sitemap.xml", txt)


if __name__ == "__main__":
    unittest.main()
