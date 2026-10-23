"""Every internal link and asset reference on the built site must lead to a real file — run: python3 -m unittest discover -s tests

(A draft once linked to /blog/, which did not exist: a 404 only a visitor would have found.) The crawl reads the committed HTML
of the repo and of a copy with the first posts published, and follows a / or https://still.ipe.rest href/src to <path>/index.html
or the file. Not checked: external sites, mailto:/tel:, a bare "#"."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent.parent
SITE = "https://still.ipe.rest"
SKIP_DIRS = {".git", ".github", "content", "scripts", "tests", "node_modules", "__pycache__"}  # sources, not the published site
REFS = {"a": "href", "link": "href", "img": "src", "script": "src", "source": "src", "iframe": "src"}


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("name"):
            self.ids.add(a["name"])
        if tag in REFS and a.get(REFS[tag]):
            self.refs.append((tag, a[REFS[tag]]))
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "refresh":
            m = re.search(r"url=(\S+)", a.get("content") or "", re.I)
            if m:
                self.refs.append(("meta-refresh", m.group(1)))
        if tag == "meta" and a.get("property") in ("og:image", "og:url") and a.get("content"):
            self.refs.append((a["property"], a["content"]))
        if tag == "meta" and a.get("name") == "twitter:image" and a.get("content"):
            self.refs.append(("twitter:image", a["content"]))


def parse(path):
    p = Refs()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def pages(root):
    for f in sorted(root.rglob("*.html")):
        if not SKIP_DIRS & set(f.relative_to(root).parts):
            yield f


def target(root, url):
    """-> (file path or None, fragment) for an internal url, or None when it is not ours to check."""
    u = url.strip()
    if u.startswith(SITE):
        u = u[len(SITE):] or "/"
    if u == "#" or u.startswith(("mailto:", "tel:", "data:", "javascript:", "http:", "https:", "//")):
        return None
    sp = urlsplit(u)
    if not sp.path and sp.fragment:
        return ("", sp.fragment)  # same page
    if not sp.path.startswith("/"):
        return ("RELATIVE", sp.path)  # we write absolute paths only
    rel = unquote(sp.path).lstrip("/")
    f = root / rel
    if sp.path.endswith("/"):
        f = f / "index.html"
    return (f, sp.fragment)


def broken(root):
    """list of 'page: <tag> url -> why' for every internal reference that does not resolve."""
    root = Path(root)
    out, parsed = [], {}
    for page in pages(root):
        here = page.relative_to(root)
        refs = parse(page)
        parsed[page] = refs
        for tag, url in refs.refs:
            t = target(root, url)
            if t is None:
                continue
            f, frag = t
            if f == "RELATIVE":
                out.append("%s: <%s> %s -> relative path (use /absolute/)" % (here, tag, url))
                continue
            if f == "":
                f = page
            elif not f.is_file():
                why = "no such file"
                if (root / unquote(urlsplit(url).path.lstrip("/"))).is_dir():
                    why = "a directory without the trailing slash"
                out.append("%s: <%s> %s -> %s (%s)" % (here, tag, url, why, f.relative_to(root)))
                continue
            if frag and f.suffix == ".html":
                ids = parsed[f].ids if f in parsed else parse(f).ids
                if frag not in ids:
                    out.append("%s: <%s> %s -> no #%s in %s" % (here, tag, url, frag, f.relative_to(root)))
    return out


class Links(unittest.TestCase):
    def test_committed_site_has_no_broken_links(self):
        self.assertEqual(broken(REPO), [])

    def test_the_crawl_really_finds_things(self):
        files = list(pages(REPO))
        self.assertGreater(len(files), 30)  # home x12, faq/about x22, privacy, terms, journal hub ...
        refs = sum(len(parse(f).refs) for f in files)
        self.assertGreater(refs, 500)

    def test_a_planted_broken_link_is_caught(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "ok").mkdir()
            (tmp / "ok" / "index.html").write_text('<a href="/ok/">x</a><a id="here" href="#nope">y</a>')
            (tmp / "index.html").write_text(
                '<a href="/blog/">a</a><a href="/ok">b</a><a href="/ok/#here">c</a><a href="/ok/#gone">d</a>'
                '<a href="https://still.ipe.rest/missing.txt">e</a><a href="mailto:x@y.z">f</a><a href="https://example.com/x">g</a>'
                '<link rel="stylesheet" href="/assets/none.css?v=1"><a href="rel/path/">h</a><a href="#">i</a>')
            got = "\n".join(broken(tmp))
            for needle in ("/blog/ -> no such file", "/ok -> a directory without the trailing slash", "#gone", "missing.txt",
                           "/assets/none.css", "relative path", "ok/index.html: <a> #nope -> no #nope"):
                self.assertIn(needle, got)
            self.assertNotIn("mailto", got)
            self.assertNotIn("example.com", got)
            self.assertNotIn("/ok/#here", got)
            self.assertEqual(len(broken(tmp)), 7)
        finally:
            shutil.rmtree(tmp)

    def test_site_with_the_first_posts_published_has_no_broken_links(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
            # publish everything: the scheduled posts too (a clock after their publish_at), and the draft sample stays hidden
            r = subprocess.run([sys.executable, str(REPO / "scripts/build_journal.py"), "--root", str(tmp / "s"), "--now", "2099-01-01 00:00"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((tmp / "s/journal/ko/commute-get-off-early/index.html").is_file())
            self.assertTrue((tmp / "s/journal/ko/three-am-counting-hours/index.html").is_file())
            self.assertEqual(broken(tmp / "s"), [])
            home = (tmp / "s/ko/index.html").read_text(encoding="utf-8")
            self.assertIn('href="/journal/ko/"', home)  # the journal link is there once there is a post
            faq = (tmp / "s/ko/faq/index.html").read_text(encoding="utf-8")
            self.assertIn('href="/journal/ko/"', faq)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
