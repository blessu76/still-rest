"""SEO guide v1 P0-8: the BlogPosting JSON-LD of every post page is complete and truthful — headline, description, datePublished,
dateModified, inLanguage, url, mainEntityOfPage, image (ImageObject), author/publisher (the ipe.rest Organization, with logo), a BreadcrumbList
and the link to the translation group; no date in the future. Checked on the committed pages and on the full site as the deploy runner builds it.
Run: python3 -m unittest discover -s tests"""
import datetime as dt
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_journal as bj  # noqa: E402
from seo_crawl import CLOCK, committed_site, full_site  # noqa: E402
from site_common import KST, ORG, ORG_ID, SITE  # noqa: E402

POST_URL = re.compile(r"^https://still\.ipe\.rest/journal/([a-z]{2})/([a-z0-9-]+)/$")
EXPECTED_ORG = {"@type": "Organization", "@id": "https://ipe.rest/#organization", "name": "ipe()", "url": "https://ipe.rest/",
                "logo": {"@type": "ImageObject", "url": "https://ipe.rest/icon-512.png", "width": 512, "height": 512}}
NOW = bj.parse_when(CLOCK)


def when(v):
    """ISO date or datetime (as written in JSON-LD) -> aware datetime (a bare date = start of that day, KST)"""
    d = dt.datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=KST)


class Checks:
    sites = ()
    clock = NOW

    def posts(self):
        n = 0
        for name, (root, pages) in self.sites:
            for url, p in pages.items():
                if POST_URL.match(url) and not url.startswith(SITE + "/journal/page/"):
                    n += 1
                    yield name, pages, url, p, p.blog_posting()
        self.assertGreater(n, 1)

    def test_every_post_page_has_exactly_one_blogposting_that_parses(self):
        for name, pages, url, p, post in self.posts():
            self.assertIsNotNone(post, (name, url))
            self.assertEqual(sum(1 for d in p.docs() if d.get("@type") == "BlogPosting"), 1, (name, url))
            self.assertEqual(sum(1 for d in p.docs() if d.get("@type") == "BreadcrumbList"), 1, (name, url))

    def test_required_fields(self):
        for name, pages, url, p, post in self.posts():
            m = POST_URL.match(url)
            self.assertEqual(post["@context"], "https://schema.org")
            for k in ("headline", "description", "datePublished", "dateModified", "inLanguage", "url", "mainEntityOfPage", "image", "author", "publisher"):
                self.assertTrue(post.get(k), (name, url, k))
            self.assertEqual(post["url"], url)
            self.assertEqual(post["mainEntityOfPage"], {"@type": "WebPage", "@id": url})
            self.assertEqual(post["inLanguage"], m.group(1))
            self.assertEqual(post["inLanguage"], p.lang)
            self.assertEqual(p.canonicals, [url])
            self.assertEqual(post["headline"], p.h1_text.strip(), (name, url))
            self.assertTrue(p.title.startswith(post["headline"]), (name, url))  # headline ⊂ title

    def test_image_is_an_image_object(self):
        for name, pages, url, p, post in self.posts():
            img = post["image"]
            self.assertIsInstance(img, dict, (name, url))
            self.assertEqual(img["@type"], "ImageObject", (name, url))
            self.assertRegex(img["url"], r"^https://still\.ipe\.rest/\S+\.(png|jpe?g|webp|gif)$", (name, url))
            self.assertIsInstance(img.get("width"), int, (name, url))
            self.assertIsInstance(img.get("height"), int, (name, url))
            self.assertTrue(img.get("caption"), (name, url))
            self.assertEqual(p.first("og:image"), img["url"], (name, url))

    def test_author_and_publisher_are_the_ipe_rest_organization_with_a_logo(self):
        self.assertEqual(ORG, EXPECTED_ORG)
        for name, pages, url, p, post in self.posts():
            self.assertEqual(post["author"], EXPECTED_ORG, (name, url))
            self.assertEqual(post["publisher"], EXPECTED_ORG, (name, url))
            self.assertEqual(post["publisher"]["@id"], ORG_ID)
            self.assertEqual(post["publisher"]["logo"]["@type"], "ImageObject")

    def test_dates_are_iso_ordered_and_never_in_the_future(self):
        for name, pages, url, p, post in self.posts():
            pub, mod = when(post["datePublished"]), when(post["dateModified"])
            self.assertLessEqual(pub, self.clock, (name, url, "datePublished is in the future"))
            self.assertLessEqual(mod, self.clock + dt.timedelta(hours=0), (name, url, "dateModified is in the future"))
            self.assertGreaterEqual(mod.date(), pub.date(), (name, url, "modified before published"))
            self.assertEqual(p.first("article:published_time"), post["datePublished"], (name, url))
            self.assertEqual(p.first("article:modified_time"), post["dateModified"], (name, url))

    def test_no_date_of_any_json_ld_block_is_in_the_future(self):
        for name, (root, pages) in self.sites:
            for url, p in pages.items():
                for raw in p.ld:
                    for v in re.findall(r'"(?:datePublished|dateModified|dateCreated)":\s*"([^"]+)"', raw):
                        self.assertLessEqual(when(v), self.clock, (name, url, v))

    def test_breadcrumb_list(self):
        for name, pages, url, p, post in self.posts():
            crumb = next(d for d in p.docs() if d.get("@type") == "BreadcrumbList")
            items = crumb["itemListElement"]
            self.assertEqual([i["position"] for i in items], [1, 2, 3], (name, url))
            lang = POST_URL.match(url).group(1)
            self.assertEqual([i["item"] for i in items], ["%s/%s/" % (SITE, lang), "%s/journal/%s/" % (SITE, lang), url], (name, url))
            self.assertEqual(items[-1]["name"], post["headline"])
            self.assertTrue(all(i["name"] for i in items), (name, url))

    def test_translations_are_linked_both_ways(self):
        for name, pages, url, p, post in self.posts():
            slug = POST_URL.match(url).group(2)
            if "translationOfWork" in post:
                src = post["translationOfWork"]
                self.assertEqual(src["@type"], "BlogPosting")
                self.assertEqual(src["@id"], src["url"])
                self.assertIn(src["url"], pages, (name, url))
                self.assertEqual(POST_URL.match(src["url"]).group(2), slug, (name, url))
                self.assertEqual(src["inLanguage"], POST_URL.match(src["url"]).group(1))
                self.assertEqual(post["translator"]["@id"], ORG_ID)
                back = pages[src["url"]].blog_posting().get("workTranslation")
                back = back if isinstance(back, list) else [back] if back else []
                self.assertIn(url, [b["url"] for b in back], (name, url, "the original does not list this translation"))
            else:
                self.assertNotIn("translator", post, (name, url))
            for tr in ([post["workTranslation"]] if isinstance(post.get("workTranslation"), dict) else post.get("workTranslation", [])):
                self.assertIn(tr["url"], pages, (name, url))
                self.assertEqual(pages[tr["url"]].blog_posting()["translationOfWork"]["url"], url, (name, url))

    def test_a_group_has_one_original_that_every_translation_points_at(self):
        for name, (root, pages) in self.sites:
            groups = {}
            for url, p in pages.items():
                m = POST_URL.match(url)
                if m and m.group(2) != "page":
                    groups.setdefault(m.group(2), []).append(p.blog_posting())
            for slug, posts in groups.items():
                originals = [x for x in posts if "translationOfWork" not in x]
                self.assertGreaterEqual(len(originals), 1, (name, slug))
                self.assertLessEqual(len(originals), 2, (name, slug))  # ko and en may both be originals (en without translation_of)


class CommittedPages(Checks, unittest.TestCase):
    clock = bj.parse_when("now")

    @classmethod
    def setUpClass(cls):
        cls.sites = (("committed", committed_site()),)


class FullSitePages(Checks, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sites = (("full", full_site()),)

    def test_every_published_post_of_every_live_language_is_covered(self):
        n = sum(1 for _ in self.posts())
        self.assertGreaterEqual(n, 126)


class ImageObjectHelper(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, bj, "ROOT", bj.ROOT)

    def test_an_image_without_a_known_size_is_still_an_object(self):
        bj.ROOT = Path("/nonexistent")
        self.assertEqual(bj.image_obj("/assets/journal/x/missing.jpg"), {"@type": "ImageObject", "url": SITE + "/assets/journal/x/missing.jpg"})
        self.assertEqual(bj.image_obj("/assets/journal/x/missing.jpg", "alt text")["caption"], "alt text")
        self.assertEqual(bj.image_obj("https://example.test/a.png")["url"], "https://example.test/a.png")

    def test_a_known_size_is_read_from_the_file(self):
        bj.ROOT = Path(__file__).resolve().parent.parent
        self.assertEqual(bj.image_obj("/og-image.png"), {"@type": "ImageObject", "url": SITE + "/og-image.png", "width": 1200, "height": 630})


if __name__ == "__main__":
    unittest.main()
