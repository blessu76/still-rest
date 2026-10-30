"""home journal cards: right under the hero, <= 3 cards, one <a> per card (whole card clickable), per-language posts, grid 1/2/3 columns, auto-refresh on publish"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
from site_common import LANGS  # noqa: E402
import build_journal as bj  # noqa: E402
from test_build_journal import POST, VERSES, Base, run, write_post  # noqa: E402  (VERSES: the app's verse file, see find_verses())

PAGES = [("en", REPO / "index.html")] + [(l, REPO / l / "index.html") for l in LANGS]  # root (x-default, English) + 11 languages
SECTION = re.compile(r'<section class="journal"[^>]*>.*?</section>', re.S)
CARD = re.compile(r'<a class="j-card"[^>]*>.*?</a>', re.S)
# slug -> the reference its verse chip must show. Written by hand from the articles' quotation blocks and checked against the app's verse file.
PINNED = {
    "commute-get-off-early": "이사야 41:10",
    "evening-after-the-meeting": "마태복음 11:28",
    "first-day-at-the-clinic": "예레미야애가 3:23",
    "three-am-counting-hours": "시편 4:8",
    "unanswered-message-three-days": "시편 46:10",
    "sunday-afternoon-caring-for-mother": "시편 121:2",
    "monday-morning-list-of-the-week": "베드로전서 5:7",
    "monday-afternoon-ten-minutes-outside": "시편 23:2",
    "tuesday-morning-one-tab-at-a-time": "이사야 26:3",
    "tuesday-evening-dark-before-six": "시편 34:18",
    "wednesday-morning-coat-pocket-note": "빌립보서 4:6",
    "wednesday-evening-winter-blanket": "마태복음 11:29",
    "thursday-morning-second-alarm": "이사야 40:31",
    "thursday-evening-earbuds-ran-out": "요한복음 14:27",
    "friday-morning-umbrella-in-the-bag": "시편 55:22",
    "friday-evening-ninety-seconds-microwave": "출애굽기 14:14",
    "saturday-morning-laundry-after-sleeping-in": "빌립보서 4:13",
    "saturday-evening-grocery-bags-by-the-door": "예레미야애가 3:22",
    "sunday-morning-bicycle-on-the-balcony": "여호수아 1:9",
    "sunday-afternoon-words-from-last-week": "시편 147:3",
}
# slug -> the reference the verse chip of each translation must show. Written by hand (book name of that language, chapter:verse OF THAT
# LANGUAGE'S BIBLE: Synodal and Louis Segond number some psalms differently) — not generated from scripture.json, so the two check each other.
PINNED_I18N = {
    "en": {"commute-get-off-early": "Isaiah 41:10", "evening-after-the-meeting": "Matthew 11:28", "first-day-at-the-clinic": "Lamentations 3:23",
           "three-am-counting-hours": "Psalm 4:8", "unanswered-message-three-days": "Psalm 46:10", "sunday-afternoon-caring-for-mother": "Psalm 121:2",
           "monday-morning-list-of-the-week": "1 Peter 5:7", "monday-afternoon-ten-minutes-outside": "Psalm 23:2",
           "tuesday-morning-one-tab-at-a-time": "Isaiah 26:3", "tuesday-evening-dark-before-six": "Psalm 34:18",
           "wednesday-morning-coat-pocket-note": "Philippians 4:6", "wednesday-evening-winter-blanket": "Matthew 11:29",
           "thursday-morning-second-alarm": "Isaiah 40:31", "thursday-evening-earbuds-ran-out": "John 14:27",
           "friday-morning-umbrella-in-the-bag": "Psalm 55:22", "friday-evening-ninety-seconds-microwave": "Exodus 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Philippians 4:13", "saturday-evening-grocery-bags-by-the-door": "Lamentations 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Joshua 1:9", "sunday-afternoon-words-from-last-week": "Psalm 147:3"},
    "ja": {"commute-get-off-early": "イザヤ書 41:10", "evening-after-the-meeting": "マタイによる福音書 11:28", "first-day-at-the-clinic": "哀歌 3:23",
           "three-am-counting-hours": "詩篇 4:8", "unanswered-message-three-days": "詩篇 46:10", "sunday-afternoon-caring-for-mother": "詩篇 121:2",
           "monday-morning-list-of-the-week": "ペテロの第一の手紙 5:7", "monday-afternoon-ten-minutes-outside": "詩篇 23:2",
           "tuesday-morning-one-tab-at-a-time": "イザヤ書 26:3", "tuesday-evening-dark-before-six": "詩篇 34:18",
           "wednesday-morning-coat-pocket-note": "ピリピ人への手紙 4:6", "wednesday-evening-winter-blanket": "マタイによる福音書 11:29",
           "thursday-morning-second-alarm": "イザヤ書 40:31", "thursday-evening-earbuds-ran-out": "ヨハネによる福音書 14:27",
           "friday-morning-umbrella-in-the-bag": "詩篇 55:22", "friday-evening-ninety-seconds-microwave": "出エジプト記 14:14",
           "saturday-morning-laundry-after-sleeping-in": "ピリピ人への手紙 4:13", "saturday-evening-grocery-bags-by-the-door": "哀歌 3:22",
           "sunday-morning-bicycle-on-the-balcony": "ヨシュア記 1:9", "sunday-afternoon-words-from-last-week": "詩篇 147:3"},
    "zh": {"commute-get-off-early": "以赛亚书 41:10", "evening-after-the-meeting": "马太福音 11:28", "first-day-at-the-clinic": "耶利米哀歌 3:23",
           "three-am-counting-hours": "诗篇 4:8", "unanswered-message-three-days": "诗篇 46:10", "sunday-afternoon-caring-for-mother": "诗篇 121:2",
           "monday-morning-list-of-the-week": "彼得前书 5:7", "monday-afternoon-ten-minutes-outside": "诗篇 23:2",
           "tuesday-morning-one-tab-at-a-time": "以赛亚书 26:3", "tuesday-evening-dark-before-six": "诗篇 34:18",
           "wednesday-morning-coat-pocket-note": "腓立比书 4:6", "wednesday-evening-winter-blanket": "马太福音 11:29",
           "thursday-morning-second-alarm": "以赛亚书 40:31", "thursday-evening-earbuds-ran-out": "约翰福音 14:27",
           "friday-morning-umbrella-in-the-bag": "诗篇 55:22", "friday-evening-ninety-seconds-microwave": "出埃及记 14:14",
           "saturday-morning-laundry-after-sleeping-in": "腓立比书 4:13", "saturday-evening-grocery-bags-by-the-door": "耶利米哀歌 3:22",
           "sunday-morning-bicycle-on-the-balcony": "约书亚记 1:9", "sunday-afternoon-words-from-last-week": "诗篇 147:3"},
    "es": {"commute-get-off-early": "Isaías 41:10", "evening-after-the-meeting": "Mateo 11:28", "first-day-at-the-clinic": "Lamentaciones 3:23",
           "three-am-counting-hours": "Salmos 4:8", "unanswered-message-three-days": "Salmos 46:10", "sunday-afternoon-caring-for-mother": "Salmos 121:2",
           "monday-morning-list-of-the-week": "1 Pedro 5:7", "monday-afternoon-ten-minutes-outside": "Salmos 23:2",
           "tuesday-morning-one-tab-at-a-time": "Isaías 26:3", "tuesday-evening-dark-before-six": "Salmos 34:18",
           "wednesday-morning-coat-pocket-note": "Filipenses 4:6", "wednesday-evening-winter-blanket": "Mateo 11:29",
           "thursday-morning-second-alarm": "Isaías 40:31", "thursday-evening-earbuds-ran-out": "Juan 14:27",
           "friday-morning-umbrella-in-the-bag": "Salmos 55:22", "friday-evening-ninety-seconds-microwave": "Éxodo 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Filipenses 4:13", "saturday-evening-grocery-bags-by-the-door": "Lamentaciones 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Josué 1:9", "sunday-afternoon-words-from-last-week": "Salmos 147:3"},
    "pt": {"commute-get-off-early": "Isaías 41:10", "evening-after-the-meeting": "Mateus 11:28", "first-day-at-the-clinic": "Lamentações 3:23",
           "three-am-counting-hours": "Salmos 4:8", "unanswered-message-three-days": "Salmos 46:10", "sunday-afternoon-caring-for-mother": "Salmos 121:2",
           "monday-morning-list-of-the-week": "1 Pedro 5:7", "monday-afternoon-ten-minutes-outside": "Salmos 23:2",
           "tuesday-morning-one-tab-at-a-time": "Isaías 26:3", "tuesday-evening-dark-before-six": "Salmos 34:18",
           "wednesday-morning-coat-pocket-note": "Filipenses 4:6", "wednesday-evening-winter-blanket": "Mateus 11:29",
           "thursday-morning-second-alarm": "Isaías 40:31", "thursday-evening-earbuds-ran-out": "João 14:27",
           "friday-morning-umbrella-in-the-bag": "Salmos 55:22", "friday-evening-ninety-seconds-microwave": "Êxodo 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Filipenses 4:13", "saturday-evening-grocery-bags-by-the-door": "Lamentações 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Josué 1:9", "sunday-afternoon-words-from-last-week": "Salmos 147:3"},
    "ru": {"commute-get-off-early": "Исаия 41:10", "evening-after-the-meeting": "От Матфея 11:28", "first-day-at-the-clinic": "Плач Иеремии 3:23",
           "three-am-counting-hours": "Псалом 4:9", "unanswered-message-three-days": "Псалом 45:11", "sunday-afternoon-caring-for-mother": "Псалом 120:2",
           "monday-morning-list-of-the-week": "1 Петра 5:7", "monday-afternoon-ten-minutes-outside": "Псалом 22:2",
           "tuesday-morning-one-tab-at-a-time": "Исаия 26:3", "tuesday-evening-dark-before-six": "Псалом 33:19",
           "wednesday-morning-coat-pocket-note": "К Филиппийцам 4:6", "wednesday-evening-winter-blanket": "От Матфея 11:29",
           "thursday-morning-second-alarm": "Исаия 40:31", "thursday-evening-earbuds-ran-out": "От Иоанна 14:27",
           "friday-morning-umbrella-in-the-bag": "Псалом 54:23", "friday-evening-ninety-seconds-microwave": "Исход 14:14",
           "saturday-morning-laundry-after-sleeping-in": "К Филиппийцам 4:13", "saturday-evening-grocery-bags-by-the-door": "Плач Иеремии 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Иисус Навин 1:9", "sunday-afternoon-words-from-last-week": "Псалом 146:3"},
    "vi": {"commute-get-off-early": "Ê-sai 41:10", "evening-after-the-meeting": "Ma-thi-ơ 11:28", "first-day-at-the-clinic": "Ca Thương 3:23",
           "three-am-counting-hours": "Thi Thiên 4:8", "unanswered-message-three-days": "Thi Thiên 46:10", "sunday-afternoon-caring-for-mother": "Thi Thiên 121:2",
           "monday-morning-list-of-the-week": "1 Phi-e-rơ 5:7", "monday-afternoon-ten-minutes-outside": "Thi Thiên 23:2",
           "tuesday-morning-one-tab-at-a-time": "Ê-sai 26:3", "tuesday-evening-dark-before-six": "Thi Thiên 34:18",
           "wednesday-morning-coat-pocket-note": "Phi-líp 4:6", "wednesday-evening-winter-blanket": "Ma-thi-ơ 11:29",
           "thursday-morning-second-alarm": "Ê-sai 40:31", "thursday-evening-earbuds-ran-out": "Giăng 14:27",
           "friday-morning-umbrella-in-the-bag": "Thi Thiên 55:22", "friday-evening-ninety-seconds-microwave": "Xuất Ê-díp-tô Ký 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Phi-líp 4:13", "saturday-evening-grocery-bags-by-the-door": "Ca Thương 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Giô-suê 1:9", "sunday-afternoon-words-from-last-week": "Thi Thiên 147:3"},
    "fr": {"commute-get-off-early": "Ésaïe 41:10", "evening-after-the-meeting": "Matthieu 11:28", "first-day-at-the-clinic": "Lamentations 3:23",
           "three-am-counting-hours": "Psaume 4:9", "unanswered-message-three-days": "Psaume 46:11", "sunday-afternoon-caring-for-mother": "Psaume 121:2",
           "monday-morning-list-of-the-week": "1 Pierre 5:7", "monday-afternoon-ten-minutes-outside": "Psaume 23:2",
           "tuesday-morning-one-tab-at-a-time": "Ésaïe 26:3", "tuesday-evening-dark-before-six": "Psaume 34:19",
           "wednesday-morning-coat-pocket-note": "Philippiens 4:6", "wednesday-evening-winter-blanket": "Matthieu 11:29",
           "thursday-morning-second-alarm": "Ésaïe 40:31", "thursday-evening-earbuds-ran-out": "Jean 14:27",
           "friday-morning-umbrella-in-the-bag": "Psaume 55:23", "friday-evening-ninety-seconds-microwave": "Exode 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Philippiens 4:13", "saturday-evening-grocery-bags-by-the-door": "Lamentations 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Josué 1:9", "sunday-afternoon-words-from-last-week": "Psaume 147:3"},
    "de": {"commute-get-off-early": "Jesaja 41:10", "evening-after-the-meeting": "Matthäus 11:28", "first-day-at-the-clinic": "Klagelieder 3:23",
           "three-am-counting-hours": "Psalm 4:8", "unanswered-message-three-days": "Psalm 46:10", "sunday-afternoon-caring-for-mother": "Psalm 121:2",
           "monday-morning-list-of-the-week": "1. Petrus 5:7", "monday-afternoon-ten-minutes-outside": "Psalm 23:2",
           "tuesday-morning-one-tab-at-a-time": "Jesaja 26:3", "tuesday-evening-dark-before-six": "Psalm 34:18",
           "wednesday-morning-coat-pocket-note": "Philipper 4:6", "wednesday-evening-winter-blanket": "Matthäus 11:29",
           "thursday-morning-second-alarm": "Jesaja 40:31", "thursday-evening-earbuds-ran-out": "Johannes 14:27",
           "friday-morning-umbrella-in-the-bag": "Psalm 55:22", "friday-evening-ninety-seconds-microwave": "2. Mose 14:14",
           "saturday-morning-laundry-after-sleeping-in": "Philipper 4:13", "saturday-evening-grocery-bags-by-the-door": "Klagelieder 3:22",
           "sunday-morning-bicycle-on-the-balcony": "Josua 1:9", "sunday-afternoon-words-from-last-week": "Psalm 147:3"},
}
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
                self.assertRegex(c, r'<p class="j-date"><span class="j-no">No\.&nbsp;\d+</span> · <time datetime="[^"]+"[^>]*>[^<]+</time></p>')  # number, then the date (KST) in a <time>
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
            alls = re.findall(r'<p class="journal-all"><a class="btn-ghost" href="([^"]+)">', s)
            self.assertEqual(len(alls), 1, f)
            self.assertEqual(alls[0], "/journal/%s/" % lang if list_exists(lang) else "/journal/", f)  # no list in that language yet -> the hub
            self.assertTrue((REPO / alls[0].strip("/") / "index.html").is_file(), f)

    def test_category_chip_is_the_posts_category_and_a_span(self):
        for lang, f, h in self.pages():
            for c in CARD.findall(section(h)):
                pl, slug = re.search(r'href="/journal/([a-z]{2})/([^/"]+)/"', c).groups()
                cat = bj.esc(bj.parse_post(REPO / "content/journal" / pl / (slug + ".md"))["category"])
                self.assertRegex(c, r'<div class="j-top"><span class="j-cat">%s</span>' % re.escape(cat))
                self.assertLess(c.index('class="j-top"'), c.index('class="j-date"'), f)  # chips sit above the date
                self.assertNotRegex(c, r'<(a|button)\b[^>]*>[^<]*<span class="j-(cat|verse|lang)"')  # chips are never links

    def test_verse_chip_is_the_pinned_reference_of_the_article(self):
        seen = 0
        for lang, f, h in self.pages():
            for c in CARD.findall(section(h)):
                pl, slug = re.search(r'href="/journal/([a-z]{2})/([^/"]+)/"', c).groups()
                want = PINNED[slug] if pl == "ko" else PINNED_I18N[pl][slug]  # translations: that language's book name and numbering
                self.assertEqual(re.findall(r'<span class="j-verse">([^<]+)</span>', c), [bj.esc(want)], (f, slug))
                seen += 1
        self.assertGreaterEqual(seen, 12)

    def test_language_badge_only_on_fallback_cards(self):
        for lang, f, h in self.pages():
            for c in CARD.findall(section(h)):
                card_lang = re.search(r'<a class="j-card"[^>]* lang="([^"]+)"', c).group(1)
                badges = re.findall(r'<span class="j-lang">([^<]+)</span>', c)
                if card_lang == lang:
                    self.assertEqual(badges, [], (f, "same language: no badge"))
                else:
                    self.assertEqual(badges, [LANGS[card_lang]["name"]], f)  # the language's own name, e.g. 한국어
        self.assertNotIn("j-lang", CARD.findall(section((REPO / "ko/index.html").read_text(encoding="utf-8")))[0])
        for lang in ("en", "ja", "es"):  # translated: that language's own posts, no badge
            self.assertNotIn("j-lang", section((REPO / lang / "index.html").read_text(encoding="utf-8")), lang)
        # a held language (id) shows the English versions, badged
        self.assertIn('<span class="j-lang">English</span>', CARD.findall(section((REPO / "id/index.html").read_text(encoding="utf-8")))[0])
        # vi: its translations are drafts (crisis lines not verified) -> the same English fallback, badged
        self.assertIn('<span class="j-lang">English</span>', CARD.findall(section((REPO / "vi/index.html").read_text(encoding="utf-8")))[0])

    def test_all_button(self):
        for lang, f, h in self.pages():
            self.assertRegex(section(h), r'<p class="journal-all"><a class="btn-ghost" href="/journal/([a-z]{2}/)?">[^<]*<span data-i18n="journal_all">[^<]+</span> <span aria-hidden="true">→</span></a></p>')

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

    def test_chips_and_button_css(self):
        css = TEMPLATE[TEMPLATE.index("1.5 JOURNAL"):TEMPLATE.index("/* ---------- 7. CTA")]
        self.assertRegex(css, r"\.j-cat\{[^}]*color:var\(--sage\)")
        self.assertRegex(css, r"\.btn-ghost\{[^}]*min-height:48px[^}]*border:1px solid var\(--gold\)")
        self.assertRegex(css, r"\.btn-ghost:hover,\.btn-ghost:focus-visible\{")
        self.assertIn("-webkit-line-clamp:3", css)  # title: 3 lines
        self.assertNotRegex(css, r"#[0-9a-fA-F]{3,6}\b")  # no new colour literal: tokens and the existing rgba(35,42,54,..) only

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
        self.assertIn('<a class="btn-ghost" href="/journal/ja/">', section(self.home("ja")))


class VerseRef(unittest.TestCase):
    """the verse chip: right or absent — a wrong verse on a faith app's home page is the one thing that must not happen"""

    def post(self, body, lang="ko", bible="개역한글(1961)", **kw):
        return dict(lang=lang, _body=body, _bible=bible, **kw)

    def block(self, ref_line, quote="나의 도움이 천지를 지으신 여호와에게서로다"):
        return "본문입니다.\n\n> %s\n>\n> %s\n\n끝." % (quote, ref_line)

    def test_every_real_article_matches_the_pinned_reference(self):
        posts = {f.stem: bj.parse_post(f) for f in (REPO / "content/journal/ko").glob("*.md") if f.stem != "sample-template"}
        self.assertEqual(set(posts), set(PINNED))
        for slug, p in posts.items():
            self.assertEqual(bj.verse_ref(p), PINNED[slug], slug)
            self.assertNotIn("verse", p)  # the pinned value comes from the quotation block

    def test_pinned_references_are_in_the_apps_verse_file_and_the_quote_matches(self):
        if not VERSES.is_file():
            self.skipTest("daily_verses.json is not on this machine")
        canon = {v["ref_ko"]: v["ko"] for v in json.loads(VERSES.read_text(encoding="utf-8"))["verses"]}
        for slug, ref in PINNED.items():
            self.assertIn(ref, canon, slug)
            body = bj.parse_post(REPO / "content/journal/ko" / (slug + ".md"))["_body"]
            self.assertIn("> %s\n>\n> %s (개역한글)" % (canon[ref], ref), body, slug)  # same verse, to the letter

    def test_extraction(self):
        self.assertEqual(bj.verse_ref(self.post(self.block("시편 121:2 (개역한글)"))), "시편 121:2")
        self.assertEqual(bj.verse_ref(self.post(self.block("로마서 8:38-39 (개역한글)"))), "로마서 8:38-39")
        self.assertEqual(bj.verse_ref(self.post(self.block("베드로전서 5:7 (개역한글)"))), "베드로전서 5:7")
        self.assertEqual(bj.verse_ref(self.post(self.block("1 Peter 5:7 (WEB)", "Casting all your worries on him"), lang="en", bible="WEB")), "1 Peter 5:7")

    def test_unsure_means_no_chip(self):
        bad = {
            "no version": self.block("시편 121:2"),
            "version differs from bible_version": self.block("시편 121:2 (개정개역)"),
            "unknown book": self.block("시편책 121:2 (개역한글)"),
            "english book in a ko post": self.block("Psalm 121:2 (개역한글)"),
            "no verse number": self.block("시편 121 (개역한글)"),
            "reversed range": self.block("로마서 8:39-38 (개역한글)"),
            "zero chapter": self.block("시편 0:2 (개역한글)"),
            "extra text on the line": self.block("시편 121:2 참고 (개역한글)"),
            "two blocks": self.block("시편 121:2 (개역한글)") + "\n> 또\n>\n> 시편 23:1 (개역한글)\n",
            "no quotation": "인용 없는 글입니다.",
            "quote without blank '>' line": "> 인용\n> 시편 121:2 (개역한글)\n",
        }
        for why, body in bad.items():
            self.assertIsNone(bj.verse_ref(self.post(body)), why)
        self.assertIsNone(bj.verse_ref(self.post(self.block("시편 121:2 (개역한글)"), bible=None)), "no bible_version")

    def test_front_matter_verse(self):
        # preferred value when the block cannot be read ...
        self.assertEqual(bj.verse_ref(self.post("인용 없음", verse="시편 121:2")), "시편 121:2")
        self.assertEqual(bj.verse_ref(self.post("인용 없음", lang="ja", verse="詩篇 121:2")), "詩篇 121:2")  # other languages: shape only
        # ... same value in both: fine; different values: the two disagree -> no chip
        self.assertEqual(bj.verse_ref(self.post(self.block("시편 121:2 (개역한글)"), verse="시편 121:2")), "시편 121:2")
        self.assertIsNone(bj.verse_ref(self.post(self.block("시편 121:2 (개역한글)"), verse="시편 23:1")))
        # malformed or unknown book in `verse:` is dropped
        self.assertIsNone(bj.verse_ref(self.post("인용 없음", verse="시편 하나")))
        self.assertIsNone(bj.verse_ref(self.post("인용 없음", verse="아무책 1:1")))
        self.assertEqual(bj.verse_ref(self.post(self.block("시편 121:2 (개역한글)"), verse="시편 하나")), "시편 121:2")


class Cards(Base):
    """chips and badge on generated pages (temp site)"""

    def post(self, slug, date, lang, body_ref="Psalm 46:10 (WEB)", category="rest", extra="", verse_text="Be still."):
        text = ("---\ntitle: T %s\ndate: %s\nslug: %s\nlang: %s\ndescription: D.\ncategory: %s\nbible_version: WEB\n%s%s---\n\n"
                "Body.\n\n> %s\n>\n> %s\n") % (slug, date, slug, lang, category, "" if lang in ("ko", "en") else "translation_of: en\n", extra, verse_text, body_ref)
        write_post(self.tmp, lang, slug, text=text)

    def cards(self, lang):
        return CARD.findall(section(self.page("index.html" if lang == "root" else "%s/index.html" % lang)))

    def test_badge_and_chips_with_originals_and_translations(self):
        self.post("a", "2026-10-20", "en")
        self.post("a", "2026-10-20", "ja", body_ref="詩篇 46:10 (WEB)", category="休息")
        self.assertEqual(run(self.tmp).returncode, 0)
        (en,), (ja,) = self.cards("en"), self.cards("ja")
        (fr,) = self.cards("fr")  # fr has no post -> the English original
        self.assertIn('<span class="j-cat">rest</span><span class="j-verse">Psalm 46:10</span>', en)
        self.assertNotIn("j-lang", en)  # same language: no badge
        self.assertIn('<span class="j-cat">休息</span>', ja)
        self.assertIn('<span class="j-verse">', ja)  # translation: shape of `verse` is not checked against a book list ...
        self.assertNotIn("j-lang", ja)
        self.assertIn('<span class="j-lang">English</span>', fr)  # fallback card: the post's language, in its own name
        self.assertIn('<span class="j-verse">Psalm 46:10</span>', fr)
        self.assertEqual(fr.count("<a "), 1)

    def test_unreadable_reference_leaves_the_chip_out_only(self):
        self.post("b", "2026-10-20", "en", body_ref="Psalm 46:10")  # no version in the reference line
        self.assertEqual(run(self.tmp).returncode, 0)
        (c,) = self.cards("en")
        self.assertIn('<span class="j-cat">rest</span>', c)
        self.assertNotIn("j-verse", c)

    def test_verse_front_matter_wins_when_the_block_is_unreadable(self):
        self.post("c", "2026-10-20", "ko", body_ref="시편 46:10", verse_text="가만히 있어", extra="verse: 시편 46:10\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        (c,) = self.cards("ko")
        self.assertIn('<span class="j-verse">시편 46:10</span>', c)
        self.assertNotIn("j-lang", c)
        self.assertIn('<span class="j-lang">한국어</span>', self.cards("ja")[0])


if __name__ == "__main__":
    unittest.main()
