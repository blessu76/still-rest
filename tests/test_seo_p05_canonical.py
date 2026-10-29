"""SEO guide v1 P0-5: every page has a self-referencing absolute https canonical, robots defaults to index, and noindex exists only on pages
that are meant to be left out (the 404 page, empty lists, redirect stubs). Checked on the committed pages and on the full site as the deploy
runner builds it. Run: python3 -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seo_crawl import REPO, committed_site, full_site  # noqa: E402


class Checks:
    """the same checks on any set of built pages; subclasses provide self.sites = ((name, (root, {url: Page})), ...)"""

    def each(self):
        for name, (root, pages) in self.sites:
            self.assertGreater(len(pages), 30, name)
            for url, p in pages.items():
                yield name, url, p

    def test_every_page_has_exactly_one_canonical_and_it_is_itself(self):
        for name, url, p in self.each():
            if p.indexable:
                self.assertEqual(p.canonicals, [url], (name, url))
            else:  # an intentionally left-out page may carry none, or point at its target (redirect stub), never at something else of this site's index
                self.assertLessEqual(len(p.canonicals), 1, (name, url))

    def test_canonical_is_absolute_https_on_the_site(self):
        for name, url, p in self.each():
            for c in p.canonicals:
                self.assertRegex(c, r"^https://still\.ipe\.rest/[^?#\s]*$", (name, url))
                self.assertNotIn("//", c[len("https://"):], (name, url))
                self.assertTrue(c.endswith("/"), (name, url))  # the directory index: one address per page

    def test_robots_meta_is_present_and_index_by_default(self):
        for name, url, p in self.each():
            self.assertTrue(p.robots, (name, url))
            if p.indexable:
                self.assertIn("index", p.robots.lower(), (name, url))
                self.assertNotIn("nofollow", p.robots.lower(), (name, url))

    def test_noindex_only_where_it_is_meant(self):
        for name, url, p in self.each():
            if p.indexable:
                continue
            empty_list = re.fullmatch(r"https://still\.ipe\.rest/journal/([a-z]{2}/)?(page/\d+/)?", url) is not None
            redirect_stub = p.title == "Moved — still()"
            self.assertTrue(empty_list or redirect_stub, "unexpected noindex page: %s (%s)" % (url, p.robots))

    def test_noindex_pages_are_not_in_the_sitemap(self):
        for name, (root, pages) in self.sites:
            sm = (root / "sitemap.xml").read_text(encoding="utf-8")
            for url, p in pages.items():
                if not p.indexable:
                    self.assertNotIn("<loc>%s</loc>" % url, sm, (name, url))

    def test_the_404_page_is_the_one_noindex_page_with_no_canonical(self):
        p404 = (REPO / "404.html").read_text(encoding="utf-8")
        self.assertRegex(p404, r'<meta name="robots" content="noindex[^"]*">')
        self.assertNotIn('rel="canonical"', p404)  # a 404 URL has no address of its own to claim
        self.assertEqual(len(re.findall(r"<h1[ >]", p404)), 1)
        self.assertIn('href="/"', p404)
        self.assertIn('href="/journal/"', p404)
        # the Pages 404 is an html file at the root, not a directory index
        self.assertFalse((REPO / "404").exists())

    def test_no_page_of_the_full_site_is_noindex_except_empty_lists(self):
        root, pages = full_site()
        self.assertEqual([u for u, p in pages.items() if not p.indexable], [])  # with posts in every list there is nothing to hide


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
