"""SEO guide v1 P0-10: the site has its own 404.html (noindex, links to the home page and the journal, status 404 is GitHub Pages' own),
and every link on it leads to a page that exists in the full site. Run: python3 -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seo_crawl import REPO, Page, full_site  # noqa: E402

SITE = "https://still.ipe.rest"


class NotFoundPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root, cls.pages = full_site()
        cls.p = Page(SITE + "/404.html", (REPO / "404.html").read_text(encoding="utf-8"))

    def test_it_is_noindex_follow_and_has_no_canonical(self):
        self.assertEqual(self.p.robots.replace(" ", ""), "noindex,follow")
        self.assertEqual(self.p.canonicals, [])
        self.assertEqual(self.p.hreflangs, [])
        self.assertEqual(self.p.lang, "en")
        self.assertEqual(self.p.h1, 1)

    def test_it_links_home_and_the_journal(self):
        hrefs = {a["href"] for a in self.p.anchors}
        self.assertIn("/", hrefs)
        self.assertIn("/journal/", hrefs)

    def test_every_link_on_it_leads_to_a_page_that_exists(self):
        for a in self.p.anchors:
            href = a["href"]
            self.assertTrue(href.startswith("/") and not href.startswith("//"), href)  # site-relative: works on any host the page is served from
            self.assertTrue((self.root / href.strip("/") / "index.html").is_file(), "404.html links to a page that does not exist: " + href)

    def test_it_offers_a_journal_link_only_for_languages_that_have_a_journal(self):
        journal_langs = set(re.findall(r'href="/journal/([a-z]{2})/"', (REPO / "404.html").read_text(encoding="utf-8")))
        built = {d.name for d in (self.root / "journal").iterdir() if d.is_dir() and d.name != "page"}
        self.assertEqual(journal_langs, built)  # a language added to (or held back from) the journal changes this list on purpose

    def test_the_404_is_a_root_file_next_to_the_cname(self):
        self.assertTrue((REPO / "404.html").is_file())
        self.assertTrue((REPO / "CNAME").is_file())
        self.assertFalse((self.root / "404.html").is_dir())
        self.assertNotIn("404", (self.root / "sitemap.xml").read_text(encoding="utf-8"))
        self.assertNotIn("404.html", (self.root / "robots.txt").read_text(encoding="utf-8"))

    def test_the_deploy_ships_it(self):
        wf = (REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertIn("rsync -a", wf)
        self.assertNotIn("--exclude='/404", wf)  # the assembled site is the repo root minus sources only


if __name__ == "__main__":
    unittest.main()
