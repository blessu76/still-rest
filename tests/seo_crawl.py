"""Shared helper of the SEO guide v1 tests: build the whole site the way the deploy runner does, then read every page like a crawler would.
Not a test module (unittest only collects test*.py)."""
import json
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = ("content", "scripts", "tests", ".git", ".github")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from site_common import ENDED_DIRS, LANGS, MOVED, SITE  # noqa: E402

CLOCK = "2026-10-29 23:59"  # the real "today" of this work: the 10-30 posts are scheduled and must stay out of the build


# ---- what a crawl-wide SEO check treats as "the index" (ONE place for the exclusions; every SEO test goes through `live()`).
# - ACTIVE_LANGS: the 12 languages of the site (kit list: en ko ja zh-Hant es pt-BR fr de id th vi tr). They keep the full strictness.
# - frozen pages: the ended languages (site_common.ENDED_DIRS = zh ru ar hi, also journal/zh, journal/ru) stay on disk untouched but are no
#   longer built or listed, so their hreflang / language select still describe the old 13-language site. They are not in the sitemap and
#   are not part of the current index, so cluster checks (reciprocity, "target exists", language set) must not look at them.
# - redirect stubs: the old /pt/... and /journal/pt/... (site_common.MOVED) are noindex pages with canonical = the new /pt-BR/... address,
#   not index targets either; they are checked separately by their own tests (see is_stub / stub_target).
ACTIVE_LANGS = tuple(LANGS)
FROZEN_DIRS = tuple(ENDED_DIRS)
STUB_DIRS = tuple(MOVED)


def _lang_dir(url):
    """first language-like folder of a page address: /<d>/... or /journal/<d>/... (None for /, /journal/, /privacy/ ...)"""
    parts = url[len(SITE) + 1:].strip("/").split("/")
    if parts and parts[0] == "journal":
        return parts[1] if len(parts) > 1 else None
    return parts[0] if parts else None


def is_frozen(url):
    return _lang_dir(url) in FROZEN_DIRS


def is_stub(url):
    """old-address redirect stub (/pt/, /pt/faq/, /pt/about/, /journal/pt/, /journal/pt/<slug>/ ...)"""
    return _lang_dir(url) in STUB_DIRS


def stub_target(url):
    """the new address of a moved page: /pt/x/ -> /pt-BR/x/, /journal/pt/x/ -> /journal/pt-BR/x/"""
    old = _lang_dir(url)
    return url.replace("/%s/" % old, "/%s/" % MOVED[old], 1) if old in MOVED else None


def live(pages):
    """{url: Page} without the frozen ended-language pages and the redirect stubs = the pages that take part in the current index."""
    return {u: p for u, p in pages.items() if not is_frozen(u) and not is_stub(u)}


def stubs(pages):
    return {u: p for u, p in pages.items() if is_stub(u)}


class Page(HTMLParser):
    """title · meta · <link>s · h1 count · JSON-LD documents of one page (links inside <noscript> are ignored)."""

    def __init__(self, url, text):
        super().__init__(convert_charrefs=True)
        self.url, self.lang = url, None
        self.title, self.meta, self.links, self.h1, self.ld, self.anchors = None, {}, [], 0, [], []
        self.h1_text = ""
        self._in_title, self._in_ld, self._in_h1, self._noscript = False, False, False, 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title, self.title = True, ""
        elif tag == "noscript":
            self._noscript += 1
        elif tag == "meta":
            key = a.get("name") or a.get("property")
            if key:
                self.meta.setdefault(key, []).append(a.get("content", ""))
        elif tag == "link" and not self._noscript:
            self.links.append(a)
        elif tag == "h1":
            self.h1 += 1
            self._in_h1 = True
        elif tag == "a" and a.get("href"):
            self.anchors.append(a)
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld = True
            self.ld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "noscript":
            self._noscript = max(0, self._noscript - 1)
        elif tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_ld:
            self.ld[-1] += data
        if self._in_h1:
            self.h1_text += data

    # ---- what the tests ask for
    def first(self, key):
        return (self.meta.get(key) or [None])[0]

    @property
    def description(self):
        return self.first("description")

    @property
    def robots(self):
        return self.first("robots") or ""

    @property
    def indexable(self):
        return "noindex" not in self.robots.lower()

    @property
    def canonicals(self):
        return [l.get("href") for l in self.links if l.get("rel") == "canonical"]

    @property
    def hreflangs(self):
        return [(l["hreflang"], l.get("href")) for l in self.links if l.get("rel") == "alternate" and l.get("hreflang")]

    def docs(self):
        return [json.loads(x) for x in self.ld]

    def blog_posting(self):
        posts = [d for d in self.docs() if d.get("@type") == "BlogPosting"]
        return posts[0] if posts else None


def url_of(root, f):
    rel = f.parent.relative_to(root).as_posix()
    return "https://still.ipe.rest/" + ("" if rel == "." else rel + "/")


def crawl(root):
    """{url: Page} of every index.html of a built site (not the build sources)."""
    root = Path(root)
    out = {}
    for f in sorted(root.rglob("index.html")):
        if f.relative_to(root).parts[0] in SOURCES:
            continue
        u = url_of(root, f)
        out[u] = Page(u, f.read_text(encoding="utf-8"))
    return out


def build_full(clock=CLOCK):
    """copy of the repo built with the deploy runner's command (`build_journal.py --now <clock>`); returns the temp dir (caller removes it)."""
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(REPO, tmp / "s", ignore=shutil.ignore_patterns(".git", "__pycache__"))
    r = subprocess.run([sys.executable, str(REPO / "scripts/build_journal.py"), "--root", str(tmp / "s"), "--now", clock], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return tmp


_CACHE = {}


def full_site(clock=CLOCK):
    """(root, {url: Page}) of the full build at `clock`, built once per test run and shared by every SEO test module."""
    import atexit
    if clock not in _CACHE:
        tmp = build_full(clock)
        atexit.register(shutil.rmtree, tmp, True)
        _CACHE[clock] = (tmp / "s", crawl(tmp / "s"))
    return _CACHE[clock]


def committed_site():
    if "committed" not in _CACHE:
        _CACHE["committed"] = (REPO, crawl(REPO))
    return _CACHE["committed"]
