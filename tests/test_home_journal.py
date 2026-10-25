"""home journal cards: right under the hero, <= 3 cards, one <a> per card (whole card clickable), per-language posts, grid 1/2/3 columns, auto-refresh on publish"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
from site_common import LANGS  # noqa: E402
from test_build_journal import POST, Base, run, write_post  # noqa: E402

PAGES = [("en", REPO / "index.html")] + [(l, REPO / l / "index.html") for l in LANGS]  # root (x-default, English) + 11 languages
SECTION = re.compile(r'<section class="journal"[^>]*>.*?</section>', re.S)
CARD = re.compile(r'<a class="j-card"[^>]*>.*?</a>', re.S)
TEMPLATE = (REPO / "content/home/template.html").read_text(encoding="utf-8")


def section(h):
    m = SECTION.search(h)
    return m.group(0) if m else None


def list_exists(lang):
    return (REPO / "journal" / lang / "index.html").is_file()


class CommittedPages(unittest.TestCase):
    def pages(self):
        self.assertEqual(len(PAGES), 12)
        for lang, f in PAGES:
            yield lang, f, f.read_text(encoding="utf-8")

    def test_section_comes_right_after_the_hero(self):
        for lang, f, h in self.pages():
            i_hero, i_end = h.index('<header class="hero'), h.index("</header>")
            i_sec = h.index('<section class="journal"')
            sections = [m.start() for m in re.finditer(r"<section\b", h)]
            self.assertLess(i_end, i_sec, f)
            self.assertEqual(h[i_end:i_sec].count("<section"), 0, f)  # no other section between the hero and the journal
            self.assertEqual(sections[0], i_sec, f)  # it is the first section of the page
            self.assertLess(i_sec, h.index('<section class="heart">'), f)
            self.assertLess(i_hero, i_end, f)

    def test_at_most_three_cards_each_one_link(self):
        for lang, f, h in self.pages():
            s = section(h)
            self.assertIsNotNone(s, f)
            self.assertNotIn(" hidden", re.match(r"<section[^>]*>", s).group(0), f)  # posts exist -> shown
            cards = CARD.findall(s)
            self.assertTrue(1 <= len(cards) <= 3, (f, len(cards)))
            self.assertEqual(s.count('class="j-card"'), len(cards), f)
            self.assertEqual(s.count("<article"), 0, f)
            for c in cards:
                self.assertEqual(c.count("<a "), 1, (f, "the card is ONE <a>: no nested links"))
                self.assertEqual(len(re.findall(r'href="', c)), 1, f)
                self.assertRegex(c, r'<p class="j-date"><time datetime="[^"]+"[^>]*>[^<]+</time></p>')  # date (KST) in a <time>
                self.assertRegex(c, r'<h3 class="j-title">[^<]+</h3>')
                self.assertRegex(c, r'<p class="j-desc">[^<]+</p>')  # the summary, clamped to 2 lines by CSS
                self.assertIn('class="j-more"', c)
            self.assertIn('class="journal-grid j-n%d"' % len(cards), s, f)

    def test_cards_are_that_languages_posts(self):
        # a language with its own posts shows only those; one without (no translation yet) shows the original posts (en, else ko) — never a mix
        for lang, f, h in self.pages():
            cards = CARD.findall(section(h))
            langs = {re.search(r'lang="([^"]+)"', c).group(1) for c in cards}
            self.assertEqual(len(langs), 1, (f, langs))
            card_lang = langs.pop()
            own = [p for p in (REPO / "journal" / lang).glob("*/index.html")] if list_exists(lang) else []
            if own:
                self.assertEqual(card_lang, lang, f)
            for c in cards:
                href = re.search(r'href="([^"]+)"', c).group(1)
                self.assertRegex(href, r"^/journal/%s/[a-z0-9-]+/$" % card_lang, f)
                self.assertTrue((REPO / href.strip("/") / "index.html").is_file(), href)

    def test_all_link_goes_to_that_languages_list(self):
        for lang, f, h in self.pages():
            s = section(h)
            alls = re.findall(r'<p class="journal-all"><a class="more-link" href="([^"]+)">', s)
            self.assertEqual(len(alls), 1, f)
            self.assertEqual(alls[0], "/journal/%s/" % lang if list_exists(lang) else "/journal/", f)  # no list in that language yet -> the hub
            self.assertTrue((REPO / alls[0].strip("/") / "index.html").is_file(), f)

    def test_no_script_in_the_section(self):
        for lang, f, h in self.pages():
            self.assertNotIn("<script", section(h), f)  # static: nothing to allow if a CSP ever arrives


class Template(unittest.TestCase):
    def test_columns_1_2_3_by_media_query(self):
        css = TEMPLATE[TEMPLATE.index("1.5 JOURNAL"):TEMPLATE.index("/* ---------- 7. CTA")]
        self.assertNotIn("auto-fit", css)
        self.assertRegex(css, r"\.journal-grid\{display:grid;grid-template-columns:1fr;")  # base: 1 column (320/375)
        self.assertRegex(css, r"@media \(min-width:640px\)\{\s*\.journal-grid\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)")  # 768: 2 columns
        self.assertRegex(css, r"@media \(min-width:1024px\)\{\s*\.journal-grid\.j-n3\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)")  # 1280: 3 columns
        self.assertIn("-webkit-line-clamp:2", css)  # summary: 1-2 lines

    def test_hero_comes_first_and_is_untouched_by_the_journal(self):
        self.assertLess(TEMPLATE.index('<header class="hero dark">'), TEMPLATE.index('<section class="journal"'))
        self.assertLess(TEMPLATE.index('<section class="journal"'), TEMPLATE.index('<section class="heart">'))


class Generated(Base):
    """cards follow the posts: 0 -> hidden · 1/2 -> that many (no empty card) · >3 -> newest 3 · a newly due post appears via --now"""

    def post(self, slug, date, lang="ko", extra="bible_version: WEB\n"):
        write_post(self.tmp, lang, slug, text=POST.replace("slug: hello", "slug: " + slug).replace("2026-10-22", date) % dict(l=lang, extra=extra))

    def home(self, lang="ko"):
        return self.page("%s/index.html" % lang)

    def test_zero_posts_hide_the_section(self):
        self.assertEqual(run(self.tmp).returncode, 0)
        for f in ("index.html", "ko/index.html", "ja/index.html"):
            s = section(self.page(f))
            self.assertIn(" hidden", re.match(r"<section[^>]*>", s).group(0), f)
            self.assertEqual(CARD.findall(s), [], f)

    def test_one_two_and_many_posts(self):
        for n, want in ((1, 1), (2, 2), (5, 3)):
            for i in range(n):
                self.post("p%d" % i, "2026-10-%02d" % (10 + i))
            self.assertEqual(run(self.tmp).returncode, 0)
            cards = CARD.findall(section(self.home()))
            self.assertEqual(len(cards), want, n)
            self.assertIn('class="journal-grid j-n%d"' % want, self.home())
            self.assertEqual([re.search(r'href="([^"]+)"', c).group(1) for c in cards],
                             ["/journal/ko/p%d/" % i for i in range(n - 1, n - 1 - want, -1)])  # newest first
            for c in cards:
                self.assertNotIn("<article", c)

    def test_a_due_post_appears_on_every_home_via_now_and_not_in_the_committed_build(self):
        self.post("old", "2026-10-20")
        self.post("sched", "2026-10-26", extra="bible_version: WEB\npublish_at: 2026-10-26 09:08\n")
        self.assertEqual(run(self.tmp).returncode, 0)  # committed (clock-free) build
        self.assertNotIn("/journal/ko/sched/", self.home())
        self.assertEqual(len(CARD.findall(section(self.home()))), 1)
        self.assertEqual(run(self.tmp, "--now", "2026-10-26 09:08").returncode, 0)  # the deploy runner's path
        for f in ("index.html", "ko/index.html", "ja/index.html", "en/index.html"):  # every home page (languages without posts show the originals)
            cards = CARD.findall(section(self.page(f)))
            self.assertEqual(len(cards), 2, f)
            self.assertIn('href="/journal/ko/sched/"', cards[0], f)  # newest first
            self.assertIn('data-ipe-time>2026년 10월 26일&nbsp;09:08 KST</time>', cards[0], f)

    def test_own_language_posts_win_over_the_originals(self):
        self.post("orig", "2026-10-20")
        self.post("orig", "2026-10-20", lang="ja", extra="bible_version: WEB\ntranslation_of: ko\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        ja = CARD.findall(section(self.home("ja")))
        self.assertEqual(len(ja), 1)
        self.assertIn('href="/journal/ja/orig/"', ja[0])
        self.assertIn('lang="ja"', ja[0])
        self.assertIn('href="/journal/ko/orig/"', CARD.findall(section(self.home("fr")))[0])  # fr has no post yet -> the original
        self.assertIn('<a class="more-link" href="/journal/ja/">', section(self.home("ja")))


if __name__ == "__main__":
    unittest.main()
