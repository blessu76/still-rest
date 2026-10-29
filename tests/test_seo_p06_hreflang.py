"""SEO guide v1 P0-6: hreflang is reciprocal, every page lists itself, there is exactly one x-default, every target is a real indexable
page, the html <link>s and the sitemap carry the same set, and the private journal languages (vi: draft only; id: on hold) never appear in a
journal hreflang cluster or the sitemap's journal rows. Checked on the committed pages and on the full site as the deploy runner builds it.
Run: python3 -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_sitemap  # noqa: E402
from seo_crawl import committed_site, full_site  # noqa: E402

# the journal languages that are live (decision 2026-10-29): changing this set is a deliberate act, not a side effect of a build
LIVE_JOURNAL_LANGS = {"ko", "en", "ja", "zh", "es", "fr", "de", "pt", "ru"}
PRIVATE_JOURNAL_LANGS = ("vi", "id")
SITE = "https://still.ipe.rest"


class Checks:
    sites = ()

    def each(self):
        for name, (root, pages) in self.sites:
            self.assertGreater(len(pages), 30, name)
            for url, p in pages.items():
                if p.hreflangs:
                    yield name, pages, url, p

    def test_each_page_lists_itself_once_with_one_x_default_and_no_duplicate_language(self):
        n = 0
        for name, pages, url, p in self.each():
            n += 1
            langs = [l for l, _ in p.hreflangs]
            self.assertEqual(len(langs), len(set(langs)), (name, url, "duplicate hreflang"))
            self.assertEqual(langs.count("x-default"), 1, (name, url))
            self.assertIn(url, [h for _, h in p.hreflangs], (name, url, "does not list itself"))
            for lang, href in p.hreflangs:
                self.assertRegex(href, r"^https://still\.ipe\.rest/\S*/$|^https://still\.ipe\.rest/$", (name, url, lang))
        self.assertGreater(n, 30)

    def test_every_target_is_a_real_indexable_page(self):
        for name, pages, url, p in self.each():
            for lang, href in p.hreflangs:
                self.assertIn(href, pages, (name, url, lang, "target page does not exist"))
                self.assertTrue(pages[href].indexable, (name, url, lang, "target is noindex"))

    def test_reciprocal(self):
        for name, pages, url, p in self.each():
            for lang, href in p.hreflangs:
                if href == url:
                    continue
                back = [h for _, h in pages[href].hreflangs]
                self.assertIn(url, back, "%s: %s -> %s (%s) but %s does not list %s back" % (name, url, href, lang, href, url))

    def test_pages_of_one_cluster_carry_the_same_set(self):
        for name, pages, url, p in self.each():
            mine = set(p.hreflangs)
            for lang, href in p.hreflangs:
                if lang == "x-default" or href == url:
                    continue
                self.assertEqual(set(pages[href].hreflangs), mine, "%s: %s and %s declare different sets" % (name, url, href))

    def test_hreflang_codes_are_the_language_of_the_target_page(self):
        for name, pages, url, p in self.each():
            for lang, href in p.hreflangs:
                if lang != "x-default":
                    self.assertEqual(pages[href].lang, lang, (name, url, href))

    def test_journal_clusters_name_only_live_languages(self):
        seen = 0
        for name, pages, url, p in self.each():
            if "/journal/" not in url:
                continue
            seen += 1
            langs = {l for l, _ in p.hreflangs if l != "x-default"}
            self.assertLessEqual(langs, LIVE_JOURNAL_LANGS, (name, url))
            for l in PRIVATE_JOURNAL_LANGS:
                self.assertNotIn(l, langs, (name, url))
            for _, href in p.hreflangs:
                self.assertNotRegex(href, r"/journal/(vi|id)/", (name, url))
        self.assertGreater(seen, 0)

    def test_x_default_of_a_post_is_english_else_the_original(self):
        for name, pages, url, p in self.each():
            m = re.fullmatch(SITE + r"/journal/([a-z]{2})/([a-z0-9-]+)/", url)
            if not m or m.group(2) == "page":
                continue
            d = dict(p.hreflangs)
            expect = d.get("en") or d.get("ko")
            self.assertEqual(d["x-default"], expect, (name, url))

    def test_private_languages_have_no_journal_pages_and_are_not_in_the_sitemap(self):
        for name, (root, pages) in self.sites:
            for l in PRIVATE_JOURNAL_LANGS:
                self.assertFalse((root / "journal" / l).exists(), (name, l))
            sm = (root / "sitemap.xml").read_text(encoding="utf-8")
            self.assertEqual(re.findall(r"/journal/(?:vi|id)/", sm), [], name)
            live = {d.name for d in (root / "journal").iterdir() if d.is_dir() and d.name != "page"}
            self.assertLessEqual(live, LIVE_JOURNAL_LANGS, name)

    def test_html_hreflang_and_sitemap_carry_the_same_set(self):
        for name, (root, pages) in self.sites:
            errs = [e for e in check_sitemap.check(root, check_sitemap.parse_when("2026-10-29 23:59") if name == "full" else None)[0]]
            self.assertEqual(errs, [], name)


class CommittedPages(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("committed", committed_site()),)


class FullSitePages(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("full", full_site()),)

    def test_the_full_site_has_exactly_the_nine_live_journal_languages(self):
        root, pages = self.sites[0][1]
        self.assertEqual({d.name for d in (root / "journal").iterdir() if d.is_dir() and d.name != "page"}, LIVE_JOURNAL_LANGS)
        # a 9-way cluster per post: nine language alternates + x-default
        post = pages[SITE + "/journal/ko/thursday-evening-earbuds-ran-out/"]
        self.assertEqual(sorted(l for l, _ in post.hreflangs), sorted(LIVE_JOURNAL_LANGS | {"x-default"}))


if __name__ == "__main__":
    unittest.main()
