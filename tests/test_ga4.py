"""GA4 (G-XG4BH800J0, the ipe.rest property): the snippet comes from ONE constant and lands in the <head> of every page — generated pages
(home x11, faq/about x11, journal hub/lists/posts incl. posts that publish later) and the hand-written ones (privacy, terms, 404) — and the privacy
policy / FAQ / llms.txt say what the site really does, the app and the website kept apart. Run: python3 -m unittest discover -s tests"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import site_common as sc  # noqa: E402
from test_build_journal import REPO, Base, run, write_post  # noqa: E402
from test_journal_paging import put  # noqa: E402

GA_ID = "G-XG4BH800J0"
SKIP_DIRS = {".git", ".github", "content", "scripts", "tests", "node_modules", "assets"}


def served_html(root):
    """every .html the site serves (build-only folders and the assets folder are not pages)"""
    root = Path(root)
    return sorted(p for p in root.rglob("*.html") if not (set(p.relative_to(root).parts[:-1]) & SKIP_DIRS))


def head_of(text):
    return text[text.index("<head"):text.index("</head>")]


def check_snippet(case, root):
    pages = served_html(root)
    case.assertGreater(len(pages), 3)
    for p in pages:
        text = p.read_text(encoding="utf-8")
        with case.subTest(str(p.relative_to(root))):
            case.assertEqual(text.count("googletagmanager.com/gtag/js"), 1)
            case.assertEqual(text.count(GA_ID), 1)
            case.assertIn(sc.GA_SNIPPET, head_of(text))  # in <head>, byte for byte the constant
    return pages


class Census(unittest.TestCase):
    """an independent head-count over EVERY .html in the tree (no skip list beyond .git): the measurement id appears exactly once in each,
    the only .html without it is the build-only home template (it carries the {{GA_SNIPPET}} placeholder), and no other property / tag tool exists"""
    BUILD_ONLY = {"content/home/template.html"}
    OTHER_TAGS = re.compile(r"G-[A-Z0-9]{8,12}|UA-\d{4,}-\d+|GTM-[A-Z0-9]+|AW-\d{6,}|fbq\(|connect\.facebook\.net|hotjar|clarity\.ms")

    def test_every_html_has_the_measurement_id_exactly_once(self):
        counts = {}
        for p in REPO.rglob("*.html"):
            if ".git" in p.relative_to(REPO).parts:
                continue
            counts[str(p.relative_to(REPO))] = p.read_text(encoding="utf-8").count(GA_ID)
        self.assertGreater(len(counts), 60)
        self.assertEqual({r for r, n in counts.items() if n == 0}, self.BUILD_ONLY)
        self.assertEqual({r: n for r, n in counts.items() if n > 1}, {})

    def test_no_other_property_or_tracker(self):
        for p in REPO.rglob("*.html"):
            rel = str(p.relative_to(REPO))
            if ".git" in p.relative_to(REPO).parts:
                continue
            with self.subTest(rel):
                self.assertEqual(set(self.OTHER_TAGS.findall(p.read_text(encoding="utf-8"))) - {GA_ID}, set())


class Constant(unittest.TestCase):
    def test_constant_is_the_ipe_rest_property(self):
        self.assertEqual(sc.GA_MEASUREMENT_ID, GA_ID)
        self.assertEqual(sc.GA_SNIPPET.count(GA_ID), 1)

    def test_snippet_is_inline_async_and_idle_on_localhost(self):
        s = sc.GA_SNIPPET
        self.assertTrue(s.startswith("<script>") and s.endswith("</script>"))
        self.assertEqual(s.count("<script"), 1)
        self.assertIn("s.async=true", s)
        self.assertIn("'outbound_click'", s)
        self.assertIn("127", s)  # a local preview does not count as a visit
        self.assertNotIn("select_game", s)  # play.ipe.rest only

    def test_every_hand_written_page_is_listed(self):
        """a new hand-written .html page must be added to STATIC_PAGES (or be generated) — otherwise it would ship without GA4"""
        generated = re.compile(r"^(index\.html|[a-z]{2}/(index|faq/index|about/index)\.html|journal/.*)$")
        hand_written = {str(p.relative_to(REPO)) for p in served_html(REPO) if not generated.match(str(p.relative_to(REPO)))}
        self.assertEqual(hand_written, set(sc.STATIC_PAGES))


class CommittedSite(unittest.TestCase):
    def test_every_committed_page_has_the_snippet_once(self):
        pages = check_snippet(self, REPO)
        self.assertGreater(len(pages), 60)

    def test_404_and_legal_pages(self):
        for rel in sc.STATIC_PAGES:
            text = (REPO / rel).read_text(encoding="utf-8")
            with self.subTest(rel):
                self.assertEqual(text.count(sc.GA_START), 1)
                self.assertEqual(text.count(sc.GA_END), 1)
                self.assertEqual(text.count("</head>"), 1)
                self.assertLess(text.index(sc.GA_START), text.index("</head>"))

    def test_sync_is_idempotent_and_repairs_a_hand_edit(self):
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            for rel in sc.STATIC_PAGES:
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(REPO / rel, tmp / rel)
            before = {rel: (tmp / rel).read_text(encoding="utf-8") for rel in sc.STATIC_PAGES}
            sc.sync_static_ga(tmp)
            self.assertEqual(before, {rel: (tmp / rel).read_text(encoding="utf-8") for rel in sc.STATIC_PAGES})
            page = tmp / "404.html"
            page.write_text(before["404.html"].replace(GA_ID, "G-WRONG"), encoding="utf-8")
            sc.sync_static_ga(tmp)
            self.assertEqual(page.read_text(encoding="utf-8"), before["404.html"])
            page.write_text(before["404.html"].replace(sc.GA_END, ""), encoding="utf-8")  # broken markers: refuse, do not guess
            with self.assertRaises(SystemExit):
                sc.sync_static_ga(tmp)
        finally:
            shutil.rmtree(tmp, True)


class GeneratorOutput(Base):
    """the journal generator (hub, lists, posts — a scheduled post once it publishes — and the home / faq / about it also builds)"""

    def test_fixture_build_puts_the_snippet_into_every_page(self):
        for l in sc.LANGS:
            write_post(self.tmp, l)
        put(self.tmp, "ko", "later", "2026-10-30", "publish_at: 2026-10-30 10:06\n")
        r = run(self.tmp, "--now", "2026-10-30 10:06")
        self.assertEqual(r.returncode, 0, r.stderr)
        pages = check_snippet(self, self.tmp)
        rels = {str(p.relative_to(self.tmp)) for p in pages}
        for need in ("index.html", "ko/index.html", "en/index.html", "ko/faq/index.html", "ko/about/index.html", "journal/index.html",
                     "journal/ko/index.html", "journal/en/hello/index.html", "journal/ko/later/index.html", "404.html", "privacy/index.html"):
            self.assertIn(need, rels)
        self.assertGreaterEqual(len(rels), 11 * 3 + 12)

    def test_scheduled_post_before_its_time_is_not_published(self):
        write_post(self.tmp, "ko")
        put(self.tmp, "ko", "later", "2026-10-30", "publish_at: 2026-10-30 10:06\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertFalse((self.tmp / "journal/ko/later").exists())
        check_snippet(self, self.tmp)

    def test_snippet_sits_after_the_stylesheet_and_before_the_body(self):
        write_post(self.tmp, "en")
        self.assertEqual(run(self.tmp).returncode, 0)
        h = self.page("journal/en/hello/index.html")
        self.assertLess(h.index("journal.css"), h.index(GA_ID))
        self.assertLess(h.index(GA_ID), h.index("<body"))


class Texts(unittest.TestCase):
    """what the pages say must match what the site does"""
    # ("The App contains no analytics or tracking SDKs" stays true and stays — the stale claims are the ones about the website)
    stale = re.compile(r"website[^.]{0,40}no (analytics|tracking|cookies)|cookieless analytics that do not track|we collect no personal data\. Not through|"
                       r"쿠키 없는 분석만|쿠키리스·개인정보 미수집·핑거프린팅|our only third-party service", re.I)

    def test_faq_answer_names_google_analytics_in_every_language(self):
        d = json.loads((REPO / "content/info/pages.json").read_text(encoding="utf-8"))
        for l in sc.LANGS:
            answer = d[l]["faq"][2][1]
            with self.subTest(l):
                self.assertIn("Google Analytics", answer)
                self.assertIn("Cloudflare", answer)
                self.assertIn("(/privacy/)", answer)
                self.assertNotRegex(answer, self.stale)

    def test_privacy_policy_keeps_app_and_website_apart(self):
        text = (REPO / "privacy/index.html").read_text(encoding="utf-8")
        for lang in ("en", "ko"):
            m = re.search(r'<div data-lang-block="%s"[^>]*>(.*?)\n    </div>' % lang, text, re.S)
            block = m.group(1)
            heads = re.findall(r"<h2>(.*?)</h2>", block)
            with self.subTest(lang):
                self.assertEqual(len(heads), 14)
                self.assertEqual([int(h.split(".")[0]) for h in heads], list(range(1, 15)))
                sec = {1: heads[0], 2: heads[1]}
                self.assertIn("still.ipe.rest", sec[2])
                self.assertIn("2026-11-01", block.split("</p>")[0])  # effective date, no placeholder
                self.assertNotIn("to be published", block)
                self.assertNotIn("게시 예정", block)
                two = block[block.index("<h2>2."):block.index("<h2>3.")]
                for word in ("Google Analytics 4", "_ga", "Cloudflare Web Analytics", "tools.google.com/dlpage/gaoptout", "GitHub"):
                    self.assertIn(word, two)
                one = block[block.index("<h2>1."):block.index("<h2>2.")]
                self.assertNotIn("Google", one)  # the app section says nothing about the website's tools
                self.assertNotRegex(block, self.stale)

    def test_privacy_meta_matches(self):
        text = (REPO / "privacy/index.html").read_text(encoding="utf-8")
        for pat in (r'<meta name="description" content="(.*?)">', r'<meta property="og:description" content="(.*?)">',
                    r'<meta name="twitter:description" content="(.*?)">'):
            d = re.search(pat, text).group(1)
            self.assertIn("Google Analytics", d)
            self.assertLessEqual(len(d), 160)

    def test_privacy_sitemap_lastmod_is_the_revision_date(self):
        sm = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        self.assertRegex(sm, r"<loc>https://still\.ipe\.rest/privacy/</loc>\s*<lastmod>2026-11-01</lastmod>")

    def test_llms_txt_says_so(self):
        t = (REPO / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("Google Analytics", t)
        self.assertIn("the app collects nothing", t)

    def test_home_template_has_the_placeholder(self):
        t = (REPO / "content/home/template.html").read_text(encoding="utf-8")
        self.assertEqual(t.count("{{GA_SNIPPET}}"), 1)
        self.assertLess(t.index("{{GA_SNIPPET}}"), t.index("</head>"))
        self.assertNotIn(GA_ID, t)  # the id lives in one place only


if __name__ == "__main__":
    unittest.main()
