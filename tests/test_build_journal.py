"""Tests for scripts/build_journal.py — run: python3 -m unittest discover -s tests"""
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
    for f in ("sitemap.xml", "llms.txt", "og-image.png"):
        shutil.copy(REPO / f, tmp / f)
    shutil.copytree(REPO / "content/home", tmp / "content/home")
    (tmp / "content/journal").mkdir(parents=True)
    for page in ("privacy", "terms"):  # legal pages listed in the sitemap
        (tmp / page).mkdir()
        (tmp / page / "index.html").write_text("x")
    for f in ("safety.json", "ui.json"):
        shutil.copy(REPO / "content/journal" / f, tmp / "content/journal" / f)
    return tmp


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
            self.assertIn('data-crisis-lines="draft"', h, l)
            self.assertIn("https://findahelpline.com", h, l)
            self.assertIn('class="bible-version"', h, l)
            self.assertIn("WEB", h, l)
            self.assertEqual(h.count(bj.esc(txt["disclaimer"])), 2, l)  # under the title and again after the text
            for r in data["lines"][l]["regions"]:
                for it in r["items"]:
                    self.assertIn(bj.esc(it["number"]), h, l)
                    if it.get("tel"):
                        self.assertIn('href="tel:%s"' % it["tel"], h, l)

    def test_korean_lines_placeholder(self):
        h = self.page("journal/ko/hello/index.html")
        self.assertIn("자살예방상담전화", h)
        self.assertIn("1577-0199", h)

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
        self.assertEqual(len(locs), 12 + 2 + 1 + 11 + 11)  # home + privacy/terms + hub + lists + posts

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

    def test_strict_safety_gate(self):
        write_post(self.tmp, "ko", extra="bible_version: x\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check").returncode, 0)  # the normal check allows draft crisis lines
        r = run(self.tmp, "--check", "--strict-safety")
        self.assertEqual(r.returncode, 1)
        self.assertIn("crisis lines for ko are still `draft`", r.stderr)
        p = self.tmp / "content/journal/safety.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["lines"]["ko"]["status"] = "verified"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check", "--strict-safety").returncode, 0)  # only languages with posts are gated

    def test_strict_safety_passes_without_posts(self):
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(run(self.tmp, "--check", "--strict-safety").returncode, 0)


class RepoState(unittest.TestCase):
    def test_committed_site_builds_clean(self):
        r = run(REPO, "--check")
        self.assertEqual(r.returncode, 0, r.stderr)
        errs, _ = check_sitemap.check(REPO)
        self.assertEqual(errs, [])

    def test_safety_data_covers_all_languages(self):
        d = json.loads((REPO / "content/journal/safety.json").read_text(encoding="utf-8"))
        self.assertEqual(list(d["text"]), LANGS)
        self.assertEqual(list(d["lines"]), LANGS)
        ui = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
        self.assertEqual([l for l in ui if not l.startswith("_")], LANGS)


if __name__ == "__main__":
    unittest.main()
