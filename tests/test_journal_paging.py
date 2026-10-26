"""Journal numbers (No. N, publication order, same in every language) and paging (10 a page) — run: python3 -m unittest discover -s tests

Davy's rule for every ipe website (2026-10-27): ① number = publication order, first article = No. 1, shown on the list card and the article head;
② list = newest first, at most 10 a page, page 2+ at <list>page/<n>/ (page 1 keeps the plain address), prev/next, self canonical,
hreflang between the same page numbers, every page in the sitemap, a page number in the title of page 2+, JSON-LD of that page's posts only.
The real site has 8 articles per language, so paging is tested on generated fixtures with 10 / 11 / 20 / 21 articles."""
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402
import check_sitemap  # noqa: E402
from test_build_journal import Base, run  # noqa: E402

FIRST_DAY = dt.date(2026, 9, 1)
NO = re.compile(r'<span class="j-no">No\.&nbsp;(\d+)</span>')
LD = re.compile(r'<script type="application/ld\+json">\n(.*?)\n</script>', re.S)


def put(root, lang, slug, date, extra="", title=None):
    """one post file; ko = original, any other language = `translation_of: ko` (+ extra front matter lines)."""
    tr = "" if lang == "ko" else "translation_of: ko\n"
    d = Path(root) / "content/journal" / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / (slug + ".md")).write_text(
        "---\ntitle: %s\ndate: %s\nslug: %s\nlang: %s\ndescription: Desc %s %s.\ncategory: test\n%s%s---\n\nBody %s.\n"
        % (title or "T %s %s" % (slug, lang), date, slug, lang, slug, lang, tr, extra, slug), encoding="utf-8")


def series(root, n, langs=("ko",), counts=None):
    """posts p01..p<n> (p01 is the oldest, one day apart) in each language; counts = {lang: how many of the first posts exist in that language}."""
    for i in range(1, n + 1):
        for l in langs:
            if i <= (counts or {}).get(l, n):
                put(root, l, "p%02d" % i, (FIRST_DAY + dt.timedelta(days=i - 1)).isoformat())


def slugs_on(html):
    return re.findall(r'<h2><a href="/journal/[a-z]{2}/([a-z0-9-]+)/">', html)


def numbers_on(html):
    return [int(x) for x in NO.findall(html)]


def jsonld(html):
    return [json.loads(x) for x in LD.findall(html)]


class Numbers(Base):
    def number_of(self, lang, slug):
        return numbers_on(self.page("journal/%s/%s/index.html" % (lang, slug)))

    def test_number_is_publication_order_and_the_same_in_every_language(self):
        series(self.tmp, 5, langs=("ko", "en", "ja"))
        self.assertEqual(run(self.tmp).returncode, 0)
        for i in range(1, 6):
            for l in ("ko", "en", "ja"):
                self.assertEqual(self.number_of(l, "p%02d" % i), [i], (l, i))  # exactly one number on the article head
        # list cards: newest first, so the numbers count down; hub (originals) too
        for f in ("journal/ko/index.html", "journal/en/index.html", "journal/ja/index.html", "journal/index.html"):
            self.assertEqual(numbers_on(self.page(f)), [5, 4, 3, 2, 1], f)

    def test_number_follows_the_date_not_the_file_name(self):
        put(self.tmp, "ko", "zz-oldest", "2026-08-01")
        put(self.tmp, "ko", "aa-newest", "2026-09-30")
        put(self.tmp, "ko", "mm-middle", "2026-09-01")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual([self.number_of("ko", s) for s in ("zz-oldest", "mm-middle", "aa-newest")], [[1], [2], [3]])

    def test_same_day_posts_are_ordered_by_time_of_day(self):
        put(self.tmp, "ko", "late", "2026-10-20", "published_at: 2026-10-20 18:00\n")
        put(self.tmp, "ko", "early", "2026-10-20", "published_at: 2026-10-20 09:00\n")
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual(self.number_of("ko", "early"), [1])
        self.assertEqual(self.number_of("ko", "late"), [2])

    def test_drafts_and_unpublished_languages_take_no_number(self):
        series(self.tmp, 3, langs=("ko", "en"))
        put(self.tmp, "ko", "wip", "2026-09-02", "draft: true\n")  # a draft between p01 and p02 leaves no gap and takes no number
        put(self.tmp, "vi", "p02", "2026-09-02", "draft: true\n")  # a hidden (draft) language: the article keeps its number everywhere
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual([self.number_of("ko", "p%02d" % i) for i in (1, 2, 3)], [[1], [2], [3]])
        self.assertEqual([self.number_of("en", "p%02d" % i) for i in (1, 2, 3)], [[1], [2], [3]])
        self.assertFalse((self.tmp / "journal/ko/wip").exists())
        self.assertFalse((self.tmp / "journal/vi").exists())

    def test_a_scheduled_post_opening_never_renumbers_the_others(self):
        series(self.tmp, 3, langs=("ko", "en"))
        for l in ("ko", "en"):
            put(self.tmp, l, "soon", "2026-10-20", "publish_at: 2026-10-20 11:00\n")
        before = {}
        self.assertEqual(run(self.tmp, "--now", "2026-10-20 10:59").returncode, 0)  # not due yet
        for l in ("ko", "en"):
            before[l] = [self.number_of(l, "p%02d" % i) for i in (1, 2, 3)]
        self.assertEqual(before["ko"], [[1], [2], [3]])
        self.assertFalse((self.tmp / "journal/ko/soon").exists())
        self.assertEqual(numbers_on(self.page("journal/ko/index.html")), [3, 2, 1])
        self.assertEqual(run(self.tmp, "--now", "2026-10-20 11:00").returncode, 0)  # due: it opens as No. 4, the others stay
        for l in ("ko", "en"):
            self.assertEqual([self.number_of(l, "p%02d" % i) for i in (1, 2, 3)], before[l], l)
            self.assertEqual(self.number_of(l, "soon"), [4], l)
            self.assertEqual(numbers_on(self.page("journal/%s/index.html" % l)), [4, 3, 2, 1], l)
        # the plain (committed) build holds it back again and the numbers are the same as before it opened
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertEqual([self.number_of("ko", "p%02d" % i) for i in (1, 2, 3)], [[1], [2], [3]])

    def test_home_cards_show_the_number(self):
        series(self.tmp, 4, langs=("ko", "en"))
        self.assertEqual(run(self.tmp).returncode, 0)
        for f in ("ko/index.html", "en/index.html", "de/index.html"):  # de has no post: its cards fall back to the originals (same numbers)
            cards = re.findall(r'<a class="j-card".*?</a>', self.page(f), re.S)
            self.assertEqual(len(cards), 3, f)
            self.assertEqual([int(NO.search(c).group(1)) for c in cards], [4, 3, 2], f)
            for c in cards:
                self.assertLess(c.index("j-no"), c.index("<time"), f)

    def test_the_committed_site_numbers_are_consistent_and_survive_the_scheduled_posts(self):
        committed = {}
        for idx in sorted((REPO / "journal").glob("*/*/index.html")):
            lang, slug = idx.parent.parent.name, idx.parent.name
            if lang in bj.LANGS:
                n = numbers_on(idx.read_text(encoding="utf-8"))
                self.assertEqual(len(n), 1, idx)
                committed.setdefault(slug, set()).add(n[0])
        self.assertTrue(committed)
        for slug, ns in committed.items():
            self.assertEqual(len(ns), 1, "%s has different numbers in different languages: %s" % (slug, ns))
        self.assertEqual(sorted(n for ns in committed.values() for n in ns), list(range(1, len(committed) + 1)))
        # the deploy runner builds with the real clock: the scheduled posts open after the committed ones and nothing committed is renumbered
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
            r = run(tmp / "s", "--now", "2026-12-31 23:00")
            self.assertEqual(r.returncode, 0, r.stderr)
            live = {}
            for idx in sorted((tmp / "s/journal").glob("*/*/index.html")):
                lang, slug = idx.parent.parent.name, idx.parent.name
                if lang in bj.LANGS:
                    live.setdefault(slug, set()).update(numbers_on(idx.read_text(encoding="utf-8")))
            self.assertGreater(len(live), len(committed))
            for slug, ns in live.items():
                self.assertEqual(len(ns), 1, (slug, ns))
            for slug, ns in committed.items():
                self.assertEqual(live[slug], ns, "%s was renumbered when the scheduled posts opened" % slug)
            self.assertEqual(sorted(n for ns in live.values() for n in ns), list(range(1, len(live) + 1)))
            self.assertEqual(check_sitemap.check(tmp / "s", bj.parse_when("2026-12-31 23:00"))[0], [])
        finally:
            shutil.rmtree(tmp)


class Paging(Base):
    def build(self, n, langs=("ko",), counts=None):
        series(self.tmp, n, langs, counts)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def list_html(self, lang, n=1):
        base = "journal/%s" % lang if lang else "journal"
        return self.page(base + ("/index.html" if n == 1 else "/page/%d/index.html" % n))

    def test_page_count_and_boundaries(self):
        for total, pages in ((9, 1), (10, 1), (11, 2), (20, 2), (21, 3)):
            with self.subTest(posts=total):
                shutil.rmtree(self.tmp / "journal", ignore_errors=True)
                shutil.rmtree(self.tmp / "content/journal/ko", ignore_errors=True)
                self.build(total)
                for lang in ("ko", None):  # the language list and the hub (the originals)
                    base = self.tmp / ("journal/%s" % lang if lang else "journal")
                    for n in range(2, pages + 1):
                        self.assertTrue((base / "page" / str(n) / "index.html").is_file(), (lang, n))
                    self.assertFalse((base / "page" / str(pages + 1)).exists(), (lang, pages + 1))
                    self.assertFalse((base / "page" / "1").exists(), "page 1 keeps the plain address — there is no /page/1/")
                    seen = []
                    for n in range(1, pages + 1):
                        h = self.list_html(lang, n)
                        s = slugs_on(h)
                        self.assertEqual(len(s), min(10, total - 10 * (n - 1)), (lang, n))
                        seen += s
                    # newest first, every post exactly once, numbers 1..N count down from the newest
                    self.assertEqual(seen, ["p%02d" % i for i in range(total, 0, -1)], lang)
                    self.assertEqual([x for n in range(1, pages + 1) for x in numbers_on(self.list_html(lang, n))], list(range(total, 0, -1)), lang)

    def test_21_posts_page_membership(self):
        self.build(21)
        self.assertEqual(slugs_on(self.list_html("ko", 1)), ["p%02d" % i for i in range(21, 11, -1)])
        self.assertEqual(slugs_on(self.list_html("ko", 2)), ["p%02d" % i for i in range(11, 1, -1)])
        self.assertEqual(slugs_on(self.list_html("ko", 3)), ["p01"])

    def test_canonical_title_prev_next_and_visible_links(self):
        self.build(21, langs=("ko", "en"))
        for lang, plain_title, page_title in (("ko", "저널 — still() · 한국어", "저널 — still() · 한국어 · %d페이지"), ("en", "Journal — still() · English", "Journal — still() · English · Page %d")):
            for n in (1, 2, 3):
                h = self.list_html(lang, n)
                path = "/journal/%s/" % lang + ("" if n == 1 else "page/%d/" % n)
                self.assertIn('<link rel="canonical" href="https://still.ipe.rest%s">' % path, h, (lang, n))  # self canonical
                self.assertIn("<title>%s</title>" % (plain_title if n == 1 else page_title % n), h, (lang, n))
                self.assertIn('<meta property="og:title" content="%s">' % (plain_title if n == 1 else page_title % n), h, (lang, n))
                prev = "/journal/%s/" % lang + ("" if n == 2 else "page/%d/" % (n - 1))  # page 2's "previous" is the plain list, never /page/1/
                nxt = "/journal/%s/page/%d/" % (lang, n + 1)
                # <link rel=prev/next> in the head
                self.assertEqual(('<link rel="prev" href="https://still.ipe.rest%s">' % prev) in h, n > 1, (lang, n))
                self.assertEqual(('<link rel="next" href="https://still.ipe.rest%s">' % nxt) in h, n < 3, (lang, n))
                self.assertEqual(h.count('<link rel="prev"'), 1 if n > 1 else 0, (lang, n))
                self.assertEqual(h.count('<link rel="next"'), 1 if n < 3 else 0, (lang, n))
                # visible links
                self.assertEqual(('class="pager-prev" rel="prev" href="%s"' % prev) in h, n > 1, (lang, n))
                self.assertEqual(('class="pager-next" rel="next" href="%s"' % nxt) in h, n < 3, (lang, n))
                self.assertIn('<span class="pager-now" aria-current="page">%d / 3</span>' % n, h, (lang, n))
                self.assertNotIn("/page/1/", h, (lang, n))
        # the page number also reads in the page itself (eyebrow) from page 2 on
        self.assertIn('<p class="eyebrow">still() · Page 2</p>', self.list_html("en", 2))
        self.assertIn('<p class="eyebrow">still()</p>', self.list_html("en", 1))

    def test_one_page_has_no_pager_and_no_prev_next(self):
        self.build(10, langs=("ko", "en"))
        for lang in ("ko", "en", None):
            h = self.list_html(lang)
            self.assertNotIn('class="pager"', h, lang)
            self.assertNotIn('rel="prev"', h, lang)
            self.assertNotIn('rel="next"', h, lang)
            self.assertIn("<title>%s — still() · %s</title>" % (("저널", "한국어") if lang == "ko" else ("Journal", "English" if lang else "All languages")), h, lang)

    def test_hub_pages(self):
        self.build(21, langs=("ko", "en"))  # the hub lists the originals (ko) only: 21 -> 3 pages
        for n in (1, 2, 3):
            h = self.list_html(None, n)
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/journal/%s">' % ("" if n == 1 else "page/%d/" % n), h)
            self.assertIn("<title>Journal — still() · All languages%s</title>" % ("" if n == 1 else " · Page %d" % n), h)
        self.assertIn('class="pager-next" rel="next" href="/journal/page/2/"', self.list_html(None, 1))
        self.assertIn('class="pager-prev" rel="prev" href="/journal/"', self.list_html(None, 2))
        self.assertIn('class="pager-prev" rel="prev" href="/journal/page/2/"', self.list_html(None, 3))

    def test_hreflang_links_the_same_page_number_only(self):
        # ko: 21 posts (3 pages) · en: first 11 posts (2 pages) · ja: first 5 (1 page)
        self.build(21, langs=("ko", "en", "ja"), counts={"en": 11, "ja": 5})

        def alt(h):
            return dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="https://still\.ipe\.rest([^"]+)">', h))
        a1 = alt(self.list_html("ko", 1))
        self.assertEqual({k: v for k, v in a1.items() if k != "x-default"}, {"ko": "/journal/ko/", "en": "/journal/en/", "ja": "/journal/ja/"})
        self.assertEqual(a1["x-default"], "/journal/")
        a2 = alt(self.list_html("ko", 2))  # ja has no page 2 -> not listed (no link to a page that is not there)
        self.assertEqual({k: v for k, v in a2.items() if k != "x-default"}, {"ko": "/journal/ko/page/2/", "en": "/journal/en/page/2/"})
        self.assertEqual(a2["x-default"], "/journal/page/2/")
        a3 = alt(self.list_html("ko", 3))  # only ko has page 3
        self.assertEqual({k: v for k, v in a3.items() if k != "x-default"}, {"ko": "/journal/ko/page/3/"})
        self.assertEqual(a3["x-default"], "/journal/page/3/")
        self.assertEqual({k: v for k, v in alt(self.list_html("en", 2)).items() if k != "x-default"},
                         {"ko": "/journal/ko/page/2/", "en": "/journal/en/page/2/"})
        # the hub's page 2 names the languages that have a page 2; its x-default is itself
        h2 = alt(self.list_html(None, 2))
        self.assertEqual({k: v for k, v in h2.items() if k != "x-default"}, {"ko": "/journal/ko/page/2/", "en": "/journal/en/page/2/"})
        self.assertEqual(h2["x-default"], "/journal/page/2/")
        # the language <select>: same page number when that language has it, else its first page
        sel = re.findall(r'<option value="([^"]+)"', self.list_html("ko", 3))
        self.assertEqual(sel, ["/journal/en/", "/journal/ko/page/3/", "/journal/ja/"])

    def test_sitemap_lists_every_page_and_passes_the_checker(self):
        self.build(21, langs=("ko", "en", "ja"), counts={"en": 11, "ja": 5})
        errs, urls = check_sitemap.check(self.tmp)
        self.assertEqual(errs, [])
        want = ["/journal/", "/journal/page/2/", "/journal/page/3/",
                "/journal/ko/", "/journal/ko/page/2/", "/journal/ko/page/3/",
                "/journal/en/", "/journal/en/page/2/", "/journal/ja/"]
        for w in want:
            self.assertIn("https://still.ipe.rest" + w, urls, w)
        for w in ("/journal/en/page/3/", "/journal/ja/page/2/", "/journal/page/4/", "/journal/ko/page/1/", "/journal/page/1/"):
            self.assertNotIn("https://still.ipe.rest" + w, urls, w)
        sm = self.page("sitemap.xml")
        # the page-2 entry of ko lists the pages 2 of ko and en (not ja) + x-default
        block = re.search(r"<url>\s*<loc>https://still\.ipe\.rest/journal/ko/page/2/</loc>.*?</url>", sm, re.S).group(0)
        self.assertEqual(re.findall(r'hreflang="([^"]+)"', block), ["en", "ko", "x-default"])

    def test_sitemap_checker_notices_a_missing_page(self):
        self.build(11)
        sm = self.tmp / "sitemap.xml"
        text = sm.read_text(encoding="utf-8")
        text = re.sub(r"  <url>\s*<loc>https://still\.ipe\.rest/journal/ko/page/2/</loc>.*?</url>\n", "", text, flags=re.S)
        sm.write_text(text, encoding="utf-8")
        self.assertIn("missing from sitemap: https://still.ipe.rest/journal/ko/page/2/", check_sitemap.check(self.tmp)[0])

    def test_json_ld_holds_only_that_pages_posts(self):
        self.build(21, langs=("ko",))
        for n, want in ((1, range(21, 11, -1)), (2, range(11, 1, -1)), (3, range(1, 0, -1))):
            h = self.list_html("ko", n)
            docs = jsonld(h)
            blog = next(d for d in docs if d["@type"] == "Blog")
            items = next(d for d in docs if d["@type"] == "ItemList")
            urls = ["https://still.ipe.rest/journal/ko/p%02d/" % i for i in want]
            self.assertEqual([b["url"] for b in blog["blogPost"]], urls, n)
            self.assertEqual([e["url"] for e in items["itemListElement"]], urls, n)
            self.assertEqual(items["numberOfItems"], len(urls), n)
            self.assertEqual([e["position"] for e in items["itemListElement"]], list(range((n - 1) * 10 + 1, (n - 1) * 10 + len(urls) + 1)), n)  # positions go on across pages
            page_url = "https://still.ipe.rest/journal/ko/" + ("" if n == 1 else "page/%d/" % n)
            self.assertEqual(blog["url"], page_url, n)
            self.assertEqual(items["url"], page_url, n)
            crumb = next(d for d in docs if d["@type"] == "BreadcrumbList")
            self.assertEqual(len(crumb["itemListElement"]), 2 if n == 1 else 3, n)
            self.assertEqual(crumb["itemListElement"][1]["item"], "https://still.ipe.rest/journal/ko/", n)  # "Journal" is always page 1
            if n > 1:
                self.assertEqual(crumb["itemListElement"][2]["item"], page_url)
                self.assertEqual(crumb["itemListElement"][2]["name"], "%d페이지" % n)

    def test_every_language_has_its_own_natural_page_label(self):
        ui = json.loads((REPO / "content/journal/ui.json").read_text(encoding="utf-8"))
        for l in bj.LANGS:
            for k in ("page", "prev_page", "next_page", "aria_pager"):
                self.assertTrue(ui[l].get(k), (l, k))
            self.assertIn("{n}", ui[l]["page"], l)
        series(self.tmp, 11, langs=("ko", "ja", "de", "fr", "ru"))
        self.assertEqual(run(self.tmp).returncode, 0)
        for l, label in (("ja", "2ページ"), ("de", "Seite 2"), ("fr", "Page 2"), ("ru", "Страница 2")):
            h = self.list_html(l, 2)
            self.assertIn(label, re.search(r"<title>(.*?)</title>", h).group(1), l)

    def test_every_page_has_one_pager_one_list_and_is_indexable(self):
        self.build(21, langs=("ko", "en"))
        for lang in ("ko", "en", None):
            for n in (1, 2, 3):
                h = self.list_html(lang, n)
                self.assertEqual(h.count('<nav class="pager"'), 1, (lang, n))
                self.assertEqual(h.count('class="j-list"'), 1)
                self.assertIn('content="index, follow', h)  # a later page is indexable too

    def test_fewer_posts_remove_the_stale_page(self):
        self.build(21)
        self.assertTrue((self.tmp / "journal/ko/page/3/index.html").is_file())
        (self.tmp / "content/journal/ko/p01.md").unlink()  # 20 left: page 3 goes away
        self.assertEqual(run(self.tmp).returncode, 0)
        self.assertFalse((self.tmp / "journal/ko/page/3").exists())
        self.assertFalse((self.tmp / "journal/page/3").exists())
        self.assertTrue((self.tmp / "journal/ko/page/2/index.html").is_file())
        self.assertEqual(check_sitemap.check(self.tmp)[0], [])

    def test_check_passes_and_a_stale_page_is_noticed(self):
        self.build(21)
        # the committed-output freshness check also covers the generated pages (check_fresh builds a copy and compares every file)
        r = run(self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (self.tmp / "journal/ko/page/2/index.html").write_text("stale", encoding="utf-8")
        r = run(self.tmp, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("journal/ko/page/2/index.html", r.stderr)

    def test_page_is_a_reserved_slug(self):
        put(self.tmp, "ko", "page", "2026-10-01")
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("reserved", r.stderr)

    def test_an_alias_may_not_take_a_list_page(self):
        series(self.tmp, 2)
        put(self.tmp, "ko", "p03", "2026-09-03", "aliases: /journal/ko/page/2/\n")
        r = run(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("alias", r.stderr)


if __name__ == "__main__":
    unittest.main()
