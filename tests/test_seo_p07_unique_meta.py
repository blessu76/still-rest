"""SEO guide v1 P0-7: every indexable page has its own <title> and meta description (no repeat inside a language), exactly one <h1>,
and an html lang that is the language of the page's address. Checked on the committed pages and on the full site as the deploy runner builds it.
Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from seo_crawl import REPO, Page, committed_site, full_site  # noqa: E402
from site_common import LANGS, SITE  # noqa: E402


def expected_lang(url):
    """the language of a page from its address: /<lang>/…, /journal/<lang>/…; everything else (/, /journal/, /privacy/, hub pages) is English."""
    parts = url[len(SITE) + 1:].strip("/").split("/")
    if parts and parts[0] in LANGS:
        return parts[0]
    if len(parts) > 1 and parts[0] == "journal" and parts[1] in LANGS:
        return parts[1]
    return "en"


class Checks:
    sites = ()

    def each(self):
        for name, (root, pages) in self.sites:
            self.assertGreater(len(pages), 30, name)
            for url, p in pages.items():
                yield name, pages, url, p

    def test_title_and_description_exist(self):
        for name, pages, url, p in self.each():
            self.assertTrue((p.title or "").strip(), (name, url, "no <title>"))
            self.assertTrue((p.description or "").strip(), (name, url, "no meta description"))

    def test_no_title_repeats_inside_a_language(self):
        for key in ("title", "description"):
            for name, (root, pages) in self.sites:
                seen = defaultdict(list)
                for url, p in pages.items():
                    if p.indexable:
                        seen[(p.lang, (p.title if key == "title" else p.description).strip())].append(url)
                self.assertEqual({k[0] + ": " + k[1][:50]: v for k, v in seen.items() if len(v) > 1}, {}, (name, key))

    def test_exactly_one_h1(self):
        for name, pages, url, p in self.each():
            self.assertEqual(p.h1, 1, (name, url))

    def test_the_404_page_has_one_h1_and_its_own_title(self):
        p = Page(SITE + "/404.html", (REPO / "404.html").read_text(encoding="utf-8"))
        self.assertEqual(p.h1, 1)
        self.assertTrue(p.title)
        self.assertTrue(p.description)

    def test_html_lang_is_the_language_of_the_address(self):
        for name, pages, url, p in self.each():
            self.assertEqual(p.lang, expected_lang(url), (name, url))

    def test_the_title_names_the_site_and_og_title_is_the_title(self):
        for name, pages, url, p in self.each():
            if not p.indexable:
                continue
            self.assertEqual(p.first("og:title"), p.title.strip(), (name, url))
            self.assertIn("still()", p.title, (name, url))

    def test_a_post_title_is_its_headline_plus_the_journal_suffix(self):
        n = 0
        for name, pages, url, p in self.each():
            post = p.blog_posting()
            if post:
                n += 1
                self.assertTrue(p.title.startswith(post["headline"]), (name, url))
                self.assertEqual(p.h1_text.strip(), post["headline"], (name, url))
        if self.sites[0][0] == "full":
            self.assertGreater(n, 100)


class CommittedPages(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("committed", committed_site()),)


class FullSitePages(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("full", full_site()),)


if __name__ == "__main__":
    unittest.main()
