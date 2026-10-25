"""Journal translations: every published original exists in every journal language (held ones excepted), and a translation quotes
Scripture ONLY as copied from its language's public-domain source (content/journal/scripture.json, scripts/fetch_scripture.py)."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
from site_common import LANGS  # noqa: E402
import build_journal as bj  # noqa: E402
import fetch_scripture as fs  # noqa: E402
from test_build_journal import Base, run  # noqa: E402
from test_home_journal import CARD, PAGES, PINNED, PINNED_I18N, section  # noqa: E402

J = REPO / "content/journal"
SCRIPTURE = json.loads((J / "scripture.json").read_text(encoding="utf-8"))
HELD = {k for k in json.loads((J / "hold.json").read_text(encoding="utf-8")) if not k.startswith("_")}
TARGETS = [l for l in LANGS if l != "ko" and l not in HELD]
SAFETY = json.loads((J / "safety.json").read_text(encoding="utf-8"))["lines"]
# a language whose crisis-line list is not verified may not publish: its translations stay `draft: true` (vi: no official adult line yet)
SAFETY_DRAFT = {l for l in TARGETS if SAFETY[l]["status"] != "verified"}

# the beginning of Psalm 46:10 (Korean numbering) in each text-mode Bible, written by hand from the printed source — an anchor that the
# fetched file is the right Bible and the right verse (Synodal 45:11, Segond 46:11)
PSALM_46_10_STARTS = {"en": "“Be still, and know that I am God.", "zh": "你们要休息，要知道我是", "es": "Estad quietos, y conoced que yo soy Dios",
                      "ru": "Остановитесь и познайте, что Я - Бог", "vi": "Hãy yên lặng và biết rằng ta là Đức Chúa Trời",
                      "fr": "Arrêtez, et sachez que je suis Dieu", "de": "Seid stille und erkennet, daß ich GOTT bin"}
VERSIONS = {"en": "WEB", "zh": "和合本", "es": "Reina-Valera 1909", "ru": "Синодальный перевод", "vi": "Kinh Thánh 1925", "fr": "Louis Segond 1910",
            "de": "Lutherbibel 1912"}
REFERENCE_ONLY = {"ja", "pt"}  # no confirmed public-domain text yet (room note 20261022-221259): the reference only, no verse wording


def originals():
    return {f.stem: bj.parse_post(f) for f in sorted((J / "ko").glob("*.md")) if not bj.parse_post(f)["draft"]}


def translation(lang, slug):
    return bj.parse_post(J / lang / (slug + ".md"))


class Coverage(unittest.TestCase):
    def test_every_original_in_every_language_but_the_held_ones(self):
        orig = originals()
        self.assertEqual(set(orig), set(PINNED))
        for l in TARGETS:
            for slug in orig:
                self.assertTrue((J / l / (slug + ".md")).is_file(), "%s/%s.md missing — python3 scripts/journal_i18n.py status" % (l, slug))
        self.assertEqual(set(PINNED_I18N), set(TARGETS))

    def test_held_languages_stay_held(self):
        self.assertIn("id", HELD)  # decision 2026-10-23 (Matt·ops): no free Indonesian Bible covering the Old Testament yet
        for l in HELD:
            for f in (J / l).glob("*.md") if (J / l).is_dir() else []:
                self.assertTrue(bj.parse_post(f)["draft"], f)
            self.assertFalse((REPO / "journal" / l).exists(), l)

    def test_vi_stays_private_until_its_crisis_lines_are_verified(self):
        self.assertEqual(SAFETY_DRAFT, {"vi"})  # every other translated language was verified 2026-10-25
        for l in SAFETY_DRAFT:
            self.assertFalse((REPO / "journal" / l).exists(), l)  # no generated pages
            for f in (REPO / "sitemap.xml", REPO / "llms.txt", REPO / "journal/feed.xml"):
                if f.is_file():
                    self.assertNotIn("/journal/%s/" % l, f.read_text(encoding="utf-8"), (f.name, l))
            for page in (REPO / "journal").rglob("index.html"):  # no hreflang / language-picker entry points at it
                self.assertNotIn("/journal/%s/" % l, page.read_text(encoding="utf-8"), (str(page), l))
            for lang, f in PAGES:  # no home card (or all-link) points at it: the card falls back to English, badged
                self.assertNotIn("/journal/%s/" % l, f.read_text(encoding="utf-8"), f)

    def test_translation_front_matter_follows_the_original(self):
        for slug, o in originals().items():
            for l in TARGETS:
                t = translation(l, slug)
                self.assertEqual(t["lang"], l)
                self.assertEqual(t["translation_of"], "ko", (l, slug))
                self.assertEqual(t["date"], o["date"], (l, slug))
                for k in ("publish_at", "published_at"):
                    self.assertEqual(t.get(k), o.get(k), (l, slug, k))  # the same time in every language
                self.assertEqual(t["draft"], l in SAFETY_DRAFT, (l, slug))
                for k in ("title", "description", "category"):
                    self.assertNotEqual(t[k], o[k], (l, slug, k))  # translated, not copied
                    self.assertFalse(re.search(r"[가-힣]", t[k]), (l, slug, k))  # no Hangul left
                self.assertFalse(re.search(r"[가-힣]", t["_body"]), (l, slug, "Hangul in the body"))


class Scripture(unittest.TestCase):
    def test_scripture_json_covers_every_quoted_verse_and_language(self):
        self.assertEqual(set(SCRIPTURE["versions"]), set(TARGETS))
        keys = {bj.verse_key(p) for p in originals().values()}
        self.assertEqual(keys, set(SCRIPTURE["verses"]) & keys)
        for l, v in SCRIPTURE["versions"].items():
            if l in REFERENCE_ONLY:
                self.assertEqual(v["mode"], "reference", l)
                self.assertTrue(v.get("why"), l)
                continue
            self.assertEqual(v["mode"], "text", l)
            self.assertEqual(v["version"], VERSIONS[l], l)
            self.assertRegex(v["source"], r"^https://ebible\.org/Scriptures/[\w-]+_usfm\.zip$", l)
            self.assertRegex(v["sha256"], r"^[0-9a-f]{64}$", l)
        for key, langs in SCRIPTURE["verses"].items():
            for l in TARGETS:
                self.assertIn(l, langs, (key, l))
                self.assertEqual(bool(langs[l].get("text")), l not in REFERENCE_ONLY, (key, l))

    def test_the_fetched_psalm_is_the_right_bible_and_verse(self):
        v = SCRIPTURE["verses"]["PSA 46:10"]
        for l, start in PSALM_46_10_STARTS.items():
            self.assertTrue(v[l]["text"].startswith(start), (l, v[l]["text"]))

    def test_every_translation_quotes_the_fetched_verse_to_the_letter(self):
        for slug, o in originals().items():
            key = bj.verse_key(o)
            for l in TARGETS:
                t = translation(l, slug)
                quote = [x for x in t["_body"].split("\n") if x.startswith(">")]
                ent = SCRIPTURE["verses"][key][l]
                if l in REFERENCE_ONLY:
                    self.assertEqual(quote, ["> " + ent["ref"]], (l, slug))
                    self.assertEqual(t["bible_version"], "none", (l, slug))
                    self.assertEqual(t["verse"], ent["ref"], (l, slug))
                else:
                    self.assertEqual(quote, ["> " + ent["text"], ">", "> %s (%s)" % (ent["ref"], VERSIONS[l])], (l, slug))
                    self.assertEqual(t["bible_version"], VERSIONS[l], (l, slug))
                self.assertEqual(bj.verse_ref(t), PINNED_I18N[l][slug], (l, slug))  # the chip

    def test_reference_only_posts_quote_no_verse_text_anywhere(self):
        # the Korean text of the verse must not appear (translated) anywhere — only the reference. Here: no quotation block beyond it.
        for slug in originals():
            for l in REFERENCE_ONLY:
                body = translation(l, slug)["_body"]
                self.assertEqual(len([x for x in body.split("\n") if x.startswith(">")]), 1, (l, slug))

    def test_committed_home_chips_follow_the_pinned_references(self):
        seen = 0
        for lang, f in PAGES:
            for c in CARD.findall(section(f.read_text(encoding="utf-8"))):
                m = re.search(r'href="/journal/([a-z]{2})/([^/"]+)/"', c)
                want = PINNED[m.group(2)] if m.group(1) == "ko" else PINNED_I18N[m.group(1)][m.group(2)]
                self.assertEqual(re.findall(r'<span class="j-verse">([^<]+)</span>', c), [bj.esc(want)], (f, m.group(0)))
                seen += 1
        self.assertGreaterEqual(seen, 12)


class NoNumbersInProse(unittest.TestCase):
    def test_translations_name_no_crisis_number(self):
        """phone numbers come only from safety.json (verified per country, in the crisis box); the prose points to it (#help)"""
        safety = json.loads((J / "safety.json").read_text(encoding="utf-8"))
        numbers = {"109"} | {it["number"] for e in safety["lines"].values() for r in e["regions"] for it in r["items"]}
        for slug in originals():
            for l in TARGETS:
                body = translation(l, slug)["_body"]
                for n in numbers:
                    self.assertNotRegex(body, r"(?<![\d:])%s(?![\d:])" % re.escape(n), (l, slug, n))
        for l in TARGETS:
            self.assertIn("](#help)", translation(l, "evening-after-the-meeting")["_body"], l)  # the Korean original names 109 there


class FetchParser(unittest.TestCase):
    USFM = ("\\id PSA test\n\\c 46\n\\s1 Heading\n\\d For the Chief Musician.\\f + \\fr 46:0 \\ft note\\f*\n\\q1\n\\v 9 Nine.\n\\q1\n"
            "\\v 10 \\w Be|strong=\"H1\"\\w* still,\\x - \\xo 46.10 \\xt Ex 14:13\\x* and \\nd know\\nd*.\n\\q2 I will be exalted.\n\\v 11 Eleven.\n\\c 47\n\\v 1 x\n")

    def test_verse_text_without_markup(self):
        self.assertEqual(fs.usfm_verse(self.USFM, 46, 10, "en"), "Be still, and know . I will be exalted.".replace(" .", "."))

    def test_cjk_lines_join_without_space_and_keep_the_ideographic_space(self):
        u = "\\c 4\n\\v 8 我必安然躺下睡觉，\n\\q1 因为独有你　神。\n\\v 9 x\n"
        self.assertEqual(fs.usfm_verse(u, 4, 8, "zh"), "我必安然躺下睡觉，因为独有你　神。")

    def test_numbering_differences_need_a_hand_checked_entry(self):
        self.assertEqual(fs.source_key("ru", "PSA 46:10"), "PSA 45:11")
        self.assertEqual(fs.source_key("fr", "PSA 46:10"), "PSA 46:11")
        self.assertEqual(fs.source_key("de", "PSA 46:10"), "PSA 46:10")
        with self.assertRaises(SystemExit):
            fs.source_key("ru", "PSA 91:1")  # not checked yet -> refuse, never compute


class BuildChecksTheQuote(Base):
    """build_journal.py refuses a translation whose quotation block is not the fetched verse (deploy gate: --check runs it too)"""

    ORIG = ("---\ntitle: 원문\ndate: 2026-10-22\nslug: s\nlang: ko\ndescription: 설명.\ncategory: 쉼\nbible_version: 개역한글(1961)\n---\n\n본문.\n\n"
            "> 너희는 가만히 있어 내가 하나님 됨을 알지어다\n>\n> 시편 46:10 (개역한글)\n")

    def setUp(self):
        super().setUp()
        shutil.copy(J / "scripture.json", self.tmp / "content/journal/scripture.json")
        shutil.copy(J / "hold.json", self.tmp / "content/journal/hold.json")
        (self.tmp / "content/journal/ko").mkdir()
        (self.tmp / "content/journal/ko/s.md").write_text(self.ORIG, encoding="utf-8")

    def write(self, lang, quote, bible, extra=""):
        d = self.tmp / "content/journal" / lang
        d.mkdir(exist_ok=True)
        (d / "s.md").write_text("---\ntitle: T\ndate: 2026-10-22\nslug: s\nlang: %s\ndescription: D.\ncategory: c\nbible_version: %s\n"
                                "translation_of: ko\n%s---\n\nBody.\n\n%s\n" % (lang, bible, extra, quote), encoding="utf-8")

    def test_the_fetched_verse_builds(self):
        v = SCRIPTURE["verses"]["PSA 46:10"]
        self.write("en", "> %s\n>\n> Psalm 46:10 (WEB)" % v["en"]["text"], "WEB")
        self.write("ru", "> %s\n>\n> Псалом 45:11 (Синодальный перевод)" % v["ru"]["text"], "Синодальный перевод")
        self.write("ja", "> 詩篇 46:10", "none", "verse: 詩篇 46:10\n")
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Псалом 45:11", self.page("journal/ru/s/index.html"))

    def test_a_retyped_or_translated_verse_fails(self):
        self.write("en", "> Be still, and know that I am God.\n>\n> Psalm 46:10 (WEB)", "WEB")  # the KJV-ish half verse: not the fetched text
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("quotation block must be exactly", r.stderr)

    def test_the_korean_number_in_a_language_that_numbers_differently_fails(self):
        v = SCRIPTURE["verses"]["PSA 46:10"]
        self.write("ru", "> %s\n>\n> Псалом 46:10 (Синодальный перевод)" % v["ru"]["text"], "Синодальный перевод")
        self.assertEqual(run(self.tmp).returncode, 1)

    def test_reference_only_language_may_not_quote_text(self):
        self.write("ja", "> 静まって、わたしこそ神であることを知れ。\n>\n> 詩篇 46:10 (口語訳)", "口語訳")
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("bible_version must be 'none'", r.stderr)

    def test_journal_i18n_apply_writes_the_fetched_block(self):
        self.write("en", "> (verse)", "WEB")
        r = subprocess.run([sys.executable, str(REPO / "scripts/journal_i18n.py"), "--root", str(self.tmp), "apply", "--lang", "en"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertIn(bj.esc(SCRIPTURE["verses"]["PSA 46:10"]["en"]["text"]), self.page("journal/en/s/index.html"))


if __name__ == "__main__":
    unittest.main()
