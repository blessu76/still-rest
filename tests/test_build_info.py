"""Tests for scripts/build_info.py (FAQ + about pages, 12 languages) — run: python3 -m unittest discover -s tests"""
import html
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LANGS = "en ko ja zh-Hant es pt-BR fr de id th vi tr".split()  # the kit's 12 (scripts/site_common.LANGS)
ENDED = "zh ru ar hi".split()  # ended: frozen folders stay but are in no list / hreflang / sitemap
PAGES = ("faq", "about")
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}


def page(lang, name):
    return (REPO / lang / name / "index.html").read_text(encoding="utf-8")


def hub(lang):
    """common language rule: a link to another ipe site carries the page's language - the path when the site has one, else root ?lang=xx."""
    if lang == "pt-BR":
        return "https://ipe.rest/pt/"  # the hub's folder for Brazilian Portuguese is /pt/
    return "https://ipe.rest/%s/" % lang if lang in ("en", "ko", "ja", "es", "id", "fr", "de") else "https://ipe.rest/?lang=%s" % lang  # no hub page for zh-Hant th vi tr


def ld(h, kind):
    for m in re.finditer(r'<script type="application/ld\+json">\n(.*?)\n</script>', h, re.S):
        d = json.loads(m.group(1))
        if d.get("@type") == kind:
            return d
    raise AssertionError("no %s JSON-LD" % kind)


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


class InfoPages(unittest.TestCase):
    def test_every_language_has_both_pages(self):
        for l in LANGS:
            for p in PAGES:
                h = page(l, p)
                self.assertIn('<html lang="%s" dir="%s">' % (l, "ltr"), h, (l, p))  # no RTL language is left (ar ended)
                self.assertIn('<link rel="canonical" href="https://still.ipe.rest/%s/%s/">' % (l, p), h, (l, p))
                got = dict(re.findall(r'<link rel="alternate" hreflang="([\w-]+)" href="([^"]+)"', h))
                self.assertEqual(set(got), set(LANGS) | {"x-default"}, (l, p))  # 12 + x-default, no ended language, no old /pt/
                self.assertTrue(all(got[x] == "https://still.ipe.rest/%s/%s/" % (x, p) for x in LANGS), (l, p))
                self.assertEqual(got["x-default"], "https://still.ipe.rest/en/%s/" % p)
                self.assertNotRegex(h, r"\{(L|psalm|verse)\}", (l, p))  # every placeholder was filled
                self.assertEqual(h.count("<h1>"), 1, (l, p))
                self.assertIn('href="/%s/"' % l, h)  # back to the home page of the same language
                self.assertIn('href="/%s/%s/"' % (l, "about" if p == "faq" else "faq"), h)  # and to its sibling

    def test_faq_json_ld_is_exactly_what_is_visible(self):
        for l in LANGS:
            h = page(l, "faq")
            data = ld(h, "FAQPage")
            self.assertEqual(data["inLanguage"], l)
            self.assertEqual(len(data["mainEntity"]), 8, l)
            body = h[h.index('<div class="prose info">'):h.index("</main>")]
            qs = [text(x) for x in re.findall(r"<h2>(.*?)</h2>", body, re.S)]
            ans = [text(x) for x in re.findall(r"<p>(.*?)</p>", body, re.S)]
            self.assertEqual([q["name"] for q in data["mainEntity"]], qs, l)
            self.assertEqual([q["acceptedAnswer"]["text"] for q in data["mainEntity"]], ans, l)  # nothing only the crawler sees

    def test_faq_answers_what_it_has_to(self):
        for l in LANGS:
            h = page(l, "faq")
            self.assertIn('href="/privacy/"', h, l)  # privacy: one canonical page, linked from the answer
            self.assertIn('href="/%s/about/"' % l, h, l)  # "is it the same as other Still apps" -> the about page
            self.assertIn('href="https://findahelpline.com"', h, l)  # not therapy -> where to find help
            self.assertIn('href="%s"' % hub(l), h, l)  # ipe.rest in this page's language
            self.assertRegex(h, r"3[.,]99", l)  # price, as on the home page
            self.assertIn("still.ipe.rest", h, l)

    def test_about_page_is_one_paragraph_plus_links_and_names_the_difference(self):
        for l in LANGS:
            h = page(l, "about")
            body = h[h.index('<div class="prose info">'):h.index("</main>")]
            ps = re.findall(r"<p>(.*?)</p>", body, re.S)
            self.assertEqual(len(ps), 2, l)  # the paragraph, then the umbrella/links line
            self.assertIn('href="%s"' % hub(l), ps[1], l)  # ipe.rest umbrella link, in this page's language
            self.assertIn('href="/%s/faq/"' % l, ps[1], l)
            for needle in ("ipe Studio", "still.ipe.rest", "ipe"):
                self.assertIn(needle, ps[0], (l, needle))
            data = ld(h, "AboutPage")
            self.assertEqual(data["mainEntity"]["name"], "still()")
            self.assertNotIn("sameAs", json.dumps(data))  # until a store page / profile exists
            self.assertNotIn("downloadUrl", json.dumps(data))

    def test_links_to_other_ipe_sites_carry_the_language(self):
        for l in LANGS:
            for p in PAGES:
                h = page(l, p)
                hrefs = re.findall(r'href="(https?://(?:[a-z]+\.)?ipe\.rest[^"]*)"', h)
                visible = [u for u in hrefs if not u.startswith("https://still.ipe.rest")]
                self.assertTrue(visible, (l, p))
                for u in visible:
                    self.assertEqual(u, hub(l), (l, p))  # never a bare https://ipe.rest

    def test_text_is_in_the_pages_language(self):
        faq_ko, faq_en = page("ko", "faq"), page("en", "faq")
        self.assertIn("자주 묻는 질문", faq_ko)
        self.assertNotIn("Frequently asked questions", faq_ko)
        self.assertIn("Frequently asked questions", faq_en)
        titles = {re.search(r"<title>(.*?)</title>", page(l, p)).group(1) for l in LANGS for p in PAGES}
        self.assertEqual(len(titles), 24)

    def test_footer_links_reach_the_pages_from_home_and_info(self):
        for l in LANGS:
            for h in (page(l, "faq"), page(l, "about"), (REPO / l / "index.html").read_text(encoding="utf-8")):
                self.assertIn('href="/%s/faq/"' % l, h, l)
                self.assertIn('href="/%s/about/"' % l, h, l)
        root = (REPO / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/en/faq/"', root)

    def test_journal_links_follow_the_posts(self):
        has_posts = (REPO / "journal/index.html").is_file()  # like the home page: the journal appears with its first post
        for l in LANGS:
            for p in PAGES:
                h = page(l, p)
                h = h[h.index("<body>"):]  # (the <head> may still advertise the feed)
                self.assertEqual("/journal/" in h, has_posts, (l, p))

    def test_sitemap_and_llms_list_all_24(self):
        root = ET.parse(REPO / "sitemap.xml").getroot()
        rows = {u.find("s:loc", NS).text: u for u in root.findall("s:url", NS)}
        for p in PAGES:
            for l in LANGS:
                u = rows["https://still.ipe.rest/%s/%s/" % (l, p)]
                self.assertEqual(len(u.findall("x:link", NS)), 13, (l, p))  # 12 languages + x-default
                self.assertIsNotNone(u.find("s:lastmod", NS))
        llms = (REPO / "llms.txt").read_text(encoding="utf-8")
        for p in PAGES:
            for l in LANGS:
                self.assertIn("(https://still.ipe.rest/%s/%s/)" % (l, p), llms)
        for e in ENDED + ["pt"]:  # ended languages and the moved pt are in neither list
            for p in PAGES:
                self.assertNotIn("https://still.ipe.rest/%s/%s/" % (e, p), llms)
                self.assertNotIn("https://still.ipe.rest/%s/%s/" % (e, p), rows)

    def test_privacy_stays_one_canonical_page(self):
        # decision: the privacy policy is legal text (en + ko toggle inside) — not machine translated into 12 languages
        for l in LANGS:
            self.assertFalse((REPO / l / "privacy").exists(), l)
        self.assertTrue((REPO / "privacy/index.html").is_file())

    def test_pages_json_covers_every_language(self):
        d = json.loads((REPO / "content/info/pages.json").read_text(encoding="utf-8"))
        keys = [k for k in d if not k.startswith("_")]
        self.assertTrue(set(LANGS) <= set(keys))
        self.assertNotIn("pt", keys)  # the data key moved pt -> pt-BR
        for l in LANGS:
            self.assertEqual(len(d[l]["faq"]), 8, l)
            self.assertEqual(len(d[l]["about"]), 2, l)

    def test_new_languages_have_pages_and_ended_languages_are_not_listed(self):
        for l in ("th", "tr", "zh-Hant", "pt-BR"):
            for p in PAGES:
                self.assertIn('<html lang="%s" dir="ltr">' % l, page(l, p), (l, p))
        for e in ENDED:  # frozen folders may exist, but no live page advertises them
            for l in LANGS:
                for p in PAGES:
                    self.assertNotIn('hreflang="%s"' % e, page(l, p), (l, p, e))
                    self.assertNotIn('href="/%s/"' % e, page(l, p), (l, p, e))

    def test_old_pt_info_pages_are_redirect_stubs(self):
        for p in PAGES:
            h = page("pt", p)
            self.assertIn("generated by scripts/build_journal.py", h, p)
            self.assertIn('<link rel="canonical" href="https://still.ipe.rest/pt-BR/%s/">' % p, h, p)
            self.assertIn('http-equiv="refresh" content="0; url=https://still.ipe.rest/pt-BR/%s/"' % p, h, p)
            self.assertIn("noindex", h, p)
            self.assertNotIn("hreflang", h, p)
            self.assertNotIn("<h1>", h, p)
