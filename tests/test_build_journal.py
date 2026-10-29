"""Tests for scripts/build_journal.py — run: python3 -m unittest discover -s tests"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402
import check_sitemap  # noqa: E402

LANGS = list(bj.LANGS)
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}
POST = """---
title: Title %(l)s
date: 2026-10-22
slug: hello
lang: %(l)s
description: Desc %(l)s.
category: test
%(extra)s---

Body %(l)s.

> A verse.
>
> Psalm 46:10
"""


def write_post(root, lang, slug="hello", extra=None, text=None):
    if extra is None:
        extra = "bible_version: WEB\n" + ("" if lang in ("ko", "en") else "translation_of: en\n")
    d = Path(root) / "content/journal" / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / (slug + ".md")).write_text(text or POST % dict(l=lang, extra=extra), encoding="utf-8")


def site_copy():
    tmp = Path(tempfile.mkdtemp())
    for f in ("sitemap.xml", "llms.txt", "og-image.png", "robots.txt"):
        shutil.copy(REPO / f, tmp / f)
    shutil.copytree(REPO / "content/home", tmp / "content/home")
    shutil.copytree(REPO / "content/info", tmp / "content/info")
    (tmp / "content/journal").mkdir(parents=True)
    for page in ("privacy", "terms"):  # legal pages listed in the sitemap
        (tmp / page).mkdir()
        (tmp / page / "index.html").write_text("x")
    for f in ("safety.json", "ui.json"):
        shutil.copy(REPO / "content/journal" / f, tmp / "content/journal" / f)
    return tmp


def sitemap_errors_at(root, when):
    """check_sitemap problems with the build clock `when`, except "lastmod after today": these tests time-travel to a day before the copied
    home pages' own lastmod, which is a fixture artifact (the deploy runner's clock is the real one)."""
    return [e for e in check_sitemap.check(root, bj.parse_when(when))[0] if "is after today" not in e]


def run(root, *args):
    return subprocess.run([sys.executable, str(REPO / "scripts/build_journal.py"), "--root", str(root), *args], capture_output=True, text=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = site_copy()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def page(self, rel):
        return (self.tmp / rel).read_text(encoding="utf-8")


class AllLanguages(Base):
    """one post in every language -> every page carries the fixed safety block, hreflang is mutual, sitemap is valid"""

    def setUp(self):
        super().setUp()
        for l in LANGS:
            write_post(self.tmp, l)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_safety_block_on_every_language_page(self):
        data = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))
        for l in LANGS:
            h = self.page("journal/%s/hello/index.html" % l)
            txt = data["text"][l]
            for k in ("fiction", "disclaimer", "jump", "help_title", "help_intro", "fallback", "bible_label"):
                self.assertIn(bj.esc(txt[k]), h, "%s: %s missing" % (l, k))
            self.assertIn('id="help"', h, l)
            self.assertIn('href="#help"', h, l)  # the notice jumps to the crisis box
            self.assertIn('data-crisis-lines="%s"' % data["lines"][l]["status"], h, l)
            self.assertIn("https://findahelpline.com", h, l)
            self.assertIn('class="bible-version"', h, l)
            self.assertIn("WEB", h, l)
            self.assertEqual(h.count(bj.esc(txt["disclaimer"])), 2, l)  # under the title and again after the text
            self.assertEqual(h.count(bj.esc(txt["fiction"])), 2, l)  # the creative-work notice too: under the title and at the very end
            for r in data["lines"][l]["regions"]:
                for it in r["items"]:
                    if it["status"] != "verified":  # an unconfirmed number is never printed (neither number nor tap-to-call link)
                        self.assertNotIn(bj.esc(it["number"]), h, "%s: draft number %s is shown" % (l, it["number"]))
                        continue
                    self.assertIn(bj.esc(it["number"]), h, l)
                    if it.get("tel"):
                        self.assertIn('href="tel:%s"' % it["tel"], h, l)

    def test_only_verified_lines_are_shown(self):
        h = self.page("journal/ko/hello/index.html")
        self.assertIn("자살예방상담전화", h)
        self.assertIn(">109<", h)
        self.assertNotIn("1577-0199", h)  # draft until confirmed
        for l in ("vi",):  # nothing confirmed yet: only the worldwide directory link remains
            h = self.page("journal/%s/hello/index.html" % l)
            self.assertNotIn("help-region", h, l)
            self.assertIn("https://findahelpline.com", h, l)
        h = self.page("journal/ja/hello/index.html")  # verified (MHLW, 2026-10-25): its numbers are on the page
        self.assertIn("0120-783-556", h)
        self.assertNotIn("0570-783-556", h)  # the toll 0570 Inochi-no-Denwa line was dropped for the MHLW free number

    def test_a_number_becomes_visible_once_verified(self):
        p = self.tmp / "content/journal/safety.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        it = d["lines"]["ko"]["regions"][0]["items"][1]
        self.assertEqual((it["number"], it["status"]), ("1577-0199", "draft"))
        it["status"], it["checked_on"] = "verified", "2026-11-01"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertIn("1577-0199", self.page("journal/ko/hello/index.html"))

    def test_dates_are_written_in_the_pages_language(self):
        want = {"en": "October 22, 2026", "ko": "2026년 10월 22일", "ja": "2026年10月22日", "zh": "2026年10月22日",
                "es": "22 de octubre de 2026", "pt": "22 de outubro de 2026", "id": "22 Oktober 2026", "ru": "22 октября 2026 г.",
                "vi": "22 tháng 10, 2026", "fr": "22 octobre 2026", "de": "22. Oktober 2026"}
        self.assertEqual(sorted(want), sorted(LANGS))
        for l in LANGS:
            h = self.page("journal/%s/hello/index.html" % l)
            self.assertIn('<time datetime="2026-10-22">%s</time>' % want[l], h, l)
        self.assertEqual(bj.fmt_date(__import__("datetime").date(2026, 11, 1), "fr"), "1er novembre 2026")

    def test_aria_labels_and_language_links_follow_the_language(self):
        home = json.loads((REPO / "content/home/i18n.json").read_text(encoding="utf-8"))
        ui = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
        for l in LANGS:
            h = self.page("journal/%s/hello/index.html" % l)
            self.assertIn('class="foot-links" aria-label="%s"' % bj.esc(home[l]["aria_footer"]), h, l)
            self.assertIn('aria-label="%s"' % bj.esc(ui[l]["aria_home"]), h, l)
            self.assertIn('<meta property="og:image:alt" content="%s">' % bj.esc(home[l]["og_image_alt"]), h, l)
            # the language switch exists without JS: a link to this post in every language
            nav = re.search(r'<nav class="foot-langs".*?</nav>', h, re.S).group(0)
            self.assertEqual(sorted(re.findall(r'hreflang="(\w+)"', nav)), sorted(LANGS), l)
            self.assertIn('href="/journal/%s/hello/" hreflang="%s" lang="%s" aria-current="true"' % (l, l, l), nav)
            if l != "en":
                self.assertNotIn('aria-label="Footer"', h, l)
                self.assertNotIn('aria-label="primary"', h, l)

    def test_safety_block_comes_from_data_not_from_the_post(self):
        # a post cannot override or remove it: same wording in two different posts
        write_post(self.tmp, "en", slug="other", text=POST.replace("hello", "other") % dict(l="en", extra="bible_version: KJV\n"))
        self.assertEqual(run(self.tmp).returncode, 0)
        a, b = self.page("journal/en/hello/index.html"), self.page("journal/en/other/index.html")
        grab = lambda h: re.search(r'<div class="help".*?</section>', h, re.S).group(0)
        self.assertEqual(grab(a), grab(b))
        self.assertIn("KJV", b)

    def test_hreflang_is_mutual_and_complete(self):
        pages = {l: self.page("journal/%s/hello/index.html" % l) for l in LANGS}
        for l, h in pages.items():
            got = dict(re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', h))
            self.assertEqual(set(got), set(LANGS) | {"x-default"}, l)
            self.assertEqual(got["x-default"], "https://still.ipe.rest/journal/en/hello/")
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/journal/%s/hello/">' % l, h)
            for l2, u in got.items():
                if l2 != "x-default":
                    self.assertEqual(u, "https://still.ipe.rest/journal/%s/hello/" % l2)
                    # the target page lists this page under this page's own language: reciprocal
                    back = dict(re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', pages[l2]))
                    self.assertEqual(back[l], "https://still.ipe.rest/journal/%s/hello/" % l)

    def test_translations_show_ai_note_with_original_link(self):
        ja = self.page("journal/ja/hello/index.html")
        self.assertIn('class="ai-note"', ja)
        self.assertIn('href="/journal/en/hello/"', ja)
        self.assertIn("translationOfWork", ja)
        self.assertNotIn('class="ai-note"', self.page("journal/en/hello/index.html"))  # the original
        self.assertIn("workTranslation", self.page("journal/en/hello/index.html"))

    def test_sitemap_and_check_pass(self):
        errs, urls = check_sitemap.check(self.tmp)
        self.assertEqual(errs, [])
        root = ET.parse(self.tmp / "sitemap.xml").getroot()
        locs = {u.find("s:loc", NS).text for u in root.findall("s:url", NS)}
        self.assertIn("https://still.ipe.rest/journal/", locs)
        for l in LANGS:
            self.assertIn("https://still.ipe.rest/journal/%s/" % l, locs)
            self.assertIn("https://still.ipe.rest/journal/%s/hello/" % l, locs)
        self.assertEqual(len(locs), 12 + 22 + 2 + 1 + 11 + 11)  # home + faq/about + privacy/terms + hub + lists + posts

    def test_llms_and_feed(self):
        self.assertIn("https://still.ipe.rest/journal/ko/hello/", self.page("llms.txt"))
        feed = self.page("journal/feed.xml")
        self.assertIn("/journal/en/hello/", feed)  # an original
        self.assertNotIn("/journal/ja/hello/", feed)  # translations are not in the feed

    def test_home_cards_follow_the_language(self):
        self.assertIn('href="/journal/ja/hello/"', self.page("ja/index.html"))
        self.assertNotIn("<section class=\"journal\" id=\"journal\" hidden>", self.page("ja/index.html"))
        self.assertIn('href="/journal/ja/"', self.page("ja/index.html"))

    def test_idempotent_and_fresh(self):
        before = {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()}
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(before, {p: p.read_bytes() for p in self.tmp.rglob("*") if p.is_file()})
        r = run(self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_stale_output_fails_check(self):
        (self.tmp / "journal/ko/hello/index.html").write_text("stale " + bj.GEN_MARK, encoding="utf-8")
        self.assertEqual(run(self.tmp, "--check").returncode, 1)


    def test_journal_pages_footer_links_privacy_and_terms_with_slash(self):
        for rel in ("journal/en/hello/index.html", "journal/ko/index.html"):
            h = self.page(rel)
            self.assertIn('<a href="/privacy/">', h, rel)
            self.assertIn('<a href="/terms/">', h, rel)
            self.assertNotIn('href="/privacy"', h, rel)


class Drafts(Base):
    def test_draft_never_leaks(self):
        write_post(self.tmp, "ko", extra="draft: true\nbible_version: x\n")
        write_post(self.tmp, "en", extra="draft: true\ntranslation_of: ko\nbible_version: x\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertFalse((self.tmp / "journal/ko/hello").exists())
        self.assertFalse((self.tmp / "journal/ko").exists())
        for f in ("sitemap.xml", "llms.txt", "journal/index.html", "journal/feed.xml", "en/index.html"):
            self.assertNotIn("hello", self.page(f), f)
        self.assertIn('hidden>', self.page("ko/index.html").split('id="journal"')[1][:20])  # home section stays hidden
        self.assertIn("noindex", self.page("journal/index.html"))
        self.assertEqual(check_sitemap.check(self.tmp)[0], [])

    def test_preview_marks_drafts_noindex(self):
        write_post(self.tmp, "ko", extra="draft: true\nbible_version: x\n")
        self.assertEqual(run(self.tmp, "--drafts").returncode, 0)
        h = self.page("journal/ko/hello/index.html")
        self.assertIn("DRAFT", h)
        self.assertIn("noindex", h)

    def test_repo_samples_are_drafts(self):
        self.assertTrue((REPO / "content/journal/ko/sample-template.md").is_file())
        self.assertFalse((REPO / "journal/ko/sample-template").exists())
        self.assertNotIn("sample-template", (REPO / "sitemap.xml").read_text(encoding="utf-8"))


class Validation(Base):
    def fails(self, msg):
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(msg, r.stderr)

    def test_quote_needs_bible_version(self):
        write_post(self.tmp, "ko", extra="")
        self.fails("bible_version")

    def test_bible_version_none_is_allowed_and_not_printed(self):
        write_post(self.tmp, "ko", extra="bible_version: none\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertNotIn('class="bible-version"', self.page("journal/ko/hello/index.html"))

    def test_no_quote_needs_no_bible_version(self):
        write_post(self.tmp, "ko", text="---\ntitle: T\ndate: 2026-10-22\nslug: hello\nlang: ko\ndescription: D.\ncategory: c\n---\n\nPlain text.\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertNotIn('class="bible-version"', self.page("journal/ko/hello/index.html"))
        self.assertIn('id="help"', self.page("journal/ko/hello/index.html"))  # the rest of the safety block stays

    def test_translation_needs_translation_of_and_an_original(self):
        write_post(self.tmp, "ja", extra="bible_version: x\n")
        self.fails("translation_of")
        write_post(self.tmp, "ja", extra="bible_version: x\ntranslation_of: ko\n")
        self.fails("no ko post")

    def test_misc_errors(self):
        write_post(self.tmp, "ko", slug="feed", text=POST.replace("hello", "feed") % dict(l="ko", extra="bible_version: x\n"))
        self.fails("reserved")
        (self.tmp / "content/journal/ko/feed.md").unlink()
        write_post(self.tmp, "ko", extra="bible_version: x\nlang: en\n")
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)

    def test_safety_data_must_be_complete(self):
        p = self.tmp / "content/journal/safety.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        del d["text"]["vi"]["disclaimer"]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.fails("text.vi lacks 'disclaimer'")

    def test_every_crisis_line_needs_a_status(self):
        p = self.tmp / "content/journal/safety.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        del d["lines"]["ko"]["regions"][0]["items"][0]["status"]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.fails("needs status draft|verified")
        d["lines"]["ko"]["regions"][0]["items"][0]["status"] = "verified"
        del d["lines"]["ko"]["regions"][0]["items"][0]["checked_on"]
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.fails("has no checked_on date")

    def test_held_language_may_only_have_drafts(self):
        shutil.copy(REPO / "content/journal/hold.json", self.tmp / "content/journal/hold.json")
        write_post(self.tmp, "ko", extra="bible_version: x\n")
        write_post(self.tmp, "id", extra="bible_version: x\ntranslation_of: ko\n")
        self.fails("the id journal is on hold")
        write_post(self.tmp, "id", extra="bible_version: x\ntranslation_of: ko\ndraft: true\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check").returncode, 0)
        self.assertFalse((self.tmp / "journal/id").exists())  # no list page, no post page
        self.assertNotIn("/journal/id/", self.page("sitemap.xml"))
        self.assertNotIn("/journal/id/", self.page("llms.txt"))
        self.assertNotIn('hreflang="id"', self.page("journal/ko/hello/index.html"))
        self.assertNotIn("/journal/id/", self.page("journal/feed.xml"))
        self.assertNotIn("/journal/id/", self.page("journal/index.html"))
        self.assertIn("/journal/ko/", self.page("journal/index.html"))

    def test_strict_safety_gate(self):
        p = self.tmp / "content/journal/safety.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["lines"]["ko"]["status"] = "draft"  # (the repo's ko data is verified now)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        write_post(self.tmp, "ko", extra="bible_version: x\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check").returncode, 0)  # the normal check allows draft crisis lines
        r = run(self.tmp, "--check", "--strict-safety")
        self.assertEqual(r.returncode, 1)
        self.assertIn("crisis lines for ko are still `draft`", r.stderr)
        d["lines"]["ko"]["status"] = "verified"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check", "--strict-safety").returncode, 0)  # only languages with posts are gated

    def test_strict_safety_passes_without_posts(self):
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check", "--strict-safety").returncode, 0)


POSTS = {  # slug -> (verse reference, planned publication day)
    "commute-get-off-early": ("이사야 41:10", "2026-10-23"),
    "evening-after-the-meeting": ("마태복음 11:28", "2026-10-23"),
    "first-day-at-the-clinic": ("예레미야애가 3:23", "2026-10-24"),
    "three-am-counting-hours": ("시편 4:8", "2026-10-24"),
}
def find_verses():
    """canonical verse file of the app (not in this repo): $STILL_APP_VERSES -> ~/Developer/foundry-f001/... -> the old Desktop path.
    The first one that exists wins; none exists (CI, any machine without the app) -> the old path, so the tests that need it skip."""
    candidates = [Path(os.environ["STILL_APP_VERSES"]).expanduser()] if os.environ.get("STILL_APP_VERSES") else []
    candidates += [Path.home() / "Developer/foundry-f001/assets/verses/daily_verses.json", Path("/Users/davy.kim/Desktop/foundry-f001/assets/verses/daily_verses.json")]
    return next((c for c in candidates if c.is_file()), candidates[-1])


VERSES = find_verses()  # canonical text of the app (not in this repo)


SCHEDULE = {"first-day-at-the-clinic": "2026-10-24 11:00", "three-am-counting-hours": "2026-10-24 17:00"}  # KST; the others have no publish_at


class FirstPosts(unittest.TestCase):
    """the four Korean first posts (content/journal/ko) after the Dane review (2026-10-23)"""

    @classmethod
    def setUpClass(cls):
        cls.src = {s: bj.parse_post(REPO / "content/journal/ko" / (s + ".md")) for s in POSTS}

    def test_front_matter_after_the_review(self):
        for slug, (ref, day) in POSTS.items():
            p = self.src[slug]
            self.assertEqual(p["date"], day, slug)  # 2 posts a day, 11:00 and 17:00 KST
            self.assertEqual(p["lang"], "ko")
            self.assertFalse(p["draft"], slug)  # published: the 10-23 posts at once, the 10-24 posts on schedule
            self.assertEqual(p["_publish_at"].strftime("%Y-%m-%d %H:%M") if p["_publish_at"] else None, SCHEDULE.get(slug), slug)
            self.assertIn(ref, p["description"], slug)
            self.assertIn("1인칭 이야기", p["description"], slug)
            self.assertNotIn("기록", p["description"], slug)  # reads as a real diary
            self.assertEqual(p["_bible"], "개역한글(1961)")
            self.assertNotIn("공황", p["title"] + p["description"] + slug, slug)  # no self-diagnosis in the meta
        self.assertEqual(self.src["commute-get-off-early"]["title"], "지하철에서 한 정거장 먼저 내려도 괜찮았다")

    def test_109_comes_after_the_verse_and_the_breath(self):
        body = self.src["evening-after-the-meeting"]["_body"]
        self.assertGreater(body.index("109(자살예방 상담전화, 24시간)"), body.index("**오늘의 숨**"))
        self.assertGreater(body.index("**오늘의 숨**"), body.index("마태복음 11:28 (개역한글)"))
        for slug in ("commute-get-off-early", "first-day-at-the-clinic", "three-am-counting-hours"):
            self.assertNotIn("109", self.src[slug]["_body"], slug)

    def test_the_verse_is_the_app_text_to_the_letter(self):
        quotes = {}
        for slug, (ref, _) in POSTS.items():
            m = re.search(r"(?m)^> (.+)\n>\n> %s \(개역한글\)$" % re.escape(ref), self.src[slug]["_body"])
            self.assertTrue(m, "%s: verse block with its reference" % slug)
            quotes[ref] = m.group(1)
            self.assertEqual(len(re.findall(r"(?m)^>", self.src[slug]["_body"])), 3, slug)  # nothing else is quoted
        if not VERSES.is_file():
            self.skipTest("daily_verses.json is not on this machine")
        canon = {v["ref_ko"]: v["ko"] for v in json.loads(VERSES.read_text(encoding="utf-8"))["verses"]}
        for ref, text in quotes.items():
            self.assertEqual(text, canon[ref], ref)

    def test_every_post_page_ends_with_the_fixed_blocks(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
            r = run(tmp / "s", "--drafts")  # preview build: drafts included
            self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))["text"]["ko"]
            for slug in POSTS:
                h = (tmp / "s/journal/ko" / slug / "index.html").read_text(encoding="utf-8")
                end = h[h.index('data-safety="block"'):]
                self.assertEqual(h.count(data["fiction"]), 2, slug)  # under the title + at the end
                self.assertIn(data["fiction"], end, slug)
                self.assertIn('id="help"', end, slug)
                self.assertIn(">109<", end, slug)  # the verified crisis line
                self.assertIn("https://findahelpline.com", end, slug)
                self.assertIn(data["disclaimer"], end, slug)
                self.assertIn("개역한글(1961)", h, slug)
        finally:
            shutil.rmtree(tmp)

    def test_committed_site_has_only_the_unscheduled_posts(self):
        # the committed output is clock-free: the two 10-23 posts are in, the two scheduled ones are built only by the deploy runner (--now)
        sm = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        for slug in POSTS:
            scheduled = slug in SCHEDULE
            self.assertEqual((REPO / "journal/ko" / slug).exists(), not scheduled, slug)
            self.assertEqual("/journal/ko/%s/" % slug in sm, not scheduled, slug)
        self.assertFalse((REPO / "journal/ko/sample-template").exists())

    def test_the_scheduled_posts_go_live_at_their_time(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
            for when, live in (("2026-10-24 10:59", set()), ("2026-10-24 11:00", {"first-day-at-the-clinic"}),
                               ("2026-10-24 17:00", set(SCHEDULE))):
                r = run(tmp / "s", "--now", when)
                self.assertEqual(r.returncode, 0, r.stderr)
                for slug in SCHEDULE:
                    self.assertEqual((tmp / "s/journal/ko" / slug / "index.html").is_file(), slug in live, (when, slug))
                self.assertEqual(sitemap_errors_at(tmp / "s", when), [], when)
        finally:
            shutil.rmtree(tmp)


POSTS_1026 = {  # slug -> (verse reference, scheduled publish_at KST)
    "monday-morning-list-of-the-week": ("베드로전서 5:7", "2026-10-26 09:08"),
    "monday-afternoon-ten-minutes-outside": ("시편 23:2", "2026-10-26 16:49"),
}


class Posts1026(unittest.TestCase):
    """the two scheduled Korean posts of 2026-10-26: front matter, verse text to the letter, go-live times"""

    @classmethod
    def setUpClass(cls):
        cls.src = {s: bj.parse_post(REPO / "content/journal/ko" / (s + ".md")) for s in POSTS_1026}

    def test_front_matter(self):
        for slug, (ref, at) in POSTS_1026.items():
            p = self.src[slug]
            self.assertEqual(p["date"], "2026-10-26", slug)
            self.assertEqual(p["lang"], "ko")
            self.assertFalse(p["draft"], slug)
            self.assertEqual(p["_publish_at"].strftime("%Y-%m-%d %H:%M"), at, slug)
            self.assertIn(ref, p["description"], slug)
            self.assertIn("1인칭 이야기", p["description"], slug)
            self.assertNotIn("기록", p["description"], slug)
            self.assertEqual(p["_bible"], "개역한글(1961)")

    def test_the_verse_is_the_app_text_to_the_letter(self):
        quotes = {}
        for slug, (ref, _) in POSTS_1026.items():
            m = re.search(r"(?m)^> (.+)\n>\n> %s \(개역한글\)$" % re.escape(ref), self.src[slug]["_body"])
            self.assertTrue(m, "%s: verse block with its reference" % slug)
            quotes[ref] = m.group(1)
            self.assertEqual(len(re.findall(r"(?m)^>", self.src[slug]["_body"])), 3, slug)  # nothing else is quoted
            self.assertNotIn("109", self.src[slug]["_body"], slug)  # the crisis line comes only from the fixed block
        if not VERSES.is_file():
            self.skipTest("daily_verses.json is not on this machine")
        canon = {v["ref_ko"]: v["ko"] for v in json.loads(VERSES.read_text(encoding="utf-8"))["verses"]}
        for ref, text in quotes.items():
            self.assertEqual(text, canon[ref], ref)

    def test_the_posts_go_live_at_their_time(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
            for when, live in (("2026-10-26 09:07", set()), ("2026-10-26 09:08", {"monday-morning-list-of-the-week"}),
                               ("2026-10-26 16:49", set(POSTS_1026))):
                r = run(tmp / "s", "--now", when)
                self.assertEqual(r.returncode, 0, r.stderr)
                for slug in POSTS_1026:
                    self.assertEqual((tmp / "s/journal/ko" / slug / "index.html").is_file(), slug in live, (when, slug))
                self.assertEqual(sitemap_errors_at(tmp / "s", when), [], when)
            h = (tmp / "s/journal/ko/monday-afternoon-ten-minutes-outside/index.html").read_text(encoding="utf-8")
            data = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))["text"]["ko"]
            end = h[h.index('data-safety="block"'):]
            self.assertEqual(h.count(data["fiction"]), 2)
            self.assertIn('id="help"', end)
            self.assertIn(">109<", end)
            self.assertIn(data["disclaimer"], end)
        finally:
            shutil.rmtree(tmp)

    def test_committed_site_holds_them_back(self):
        sm = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        for slug in POSTS_1026:
            self.assertFalse((REPO / "journal/ko" / slug).exists(), slug)
            self.assertNotIn("/journal/ko/%s/" % slug, sm, slug)


class RepoState(unittest.TestCase):
    def test_id_journal_is_on_hold(self):
        hold = json.loads((REPO / "content/journal/hold.json").read_text(encoding="utf-8"))
        self.assertIn("id", hold)
        self.assertEqual([f.name for f in (REPO / "content/journal/id").glob("*.md")] if (REPO / "content/journal/id").is_dir() else [], [])
        self.assertFalse((REPO / "journal/id").exists())

    def test_committed_site_builds_clean(self):
        r = run(REPO, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        errs, _ = check_sitemap.check(REPO)
        self.assertEqual(errs, [])

    # the crisis numbers each language prints (verified items only), exactly as confirmed from official pages by Dane on 2026-10-25
    # (room note 20261025-225603). vi has no official adult line, so it stays draft and prints none. id is on hold (hold.json).
    CONFIRMED = {
        "ko": ["109"],
        "en": ["988", "9-8-8", "116 123", "13 11 14"],
        "zh": ["12356"],
        "es": ["024", "988", "800 911 2000"],
        "pt": ["188", "808 24 24 24"],
        "fr": ["3114", "9-8-8", "143", "0800 32 123"],
        "de": ["0800 111 0 111", "0800 111 0 222", "116 123", "142", "143"],
        "ja": ["0570-064-556", "0120-279-338", "0120-783-556", "0120-061-338"],
        "ru": ["8-800-2000-122", "+7 (495) 989-50-50"],
        "vi": [],
        "id": ["119 ext. 8"],
    }

    def test_each_language_prints_exactly_the_confirmed_numbers(self):
        d = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))["lines"]
        self.assertEqual(set(self.CONFIRMED), set(d))
        for l, want in self.CONFIRMED.items():
            got = [it["number"] for r in d[l]["regions"] for it in r["items"] if it["status"] == "verified"]
            self.assertEqual(got, want, l)
            for r in d[l]["regions"]:
                for it in r["items"]:
                    if it["status"] == "verified":
                        self.assertRegex(it["checked_on"], r"^2026-10-2[2-9]$", (l, it["number"]))
                        self.assertTrue(it.get("source", "").startswith("https://"), (l, it["number"]))
        for l in ("en", "zh", "es", "pt", "fr", "de", "ja", "ru"):
            self.assertEqual(d[l]["status"], "verified", l)
            self.assertEqual(d[l]["reviewed_on"], "2026-10-25", l)
        # vi stays draft: no official adult crisis line was found (Dane, 2026-10-25) -> its posts stay `draft: true`
        self.assertEqual(d["vi"]["status"], "draft")
        self.assertEqual(d["id"]["status"], "draft")

    def test_safety_data_covers_all_languages(self):
        d = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))
        self.assertEqual(list(d["text"]), LANGS)
        self.assertEqual(list(d["lines"]), LANGS)
        ui = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
        self.assertEqual([l for l in ui if not l.startswith("_")], LANGS)


if __name__ == "__main__":
    unittest.main()


class Scheduled(Base):
    """publish_at: a post goes live only in a build whose clock (--now) has reached it; the committed output ignores the clock"""

    def write(self, slug, publish_at, extra=""):
        write_post(self.tmp, "ko", slug, text=POST.replace("slug: hello", "slug: " + slug).replace("2026-10-22", publish_at[:10]) % dict(
            l="ko", extra="bible_version: WEB\npublish_at: %s\n%s" % (publish_at, extra)))

    def setUp(self):
        super().setUp()
        write_post(self.tmp, "ko", "now-post", text=POST.replace("slug: hello", "slug: now-post") % dict(l="ko", extra="bible_version: WEB\n"))
        self.write("future-post", "2026-10-24 11:00")
        self.write("past-post", "2026-10-23 09:00")

    def sitemap(self):
        return self.page("sitemap.xml")

    def test_plain_build_holds_every_scheduled_post(self):
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertTrue((self.tmp / "journal/ko/now-post/index.html").is_file())
        for slug in ("future-post", "past-post"):  # no clock -> deterministic, even for a time that has passed
            self.assertFalse((self.tmp / "journal/ko" / slug).exists(), slug)
            for f in ("sitemap.xml", "llms.txt", "journal/index.html", "journal/feed.xml", "ko/index.html"):
                self.assertNotIn(slug, self.page(f), (slug, f))
        self.assertEqual(check_sitemap.check(self.tmp)[0], [])

    def test_future_post_is_not_published_and_past_post_is(self):
        r = run(self.tmp, "--now", "2026-10-23 18:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / "journal/ko/past-post/index.html").is_file())
        self.assertFalse((self.tmp / "journal/ko/future-post").exists())
        for f in ("sitemap.xml", "llms.txt", "journal/index.html", "journal/feed.xml", "ko/index.html", "journal/ko/index.html"):
            self.assertNotIn("future-post", self.page(f), f)
        self.assertIn("/journal/ko/past-post/", self.page("sitemap.xml"))
        self.assertIn("/journal/ko/past-post/", self.page("llms.txt"))

    def test_the_sitemap_follows_the_same_rule(self):
        for now, want in (("2026-10-23 18:00", {"past-post"}), ("2026-10-24 11:00", {"past-post", "future-post"})):
            self.assertEqual(run(self.tmp, "--now", now).returncode, 0)
            self.assertEqual(sitemap_errors_at(self.tmp, now), [], now)
            sm = self.sitemap()
            for slug in ("past-post", "future-post"):
                self.assertEqual("/journal/ko/%s/" % slug in sm, slug in want, (now, slug))
        # a sitemap built at 11:00 does not pass a check made as of an earlier clock (the page is not due yet)
        errs, _ = check_sitemap.check(self.tmp, bj.parse_when("2026-10-23 18:00"))
        self.assertTrue([e for e in errs if "future-post" in e], errs)
        # ... and one built earlier lacks the post a later clock requires
        self.assertEqual(run(self.tmp, "--now", "2026-10-23 18:00").returncode, 0)
        errs, _ = check_sitemap.check(self.tmp, bj.parse_when("2026-10-24 11:00"))
        self.assertIn("missing from sitemap: https://still.ipe.rest/journal/ko/future-post/", errs)

    def test_the_boundary_is_inclusive_and_the_clock_is_kst(self):
        self.assertEqual(run(self.tmp, "--now", "2026-10-24 10:59").returncode, 0)
        self.assertFalse((self.tmp / "journal/ko/future-post").exists())
        self.assertEqual(run(self.tmp, "--now", "2026-10-24T11:00:00+09:00").returncode, 0)
        self.assertTrue((self.tmp / "journal/ko/future-post/index.html").is_file())
        self.assertEqual(run(self.tmp, "--now", "2026-10-24T01:59:00Z").returncode, 0)  # 10:59 KST: the page is swept again
        self.assertFalse((self.tmp / "journal/ko/future-post").exists())
        self.assertEqual(run(self.tmp, "--now", "2026-10-24T02:00:00Z").returncode, 0)  # = 11:00 KST
        self.assertTrue((self.tmp / "journal/ko/future-post/index.html").is_file())

    def test_draft_wins_over_publish_at(self):
        self.write("future-post", "2026-10-24 11:00", "draft: true\n")
        self.assertEqual(run(self.tmp, "--now", "2099-01-01 00:00").returncode, 0)
        self.assertFalse((self.tmp / "journal/ko/future-post").exists())

    def test_check_ignores_the_clock_but_a_due_build_is_not_fresh(self):
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check").returncode, 0)  # committed output does not go stale as time passes
        self.assertEqual(run(self.tmp, "--check", "--strict-safety").returncode, 0)
        self.assertEqual(run(self.tmp, "--now", "2099-01-01 00:00").returncode, 0)  # what the runner builds (never committed)
        r = run(self.tmp, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("out of date", r.stderr)

    def test_strict_safety_applies_to_scheduled_posts_once_due(self):
        write_post(self.tmp, "vi", "future-vi", text=POST.replace("slug: hello", "slug: future-vi").replace("2026-10-22", "2026-10-24") % dict(
            l="vi", extra="bible_version: WEB\ntranslation_of: ko\npublish_at: 2026-10-24 11:00\n"))
        self.write("future-vi", "2026-10-24 11:00")  # the ko original of that slug
        self.assertEqual(run(self.tmp).returncode, 0)
        r = run(self.tmp, "--check", "--strict-safety")
        self.assertEqual(r.returncode, 0, r.stderr)  # held -> vi is not a published language yet
        r = run(self.tmp, "--check", "--strict-safety", "--now", "2026-10-24 11:00")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("crisis lines for vi are still `draft`", r.stderr)

    def test_a_translation_may_not_outrun_its_original(self):
        write_post(self.tmp, "en", "future-post", text=POST.replace("slug: hello", "slug: future-post").replace("2026-10-22", "2026-10-23") % dict(
            l="en", extra="bible_version: WEB\ntranslation_of: ko\n"))
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("translation_of ko refers to a draft or not-yet-published post", r.stderr)

    def test_bad_values(self):
        self.write("bad-time", "2026-10-24 11:00")
        for bad, msg in (("tomorrow", "publish_at must be"), ("2026-10-25 11:00", "is not on the post's date")):
            self.write("bad-time", "2026-10-24 11:00")
            f = self.tmp / "content/journal/ko/bad-time.md"
            f.write_text(f.read_text(encoding="utf-8").replace("publish_at: 2026-10-24 11:00", "publish_at: " + bad), encoding="utf-8")
            r = run(self.tmp)
            self.assertEqual(r.returncode, 1, bad)
            self.assertIn(msg, r.stderr, bad)
        self.assertEqual(run(self.tmp, "--now", "later").returncode, 1)

    def test_scheduled_post_in_a_held_language_is_an_error(self):
        (self.tmp / "content/journal/hold.json").write_text(json.dumps({"ko": "x"}), encoding="utf-8")
        r = run(self.tmp, "--now", "2099-01-01 00:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("on hold", r.stderr)


class PostTime(Base):
    """the time of day (KST, 24 h, HH:MM, no seconds) next to the date; `publish_at` / `published_at` are its sources; unknown -> date only"""

    def write(self, slug, extra, lang="ko", date="2026-10-24"):
        write_post(self.tmp, lang, slug, text=POST.replace("slug: hello", "slug: " + slug).replace("2026-10-22", date) % dict(l=lang, extra="bible_version: WEB\n" + extra))

    def eyebrow(self, rel):
        return re.search(r'<p class="eyebrow">(.*?)</p>', self.page(rel), re.S).group(1)

    def ld(self, rel):
        return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', self.page(rel), re.S).group(1))

    def test_zero_padded_hh_mm_without_seconds_in_every_language(self):
        for l in LANGS:  # seconds in the source are cut
            self.write("t", "published_at: 2026-10-24 09:09:45\n" + ("" if l in ("ko", "en") else "translation_of: en\n"), lang=l)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        for l in LANGS:
            want = '<time datetime="2026-10-24T09:09:00+09:00" data-ipe-time>%s&nbsp;09:09 KST</time>' % bj.fmt_date(__import__("datetime").date(2026, 10, 24), l)
            self.assertIn(want, self.page("journal/%s/t/index.html" % l), l)  # article page
            self.assertIn(want, self.page("journal/%s/index.html" % l), l)  # list card
            visible = re.sub(r"<[^>]+>", "", self.eyebrow("journal/%s/t/index.html" % l))
            self.assertNotRegex(visible, r"\d\d:\d\d:\d\d", l)  # visible text: HH:MM only, no seconds

    def test_two_digit_hour_and_minute(self):
        self.write("a", "published_at: 2026-10-24 07:05\n")
        self.write("b", "published_at: 2026-10-24 17:00\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertIn("2026년 10월 24일&nbsp;07:05 KST</time>", self.page("journal/ko/a/index.html"))
        self.assertIn("2026년 10월 24일&nbsp;17:00 KST</time>", self.page("journal/ko/b/index.html"))

    def test_machine_dates_carry_the_kst_offset(self):
        self.write("a", "published_at: 2026-10-24 11:00\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        iso = "2026-10-24T11:00:00+09:00"
        d = self.ld("journal/ko/a/index.html")
        self.assertEqual((d["datePublished"], d["dateModified"]), (iso, iso))
        h = self.page("journal/ko/a/index.html")
        self.assertIn('<meta property="article:published_time" content="%s">' % iso, h)
        self.assertIn('<meta property="article:modified_time" content="%s">' % iso, h)
        lst = self.ld("journal/ko/index.html")
        self.assertEqual(lst["blogPost"][0]["datePublished"], iso)
        self.assertIn("<pubDate>Sat, 24 Oct 2026 11:00:00 +0900</pubDate>", self.page("journal/feed.xml"))
        self.assertIn('<time datetime="%s" data-ipe-time>' % iso, self.page("ko/index.html"))  # home card

    def test_an_explicit_updated_date_stays_as_written(self):
        self.write("a", "published_at: 2026-10-24 11:00\nupdated: 2026-10-25\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        d = self.ld("journal/ko/a/index.html")
        self.assertEqual((d["datePublished"], d["dateModified"]), ("2026-10-24T11:00:00+09:00", "2026-10-25"))

    def test_publish_at_is_shown_once_the_scheduled_post_is_live(self):
        self.write("s", "publish_at: 2026-10-24 17:00\n")
        self.assertEqual(run(self.tmp, "--now", "2026-10-24 17:00").returncode, 0)
        h = self.page("journal/ko/s/index.html")
        self.assertIn('<time datetime="2026-10-24T17:00:00+09:00" data-ipe-time>2026년 10월 24일&nbsp;17:00 KST</time>', h)
        self.assertEqual(self.ld("journal/ko/s/index.html")["datePublished"], "2026-10-24T17:00:00+09:00")

    def test_unknown_time_shows_the_date_only(self):
        self.write("n", "")
        self.assertEqual(run(self.tmp).returncode, 0)
        h = self.page("journal/ko/n/index.html")
        self.assertIn('<time datetime="2026-10-24">2026년 10월 24일</time>', h)
        self.assertNotRegex(self.eyebrow("journal/ko/n/index.html"), r"\d\d:\d\d")
        self.assertEqual(self.ld("journal/ko/n/index.html")["datePublished"], "2026-10-24")
        self.assertIn("<pubDate>Sat, 24 Oct 2026 09:00:00 +0900</pubDate>", self.page("journal/feed.xml"))  # as before: never an invented time

    def test_same_day_posts_are_listed_latest_time_first(self):
        self.write("early", "published_at: 2026-10-24 09:00\n")
        self.write("late", "published_at: 2026-10-24 17:00\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        h = self.page("journal/ko/index.html")
        self.assertLess(h.index("/journal/ko/late/"), h.index("/journal/ko/early/"))

    def test_bad_published_at(self):
        for extra, msg in (("published_at: noon\n", "published_at must be"),
                           ("published_at: 2026-10-25 11:00\n", "is not on the post's date"),
                           ("published_at: 2026-10-24 11:00\npublish_at: 2026-10-24 11:00\n", "both set")):
            self.write("bad", extra)
            r = run(self.tmp)
            self.assertEqual(r.returncode, 1, extra)
            self.assertIn(msg, r.stderr, extra)

    def test_check_passes_and_the_sitemap_stays_valid(self):
        self.write("a", "published_at: 2026-10-24 11:00\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check").returncode, 0)
        self.assertEqual(check_sitemap.check(self.tmp)[0], [])

    def test_the_first_posts_have_their_real_times(self):
        for slug, when in (("commute-get-off-early", "2026-10-23 18:18"), ("evening-after-the-meeting", "2026-10-23 18:18"),
                           ("first-day-at-the-clinic", "2026-10-24 11:00"), ("three-am-counting-hours", "2026-10-24 17:00")):
            p = bj.parse_post(REPO / "content/journal/ko" / (slug + ".md"))
            self.assertEqual(bj.post_when(p).strftime("%Y-%m-%d %H:%M"), when, slug)
        for slug in ("commute-get-off-early", "evening-after-the-meeting"):
            h = (REPO / "journal/ko" / slug / "index.html").read_text(encoding="utf-8")
            self.assertIn('<time datetime="2026-10-23T18:18:00+09:00" data-ipe-time>2026년 10월 23일&nbsp;18:18 KST</time>', h, slug)
