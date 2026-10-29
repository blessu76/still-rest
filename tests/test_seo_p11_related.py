"""SEO guide v1 P1-1: under every article — previous / next story and "more stories" (the newest 3 posts of the SAME language, the article itself
left out, never a post that is not public yet). Run: python3 -m unittest discover -s tests"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from seo_crawl import REPO, committed_site, full_site  # noqa: E402
from site_common import LANGS  # noqa: E402
from test_build_journal import Base, run  # noqa: E402
from test_journal_paging import put, series  # noqa: E402

def more_of(page):
    """-> (prev slug|None, next slug|None, [related slugs]) of an article page"""
    nav = re.search(r'<nav class="post-nav".*?</nav>', page, re.S)
    nav = nav.group(0) if nav else ""
    rel = re.search(r'<section class="related".*?</section>', page, re.S)
    rel = rel.group(0) if rel else ""
    slug = lambda m: m.group(1) if m else None
    return (slug(re.search(r'rel="prev" href="/journal/[a-z]{2}/([a-z0-9-]+)/"', nav)),
            slug(re.search(r'rel="next" href="/journal/[a-z]{2}/([a-z0-9-]+)/"', nav)),
            re.findall(r'<li><a href="/journal/[a-z]{2}/([a-z0-9-]+)/">', rel))


class Fixture(Base):
    def more(self, lang, slug):
        return more_of(self.page("journal/%s/%s/index.html" % (lang, slug)))

    def test_previous_next_and_the_newest_three_others(self):
        series(self.tmp, 5, langs=("ko",))
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(self.more("ko", "p05"), ("p04", None, ["p04", "p03", "p02"]))
        self.assertEqual(self.more("ko", "p03"), ("p02", "p04", ["p05", "p04", "p02"]))
        self.assertEqual(self.more("ko", "p01"), (None, "p02", ["p05", "p04", "p03"]))

    def test_only_the_pages_own_language(self):
        series(self.tmp, 4, langs=("ko", "en"), counts={"en": 2})
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(self.more("en", "p02"), ("p01", None, ["p01"]))  # en has only two posts: nothing from ko is borrowed
        self.assertEqual(self.more("ko", "p02"), ("p01", "p03", ["p04", "p03", "p01"]))
        for slug in ("p01", "p02"):
            tail = self.page("journal/en/%s/index.html" % slug).split('data-safety="block"')[1]
            self.assertNotRegex(tail.split('class="article-foot"')[0], r'href="/journal/ko/')

    def test_a_language_with_one_post_gets_no_empty_section(self):
        series(self.tmp, 1, langs=("ko",))
        self.assertEqual(run(self.tmp).returncode, 0)
        h = self.page("journal/ko/p01/index.html")
        self.assertNotIn('class="post-nav"', h)
        self.assertNotIn('class="related"', h)
        self.assertIn('class="article-foot"', h)

    def test_two_posts_link_each_other_once_each_way(self):
        series(self.tmp, 2, langs=("ko",))
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(self.more("ko", "p01"), (None, "p02", ["p02"]))
        self.assertEqual(self.more("ko", "p02"), ("p01", None, ["p01"]))

    def test_a_post_that_is_not_public_yet_is_never_linked(self):
        series(self.tmp, 3, langs=("ko",))
        put(self.tmp, "ko", "later", "2026-10-30", "publish_at: 2026-10-30 10:06\n")
        put(self.tmp, "ko", "draft", "2026-09-10", "draft: true\n")
        for args, nxt, rel in (((), None, ["p02", "p01"]),
                               (("--now", "2026-10-30 10:05"), None, ["p02", "p01"]),  # one minute before it is due
                               (("--now", "2026-10-30 10:06"), "later", ["later", "p02", "p01"])):
            self.assertEqual(run(self.tmp, *args).returncode, 0, args)
            self.assertEqual(self.more("ko", "p03")[1:], (nxt, rel), args)
            self.assertNotIn("/journal/ko/draft/", self.page("journal/ko/p03/index.html"), args)

    def test_the_safety_block_still_comes_first(self):
        series(self.tmp, 3, langs=("ko",))
        self.assertEqual(run(self.tmp).returncode, 0)
        h = self.page("journal/ko/p02/index.html")
        self.assertLess(h.index('data-safety="block"'), h.index('class="post-nav"'))
        self.assertLess(h.index('class="related"'), h.index('class="article-foot"'))
        self.assertIn('id="help"', h)
        self.assertEqual(len(re.findall(r"<h1[ >]", h)), 1)

    def test_all_eleven_languages_have_the_strings(self):
        ui = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
        for l in LANGS:
            for k in ("prev_post", "next_post", "related"):
                self.assertTrue(ui[l].get(k), (l, k))
        self.assertEqual(len({ui[l]["related"] for l in LANGS}), len(LANGS))  # nobody was left with the English words


class Site:
    sites = ()

    def articles(self):
        for name, (root, pages) in self.sites:
            for url, p in pages.items():
                m = re.fullmatch(r"https://still\.ipe\.rest/journal/([a-z]{2})/([a-z0-9-]+)/", url)
                if m and m.group(2) != "page":
                    yield name, pages, url, m.group(1), m.group(2), (root / "journal" / m.group(1) / m.group(2) / "index.html").read_text(encoding="utf-8")

    def test_every_article_links_other_articles_of_its_language(self):
        n = 0
        for name, pages, url, lang, slug, html in self.articles():
            n += 1
            same = [u for u in pages if re.fullmatch(r"https://still\.ipe\.rest/journal/%s/(?!page/)[a-z0-9-]+/" % lang, u)]
            prev, nxt, rel = more_of(html)
            self.assertEqual(len(rel), min(3, len(same) - 1), (name, url))  # all the others when there are fewer than three
            self.assertEqual(len(set(rel)), len(rel), (name, url))
            for x in {x for x in (prev, nxt, *rel) if x}:
                self.assertNotEqual(x, slug, (name, url))
                self.assertIn("https://still.ipe.rest/journal/%s/%s/" % (lang, x), pages, (name, url, x, "linked page does not exist in the same language"))
        self.assertGreater(n, 1)


class CommittedPages(Site, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("committed", committed_site()),)


class FullSitePages(Site, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("full", full_site()),)

    def test_at_least_three_other_articles_on_every_article_page(self):
        short = []
        for name, pages, url, lang, slug, html in self.articles():
            prev, nxt, rel = more_of(html)
            if len({x for x in (prev, nxt, *rel) if x}) < 3:
                short.append(url)
        self.assertEqual(short, [])

    def test_the_newest_three_are_the_newest_of_that_language(self):
        root, pages = self.sites[0][1]
        # the three newest ko posts as of the 2026-10-29 23:59 clock (the 10-30 posts are scheduled and not built)
        html = (root / "journal/ko/commute-get-off-early/index.html").read_text(encoding="utf-8")
        self.assertEqual(more_of(html)[2], ["thursday-evening-earbuds-ran-out", "thursday-morning-second-alarm", "wednesday-evening-winter-blanket"])
        self.assertNotIn("friday-", " ".join(more_of(html)[2]))  # tomorrow's posts (10-30) are not public at this clock


if __name__ == "__main__":
    unittest.main()
