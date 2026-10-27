"""JSON-LD regression: author / publisher / translator and the home Organization node all point at the ipe.rest hub (@id).
Run: python3 -m unittest discover -s tests"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from site_common import LANGS, ORG, ORG_ID  # noqa: E402

LD = re.compile(r'<script type="application/ld\+json">\n(.*?)\n</script>', re.S)
LOGO = {"@type": "ImageObject", "url": "https://ipe.rest/icon-512.png", "width": 512, "height": 512}  # the hub's square icon (hub declares the same file)
HUB = {"@type": "Organization", "@id": "https://ipe.rest/#organization", "name": "ipe()", "url": "https://ipe.rest/", "logo": LOGO}  # as published on https://ipe.rest/


def lds(path):
    """every JSON-LD document of a generated page (raises if one does not parse)"""
    return [json.loads(m) for m in LD.findall(Path(path).read_text(encoding="utf-8"))]


def nodes(doc):
    return doc["@graph"] if "@graph" in doc else [doc]


def logo_problems(org):
    """why this Organization's logo is not an acceptable square ImageObject (empty list = fine)"""
    logo = org.get("logo")
    if not isinstance(logo, dict):
        return ["logo is not an ImageObject node: %r" % (logo,)]
    bad = []
    if logo.get("@type") != "ImageObject":
        bad.append("logo.@type=%r" % logo.get("@type"))
    url = logo.get("url")
    if not (isinstance(url, str) and url.startswith("https://") and len(url) > len("https://")):
        bad.append("logo.url not an https absolute URL: %r" % (url,))
    w, h = logo.get("width"), logo.get("height")
    if not (isinstance(w, int) and isinstance(h, int) and w > 0 and w == h):
        bad.append("logo not square: %r x %r" % (w, h))
    return bad


def is_org_ref(v, full):
    """full: @id + @type + name + url + logo (a lone @id reference may not give a crawler the name); else the bare reference is fine too"""
    if full:
        return v.get("@id") == ORG_ID and v.get("name") == "ipe()" and not logo_problems(v) and all(v.get(k) == HUB[k] for k in HUB)
    return v.get("@id") == ORG_ID


class OrgHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        # the committed pages are clock-free (scheduled posts are built only by the deploy runner), so build the full site as the
        # runner would, far in the future, to cover every post of every language
        shutil.copytree(REPO, cls.tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_journal.py"), "--root", str(cls.tmp / "s"), "--now", "2099-01-01 00:00"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        cls.built = cls.tmp / "s"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_constant_matches_the_hub(self):
        self.assertEqual(ORG_ID, "https://ipe.rest/#organization")
        self.assertEqual(ORG, HUB)
        self.assertEqual(ORG["name"], "ipe()")
        self.assertEqual(logo_problems(ORG), [])

    def test_logo_is_a_square_https_imageobject(self):
        self.assertEqual(logo_problems(ORG), [])
        self.assertEqual(logo_problems(dict(ORG, logo="https://ipe.rest/icon-512.png")), ["logo is not an ImageObject node: 'https://ipe.rest/icon-512.png'"])
        self.assertTrue(logo_problems(dict(ORG, logo=dict(LOGO, width=1200, height=630))))
        self.assertTrue(logo_problems(dict(ORG, logo=dict(LOGO, url="/icon-512.png"))))
        self.assertTrue(logo_problems(dict(ORG, logo=dict(LOGO, url="http://ipe.rest/icon-512.png"))))
        self.assertTrue(logo_problems(dict(ORG, logo=dict(LOGO, **{"@type": "URL"}))))

    def check_posts(self, root):
        posts = [f for f in sorted(root.glob("journal/*/*/index.html")) if f.relative_to(root).parts[1] != "page"]  # list pages 2+ of the hub (journal/page/<n>/) are not posts
        self.assertGreaterEqual(len(posts), 18)
        n = 0
        for f in posts:
            docs = lds(f)  # also proves every ld+json block parses
            for d in docs:
                if d.get("@type") != "BlogPosting":
                    continue
                n += 1
                for k in ("author", "publisher"):
                    self.assertTrue(is_org_ref(d[k], True), (str(f), k, d[k]))
                if "translator" in d:
                    self.assertTrue(is_org_ref(d["translator"], True), (str(f), d["translator"]))
                    self.assertTrue(d["translator"].get("description"), str(f))
        self.assertEqual(n, len(posts))  # every post page carries exactly one BlogPosting
        return n

    def test_every_post_page_points_at_the_hub(self):
        # a full build: 8 originals' worth of posts x the published languages
        self.assertGreaterEqual(self.check_posts(self.built), 63)

    def test_committed_post_pages_point_at_the_hub(self):
        self.check_posts(REPO)

    def test_translated_posts_name_the_translator(self):
        n = 0
        for f in self.built.glob("journal/*/*/index.html"):
            for d in lds(f):
                if "translationOfWork" in d:
                    n += 1
                    self.assertIn("translator", d, str(f))
        self.assertGreater(n, 0)

    def test_journal_lists_point_at_the_hub(self):
        for root in (self.built, REPO):
            lists = [root / "journal/index.html"] + sorted(root.glob("journal/*/index.html"))
            self.assertGreaterEqual(len(lists), 2)
            for f in lists:
                blogs = [d for d in lds(f) if d.get("@type") == "Blog"]
                self.assertEqual(len(blogs), 1, str(f))
                self.assertTrue(is_org_ref(blogs[0]["publisher"], True), str(f))

    def test_home_pages_define_the_hub_and_refer_to_it(self):
        pages = [REPO / "index.html"] + [REPO / l / "index.html" for l in LANGS]
        self.assertEqual(len(pages), 12)
        for f in pages:
            docs = lds(f)
            orgs = [n for d in docs for n in nodes(d) if n.get("@type") == "Organization"]
            self.assertEqual(len(orgs), 1, str(f))
            self.assertEqual(orgs[0]["@id"], ORG_ID, str(f))
            self.assertEqual((orgs[0]["name"], orgs[0]["url"]), (HUB["name"], HUB["url"]), str(f))
            self.assertEqual(orgs[0]["name"], "ipe()", str(f))
            self.assertEqual(logo_problems(orgs[0]), [], str(f))
            self.assertEqual(orgs[0]["logo"], LOGO, str(f))
            for d in docs:
                for n in nodes(d):
                    if "publisher" in n:
                        self.assertTrue(is_org_ref(n["publisher"], False), (str(f), n["@type"]))
                    for k in ("author", "translator"):
                        if k in n:
                            self.assertTrue(is_org_ref(n[k], False), (str(f), k))

    def test_info_pages_point_at_the_hub(self):
        seen = 0
        for l in LANGS:
            for name in ("faq", "about"):
                for d in lds(REPO / l / name / "index.html"):
                    for n in nodes(d):
                        pubs = [n["publisher"]] if "publisher" in n else []
                        if isinstance(n.get("mainEntity"), dict) and "publisher" in n["mainEntity"]:
                            pubs.append(n["mainEntity"]["publisher"])
                        for p in pubs:
                            seen += 1
                            self.assertTrue(is_org_ref(p, True), (l, name, p))
        self.assertEqual(seen, len(LANGS) * 2)

    def test_no_stale_organization_copy_anywhere(self):
        # an Organization without @id (the old {name,url} copy) must not come back on any generated page
        for root in (self.built, REPO):
            for f in list(root.glob("*/index.html")) + list(root.glob("*/*/index.html")) + list(root.glob("*/*/*/index.html")) + [root / "index.html"]:
                if "application/ld+json" not in f.read_text(encoding="utf-8"):
                    continue
                for d in lds(f):
                    stack = [d]
                    while stack:
                        v = stack.pop()
                        if isinstance(v, dict):
                            if v.get("@type") == "Organization":
                                self.assertEqual(v.get("@id"), ORG_ID, str(f))
                                self.assertEqual(v.get("name"), "ipe()", str(f))
                                if len(v) > 1:  # a full node (not a bare {"@id"} reference) always carries the logo
                                    self.assertEqual(logo_problems(v), [], str(f))
                            stack.extend(v.values())
                        elif isinstance(v, list):
                            stack.extend(v)


if __name__ == "__main__":
    unittest.main()
