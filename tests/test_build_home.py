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
LANGS = "en ko ja zh-Hant es pt-BR fr de id th vi tr".split()  # the kit's 12 (scripts/site_common.LANGS)
ENDED = "zh ru ar hi".split()  # ended languages: folders stay frozen, but they are in no list / hreflang / sitemap and are never rebuilt
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

    def test_the_home_verse_reference_is_written_in_the_page_language(self):
        # Psalm 46:10 is the home card's verse; its reference follows the language like the verse text (and the journal's scripture.json: ru/fr
        # number the Psalm by their source text, ru 45:11, fr 46:11)
        want = {"en": "Psalm 46:10", "ko": "시편 46:10", "ja": "詩篇 46:10", "zh-Hant": "詩篇 46:10", "es": "Salmos 46:10", "pt-BR": "Salmos 46:10",
                "fr": "Psaume 46:11", "de": "Psalm 46:10", "id": "Mazmur 46:10", "th": "สดุดี 46:10", "vi": "Thi Thiên 46:10", "tr": "Mezmur 46:10"}
        self.assertEqual(set(want), set(LANGS))
        frozen = {"zh": "诗篇 46:10", "ru": "Псалом 45:11"}  # ended languages: no home page, but their journal scripture.json entries stay
        for l in LANGS:
            self.assertEqual(re.findall(r'<div class="verse-ref"[^>]*>([^<]*)</div>', self.page(l)), [want[l]], l)
        self.assertEqual(re.findall(r'<div class="verse-ref"[^>]*>([^<]*)</div>', self.page()), ["Psalm 46:10"])  # root = x-default = English
        scripture = json.loads((REPO / "content/journal/scripture.json").read_text(encoding="utf-8"))["verses"]["PSA 46:10"]
        for l, e in scripture.items():
            self.assertEqual(e["ref"], {**want, **frozen}[l], l)  # the home and the journal never write the same verse two ways

    def test_every_language_is_a_static_page(self):
        for l in LANGS:
            h = self.page(l)
            self.assertIn('<html lang="%s" dir="ltr">' % l, h, l)  # all 12 are left-to-right
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/%s/">' % l, h, l)
            got = dict(re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', h))
            self.assertEqual(set(got), set(LANGS) | {"x-default"}, l)
            self.assertEqual(got["x-default"], "https://still.ipe.rest/")
            self.assertFalse(set(got) & set(ENDED), l)  # ended languages are not alternates
            for sid in ("lang", "foot-lang"):
                block = re.search(r'<select id="%s".*?</select>' % sid, h, re.S).group(0)
                self.assertEqual(len(re.findall(r'<option value="', block)), len(LANGS), (l, sid))
            self.assertFalse([e for e in ENDED if '<option value="%s"' % e in h], l)
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
        self.assertEqual(set(strings) & set(LANGS), set(LANGS))  # file order is not significant (frozen ended-language keys may remain)
        self.assertNotIn("pt", strings)  # the data key moved pt -> pt-BR
        self.assertTrue(set(LANGS) <= set(strings))
        for l in LANGS:
            self.assertFalse(keys - set(strings[l]), "%s lacks %s" % (l, sorted(keys - set(strings[l]))))

    def test_root_is_x_default_english_with_language_rule_script(self):
        h = self.page()
        self.assertIn('<link rel="canonical" href="https://still.ipe.rest/">', h)
        self.assertIn('<html lang="en" dir="ltr">', h)
        self.assertNotIn('http-equiv="refresh"', h)  # the move is the language script's, not a static refresh (crawlers stay on the English root)
        self.assertNotIn("langHint", h)  # the old "한국어 →" hint band is gone
        self.assertNotIn("lang-hint", h)

    def root_script(self):
        return re.search(r"<script>(\(function\(\)\{try\{var ALL=.*?)</script>", self.page(), re.S).group(1)

    def test_root_script_is_first_in_head_and_follows_url_stored_browser_english_order(self):
        h = self.page()
        self.assertLess(h.index("var ALL="), h.index("<title>"))  # top of <head>, before anything renders
        js = self.root_script()
        order = [js.index(k) for k in ("q=u.get('lang')", "localStorage.getItem('still_lang')", "navigator.languages")]
        self.assertEqual(order, sorted(order))  # 1 URL, 2 stored choice, 3 browser; nothing found -> no move = English
        self.assertIn("location.replace(PRE+pick+'/'", js)
        self.assertIn("location.hash", js)
        self.assertIn("'zh-Hant'", js)  # zh-TW/HK/MO/Hant -> zh-Hant (kit resolve)
        self.assertIn("return'pt-BR'", js)  # pt* -> pt-BR
        self.assertIn("c==='in'", js)  # in -> id
        for e in ENDED:  # ended languages can never be picked
            self.assertNotIn('"%s"' % e, js, e)
        self.assertIn('ALL=' + json.dumps(LANGS), js)  # only known language codes are followed
        self.assertIn('PRE="/"', js)

    def test_root_script_never_targets_the_ended_languages_or_old_pt(self):
        js = self.root_script()
        self.assertNotIn('"pt"', js)
        self.assertNotIn("'pt'", js.replace("c===\'pt\'", "").replace("c==='pt'", ""))  # only the pt* -> pt-BR input rule mentions pt

    def test_language_pages_never_move_the_visitor(self):
        for l in LANGS:
            h = self.page(l)
            self.assertNotIn("var ALL=", h, l)
            self.assertNotIn("location.replace", h, l)
            self.assertNotIn("get('lang')", h, l)
            self.assertNotIn("navigator.language", h, l)  # the URL is the decision on a /xx/ page

    def test_language_choice_is_stored(self):
        for l in [None] + LANGS:
            h = self.page(l)
            self.assertIn("localStorage.setItem('still_lang', this.value)", h, l)  # the <select>
            self.assertIn("localStorage.setItem('still_lang', m[1])", h, l)  # footer <select id="foot-lang">

    def test_root_script_behavior(self):
        """run the real root script in node with a fake window: ?lang / stored / browser order, English stays, links keep query and hash."""
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        harness = (
            "const js = require('fs').readFileSync(0, 'utf8');\n"
            "function run(o) { let to = null, store = Object.assign({}, o.stored || {});\n"
            "  const location = { search: o.search || '', hash: o.hash || '', replace: (u) => { to = u; } };\n"
            "  const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } };\n"
            "  const navigator = { languages: o.langs || [], language: (o.langs || [])[0] };\n"
            "  new Function('location', 'localStorage', 'navigator', 'URLSearchParams', js)(location, localStorage, navigator, URLSearchParams);\n"
            "  return { to, store }; }\n"
            "const cases = JSON.parse(process.argv[1]);\n"
            "console.log(JSON.stringify(cases.map(run)));\n")
        cases = [
            {"langs": ["ko-KR", "en-US"]},                                   # 0 browser Korean -> /ko/
            {"langs": ["en-US"]},                                            # 1 English browser -> stays
            {"langs": ["fr"]},                                               # 2 -> /fr/
            {"langs": []},                                                   # 3 no language at all -> English, stays
            {"langs": ["it", "de-AT", "en"]},                                # 4 first SUPPORTED match (it is not) -> /de/
            {"langs": ["zh-TW"]},                                            # 5 -> /zh-Hant/
            {"langs": ["pt-BR"]},                                            # 6 -> /pt-BR/
            {"langs": ["ko"], "stored": {"still_lang": "en"}},               # 7 stored choice beats the browser: English stays
            {"langs": ["en"], "stored": {"still_lang": "ja"}},               # 8 stored ja beats an English browser -> /ja/
            {"langs": ["ko"], "stored": {"still_lang": "xx"}},               # 9 junk stored value is ignored -> browser -> /ko/
            {"langs": ["ko"], "search": "?lang=de", "stored": {"still_lang": "ja"}},  # 10 URL beats stored and browser -> /de/, and is remembered
            {"langs": ["en"], "search": "?lang=en"},                         # 11 explicit URL English -> /en/
            {"langs": ["ko"], "search": "?lang=zz"},                         # 12 unknown ?lang is ignored -> browser -> /ko/
            {"langs": ["ko"], "search": "?utm_source=a&lang=es", "hash": "#faq"},  # 13 other query and hash survive; lang is dropped
            {"langs": ["vi"]},                                               # 14 vi has a home page -> /vi/
            {"langs": ["ar-EG", "en"]},                                      # 15 ar ended: never matched -> stays
            {"langs": ["hi-IN"]},                                            # 16 hi ended -> stays
            {"langs": ["zh-CN", "ko"]},                                      # 17 zh-CN unsupported -> next candidate -> /ko/
            {"langs": ["zh-Hans-CN"]},                                       # 18 simplified: unsupported -> stays
            {"langs": ["zh"]},                                               # 19 bare zh: unsupported -> stays
            {"langs": ["zh-HK"]},                                            # 20 -> /zh-Hant/
            {"langs": ["zh-Hant-TW"]},                                       # 21 -> /zh-Hant/
            {"langs": ["pt-PT"]},                                            # 22 pt* -> /pt-BR/
            {"langs": ["pt"]},                                               # 23 -> /pt-BR/
            {"langs": ["in"]},                                               # 24 in -> /id/
            {"langs": ["th-TH"]},                                            # 25 -> /th/
            {"langs": ["tr"]},                                               # 26 -> /tr/
            {"langs": ["ru", "de"]},                                         # 27 ru ended -> next -> /de/
            {"langs": ["en"], "stored": {"still_lang": "pt"}},               # 28 stored old pt -> /pt-BR/
            {"langs": ["en"], "stored": {"still_lang": "ru"}},               # 29 stored ended language is ignored -> browser en -> stays
            {"langs": ["ko"], "search": "?lang=zh-TW"},                      # 30 URL zh-TW -> /zh-Hant/
            {"langs": ["ko"], "search": "?lang=ar"},                         # 31 URL ended language ignored -> browser -> /ko/
            {"langs": ["ko"], "search": "?lang=pt"},                         # 32 URL pt -> /pt-BR/ (and remembered as pt-BR)
        ]
        r = subprocess.run([node, "-e", harness, json.dumps(cases)], input=self.root_script(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = [c["to"] for c in json.loads(r.stdout)]
        self.assertEqual(got, ["/ko/", None, "/fr/", None, "/de/", "/zh-Hant/", "/pt-BR/", None, "/ja/", "/ko/", "/de/", "/en/", "/ko/",
                               "/es/?utm_source=a#faq", "/vi/", None, None, "/ko/", None, None, "/zh-Hant/", "/zh-Hant/", "/pt-BR/", "/pt-BR/",
                               "/id/", "/th/", "/tr/", "/de/", "/pt-BR/", None, "/zh-Hant/", "/ko/", "/pt-BR/"])
        self.assertEqual(json.loads(r.stdout)[10]["store"]["still_lang"], "de")
        self.assertEqual(json.loads(r.stdout)[32]["store"]["still_lang"], "pt-BR")

    def test_no_language_is_right_to_left(self):
        # ar (the only RTL language) is ended: the 12 languages are all LTR, in the built pages and in the committed home/FAQ/about
        for l in LANGS:
            self.assertIn('dir="ltr"', self.page(l)[:200], l)
            self.assertNotIn('dir="rtl"', self.page(l), l)
            for p in ("", "faq/", "about/"):
                self.assertIn('<html lang="%s" dir="ltr">' % l, (REPO / l / p / "index.html").read_text(encoding="utf-8"), (l, p))

    def test_new_languages_link_every_language_in_the_sitemap(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        rows = {u.find("s:loc", NS).text: u for u in root.findall("s:url", NS)}
        for l in ("th", "tr", "zh-Hant", "pt-BR"):
            for p in ("", "faq/", "about/"):
                u = rows["https://still.ipe.rest/%s/%s" % (l, p)]
                got = {x.get("hreflang"): x.get("href") for x in u.findall("x:link", NS)}
                self.assertEqual(set(got), set(LANGS) | {"x-default"}, (l, p))
                for x in LANGS:
                    self.assertEqual(got[x], "https://still.ipe.rest/%s/%s" % (x, p), (l, p, x))
        # and every language page points to them (the sitemap rows carry no ended language, no old /pt/)
        for l in LANGS:
            h = self.page(l)
            for x in ("th", "tr", "zh-Hant", "pt-BR"):
                self.assertIn('hreflang="%s" href="https://still.ipe.rest/%s/"' % (x, x), h, l)
        for loc in rows:
            for dead in ENDED + ["pt"]:
                self.assertFalse(loc.startswith("https://still.ipe.rest/%s/" % dead), loc)

    def test_ended_languages_are_not_rebuilt(self):
        # the test copy only has content/home: nothing for zh ru ar hi is created (frozen folders are left alone)
        for e in ENDED:
            self.assertFalse((self.tmp / e).exists(), e)
        sm = (self.tmp / "sitemap.xml").read_text(encoding="utf-8")
        llms = (self.tmp / "llms.txt").read_text(encoding="utf-8")
        for e in ENDED + ["pt"]:
            self.assertNotIn("https://still.ipe.rest/%s/" % e, sm, e)
            self.assertNotIn("https://still.ipe.rest/%s/" % e, llms, e)
            self.assertNotIn('hreflang="%s"' % e, sm, e)

    def test_old_pt_home_is_a_redirect_stub(self):
        h = self.page("pt")
        self.assertIn("generated by scripts/build_journal.py", h)  # GEN_MARK: the generator owns (and may refresh) the stub
        self.assertIn('<link rel="canonical" href="https://still.ipe.rest/pt-BR/">', h)
        self.assertIn('http-equiv="refresh" content="0; url=https://still.ipe.rest/pt-BR/"', h)
        self.assertIn("noindex", h)
        self.assertNotIn("hreflang", h)
        self.assertNotIn("<select", h)
        self.assertNotIn("https://still.ipe.rest/pt/", (self.tmp / "sitemap.xml").read_text(encoding="utf-8"))

    def test_new_pages_carry_ga4_and_the_ipe_rest_link_keeps_the_language(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from site_common import CONSENT_V, GA_SNIPPET, ipe_rest_url
        for l in ("th", "tr", "zh-Hant", "pt-BR"):
            h = self.page(l)
            self.assertIn(GA_SNIPPET, h, l)
            self.assertIn('<script src="/assets/consent.js?v=%s" defer></script>' % CONSENT_V, h.split("</head>")[0], l)
            for p in ("faq", "about"):  # the FAQ/about "(https://ipe.rest)" links go to the studio hub in the page's own language
                info = (REPO / l / p / "index.html").read_text(encoding="utf-8")
                self.assertIn('href="%s"' % ipe_rest_url(l), info, (l, p))
                self.assertNotIn('href="https://ipe.rest"', info, (l, p))
        self.assertEqual(ipe_rest_url("pt-BR"), "https://ipe.rest/pt/")  # the hub's folder for Brazilian Portuguese is still /pt/
        self.assertEqual(ipe_rest_url("th"), "https://ipe.rest/?lang=th")

    def test_accessibility_labels_and_structured_data_follow_the_language(self):
        strings = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
        for l in LANGS:
            h = self.page(l)
            for k in ("aria_lang", "aria_verse_card", "aria_save", "aria_listen", "aria_email", "aria_footer", "og_image_alt"):
                self.assertTrue(strings[l].get(k), "%s lacks %s" % (l, k))
            for k in ("aria_lang", "aria_verse_card", "aria_save", "aria_listen", "aria_email", "aria_footer"):
                self.assertIn('aria-label="%s"' % html.escape(strings[l][k]), h, "%s %s" % (l, k))
            self.assertIn('<meta property="og:image:alt" content="%s">' % html.escape(strings[l]["og_image_alt"]), h, l)
            ld = json.loads(re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', h, re.S).group(1))
            app = ld["@graph"][0]
            orgs = [n for n in ld["@graph"] if n.get("@type") == "Organization"]
            self.assertEqual([o.get("@id") for o in orgs], ["https://ipe.rest/#organization"], l)  # the ipe.rest hub, not an anonymous copy
            for n in ld["@graph"]:  # ...and every publisher in the graph refers to it
                if "publisher" in n:
                    self.assertEqual(n["publisher"], {"@id": "https://ipe.rest/#organization"}, (l, n["@type"]))
            self.assertEqual(app["inLanguage"], l)
            self.assertEqual(app["description"], strings[l].get("ld_desc") or strings[l]["meta_desc"], l)
            if l != "en":
                for english in ("Language", "Footer", "Email address", "Save this verse", "Example verse card", "Listen with calm music"):
                    self.assertNotIn('aria-label="%s"' % english, h, "%s still has English %r" % (l, english))
                self.assertNotIn("A private, on-device AI companion", h, l)

    def test_language_switch_is_plain_links_too(self):
        for l in [None] + LANGS:
            h = self.page(l)
            self.assertEqual(len(re.findall(r'<select id="foot-lang"', h)), 1, l)
            self.assertIn('<label class="foot-langsel">', h, l)
            nav = re.search(r'<noscript><nav class="foot-langs".*?</nav></noscript>', h, re.S).group(0)
            self.assertEqual(re.findall(r'<a href="/([\w-]+)/" hreflang="\1" lang="\1"', nav), LANGS, l)
            self.assertEqual(re.findall(r'<a href="/([\w-]+)/"[^>]*aria-current', nav), [l] if l else [], l)

    def test_sitemap_has_home_in_every_language(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        rows = {u.find("s:loc", NS).text: u for u in root.findall("s:url", NS) if "/journal/" not in u.find("s:loc", NS).text and u.find("x:link", NS) is not None and u.find("{http://www.google.com/schemas/sitemap-image/1.1}image") is not None}  # home rows (info pages have alternates but no image, legal pages neither)
        self.assertEqual(len(rows), 13)  # "/" + 12 languages
        for loc, u in rows.items():
            self.assertEqual(len(u.findall("x:link", NS)), 13, loc)  # 12 languages + x-default
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
            self.assertNotIn("data-journal-top", h, l)
            self.assertNotIn('class="topnav"', h, l)  # the top-bar Journal link goes too (the .topnav CSS may stay)
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
        self.assertIn('<a class="topnav" href="/journal/ko/" data-i18n="foot_journal">저널</a>', shown)
        self.assertNotIn("data-journal-link", shown)
        self.assertNotIn("data-journal-top", shown)
        hub = build_home.render_page(tpl, strings, "en", False, "", "/journal/", True)  # a language without posts still links the hub once any post exists
        self.assertIn('<a class="topnav" href="/journal/" data-i18n="foot_journal">Journal</a>', hub)
        self.assertNotIn(" hidden>", re.search(r'<section class="journal"[^>]*>', shown).group(0))
        gone = build_home.render_page(tpl, strings, "ko", False, "", "/journal/ko/")
        self.assertNotIn("저널</a>", gone)
        self.assertNotIn('class="topnav"', gone)
        self.assertIn("개인정보</a>", gone)  # the other footer links stay

    def test_sitemap_lists_legal_pages(self):
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        locs = {u.find("s:loc", NS).text for u in root.findall("s:url", NS) if "/journal/" not in u.find("s:loc", NS).text}
        self.assertEqual(len(locs), 39)  # 13 home + 24 faq/about + privacy + terms
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
        self.assertEqual(set(ex), {"/.git", "/.github", "/content", "/scripts", "/tests", "/vendor"})

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
