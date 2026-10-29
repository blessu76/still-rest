#!/usr/bin/env python3
"""Check sitemap.xml against the site — stdlib only (Python 3.8+). Exit 1 on any problem.

  python3 scripts/check_sitemap.py            # offline checks
  python3 scripts/check_sitemap.py --live     # + every sitemap URL answers HTTP 200 (run after deploy)

Offline checks:
  1. sitemap.xml is valid XML.
  2. Home: / (x-default) and /<lang>/ for all 11 languages are listed (static pages, no ?lang=), plus /<lang>/faq/ and
     /<lang>/about/ for all 11 languages, plus /privacy/ and /terms/.
  3. Every listed URL has a built page in this repo (<path>/index.html), and no listed URL carries a query string.
  4. hreflang (every <url> that has alternates): lists itself (the root only is the x-default) + x-default; every hreflang
     target is itself a <loc> in the sitemap; references are reciprocal (if A lists B under lang L, B lists A under A's lang).
  5. lastmod (SEO guide v1, P0-4): every <url> has one, a real date, never after today (--now, else the real KST clock); for a journal
     post it is the date of the page's own JSON-LD dateModified.
  6. page vs sitemap (P0-5/P0-6): each built page's <link rel=canonical> is exactly its <loc>, it is not noindex, and its html
     <link rel=alternate hreflang> set (with x-default) is the same set as the sitemap's xhtml:link set for that URL.
  7. robots.txt has `Sitemap: https://still.ipe.rest/sitemap.xml`.
  --live: every URL answers 200 at that very address (a redirect is a failure), not just "something".
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import KST, LANGS, SITE, parse_when  # noqa: E402

INFO_PAGES = ("faq", "about")  # /<lang>/faq/ and /<lang>/about/ (scripts/build_info.py)
LEGAL_PAGES = ("privacy", "terms")  # canonical form has the trailing slash (the directory index)
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "x": "http://www.w3.org/1999/xhtml"}


def expected_urls(root):
    """URLs that must be in the sitemap. Extended by the journal checks (see check())."""
    want = {SITE + "/"}
    want.update("%s/%s/" % (SITE, l) for l in LANGS)
    want.update("%s/%s/%s/" % (SITE, l, page) for l in LANGS for page in INFO_PAGES)
    want.update("%s/%s/" % (SITE, page) for page in LEGAL_PAGES)
    return want


class _Head(HTMLParser):
    """what check() needs from a built page: canonical, robots, hreflang alternates, JSON-LD blocks."""

    def __init__(self):
        super().__init__()
        self.canonical, self.robots, self.alternates, self.ld, self._ld, self._ns = [], [], [], [], False, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "noscript":
            self._ns += 1
        elif tag == "link" and not self._ns:
            if a.get("rel") == "canonical":
                self.canonical.append(a.get("href"))
            elif a.get("rel") == "alternate" and a.get("hreflang"):
                self.alternates.append((a["hreflang"], a.get("href")))
        elif tag == "meta" and (a.get("name") or "").lower() == "robots":
            self.robots.append(a.get("content") or "")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld = True
            self.ld.append("")

    def handle_endtag(self, tag):
        if tag == "noscript":
            self._ns = max(0, self._ns - 1)
        elif tag == "script":
            self._ld = False

    def handle_data(self, data):
        if self._ld:
            self.ld[-1] += data


def read_head(path):
    """-> _Head of a built page, or None when the file is not a real page (a stub in a test copy)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if "<html" not in text:
        return None
    h = _Head()
    h.feed(text)
    return h


def post_date_modified(head):
    """the date (YYYY-MM-DD) of the BlogPosting's dateModified, or None when the page has no BlogPosting."""
    for block in head.ld:
        try:
            d = json.loads(block)
        except ValueError:
            return "unparseable JSON-LD"
        if isinstance(d, dict) and d.get("@type") == "BlogPosting":
            return str(d.get("dateModified", ""))[:10]
    return None


def check(root, now=None):
    errs = []
    try:
        tree = ET.parse(root / "sitemap.xml")
    except (ET.ParseError, OSError) as ex:
        return ["sitemap.xml: %s" % ex], []
    urls, lastmods = {}, {}
    for u in tree.getroot().findall("s:url", NS):
        loc = (u.findtext("s:loc", namespaces=NS) or "").strip()
        urls[loc] = [(l.get("hreflang"), l.get("href")) for l in u.findall("x:link", NS)]
        lastmods[loc] = (u.findtext("s:lastmod", namespaces=NS) or "").strip()
    want = expected_urls(root)
    try:
        import build_journal as bj
        want |= bj.expected_sitemap_urls(root, now)
    except ImportError:  # journal not built into this checkout
        pass
    except ValueError as ex:
        return ["journal sources: %s" % ex], list(urls)
    for u in sorted(want - set(urls)):
        errs.append("missing from sitemap: %s" % u)
    for u in sorted(u for u in urls if "/journal/" in u and u not in want):
        errs.append("in sitemap but not a published journal page: %s" % u)
    for u in sorted(urls):
        if not u.startswith(SITE + "/"):
            errs.append("not on %s: %s" % (SITE, u))
        elif "?" in u or "#" in u:
            errs.append("query/fragment in sitemap URL: %s" % u)
        elif not (root / u[len(SITE) + 1:] / "index.html").is_file():
            errs.append("no built page for %s (%s/index.html)" % (u, u[len(SITE) + 1:].rstrip("/") or "."))
    for loc, links in urls.items():
        if not links:  # a page without alternates (single language) needs no hreflang
            continue
        langs = [l for l, _ in links]
        if len(set(langs)) != len(langs):
            errs.append("%s: duplicate hreflang" % loc)
        if "x-default" not in langs:
            errs.append("%s: no x-default" % loc)
        mine = [l for l, h in links if h == loc and l != "x-default"]
        hub_page = loc == SITE + "/journal/" or loc.startswith(SITE + "/journal/page/")
        if not mine and not hub_page and loc != SITE + "/":  # hub (all its pages) and root are only the x-default of their language pages
            errs.append("%s: does not list itself in hreflang" % loc)
        for lang, href in links:
            if href not in urls:
                errs.append("%s: hreflang %s -> %s is not in the sitemap" % (loc, lang, href))
            elif lang != "x-default" and href != loc and mine and (mine[0], loc) not in urls[href]:
                errs.append("%s: hreflang %s -> %s is not reciprocal (it does not list %s as %s)" % (loc, lang, href, loc, mine[0]))
    errs += check_lastmod(urls, lastmods, now)
    errs += check_pages(root, urls, lastmods)
    errs += check_robots(root)
    return errs, list(urls)


def check_lastmod(urls, lastmods, now=None):
    """every <url> has a real date as lastmod, none after today (KST) — a future lastmod is a lie to the crawler."""
    today = (now or dt.datetime.now(KST)).astimezone(KST).date()
    errs = []
    for loc in urls:
        raw = lastmods.get(loc, "")
        if not raw:
            errs.append("%s: no lastmod" % loc)
            continue
        try:
            d = dt.date.fromisoformat(raw[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}(T.*)?$", raw) else None
        except ValueError:
            d = None
        if d is None:
            errs.append("%s: lastmod is not a date: %r" % (loc, raw))
        elif d > today:
            errs.append("%s: lastmod %s is after today (%s)" % (loc, raw, today))
    return errs


def check_pages(root, urls, lastmods):
    """each built page against its sitemap row: self canonical, indexable, same hreflang set, journal post lastmod = JSON-LD dateModified."""
    errs = []
    for loc, links in urls.items():
        if not loc.startswith(SITE + "/"):
            continue
        head = read_head(root / loc[len(SITE) + 1:] / "index.html")
        if head is None:
            continue
        if head.canonical != [loc]:
            errs.append("%s: canonical is %s, expected exactly itself" % (loc, head.canonical or "missing"))
        if any("noindex" in r.lower() for r in head.robots):
            errs.append("%s: is in the sitemap but noindex" % loc)
        html_set = sorted(head.alternates)
        if html_set != sorted(links):
            errs.append("%s: html hreflang set differs from the sitemap's (html only: %s; sitemap only: %s)" % (
                loc, sorted(set(html_set) - set(links)) or "-", sorted(set(links) - set(html_set)) or "-"))
        dm = post_date_modified(head)
        if dm is not None and dm != lastmods.get(loc, "")[:10]:
            errs.append("%s: sitemap lastmod %s != JSON-LD dateModified %s" % (loc, lastmods.get(loc) or "(none)", dm))
    return errs


def check_robots(root):
    try:
        text = (root / "robots.txt").read_text(encoding="utf-8")
    except OSError:
        return ["robots.txt: missing"]
    if not re.search(r"(?mi)^Sitemap:[ \t]*%s/sitemap\.xml[ \t]*$" % re.escape(SITE), text):
        return ["robots.txt: no `Sitemap: %s/sitemap.xml` line" % SITE]
    return []


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def live(urls):
    """GET every URL without following redirects: a sitemap URL must answer 200 itself (a 301/302 means it is not the final address)."""
    errs = []
    opener = urllib.request.build_opener(_NoRedirect)
    for u in urls:
        try:
            with opener.open(urllib.request.Request(u, headers={"User-Agent": "check_sitemap/1"}), timeout=20) as r:
                if r.status != 200:
                    errs.append("HTTP %s: %s" % (r.status, u))
        except urllib.error.HTTPError as ex:
            errs.append("HTTP %s%s: %s" % (ex.code, " (redirect — not the final URL)" if 300 <= ex.code < 400 else "", u))
        except Exception as ex:  # noqa: BLE001 — any failure is a failed check
            errs.append("%s: %s" % (u, ex))
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--now", metavar="WHEN", help="the clock the site was built with (`now` or `YYYY-MM-DD HH:MM` KST) — scheduled journal posts "
                    "due by then must be in the sitemap; same value as build_journal.py --now")
    ap.add_argument("--live", action="store_true", help="also GET every sitemap URL and require HTTP 200")
    a = ap.parse_args()
    errs, urls = check(Path(a.root).resolve(), parse_when(a.now) if a.now else None)
    if a.live and not errs:
        errs += live(urls)
    if errs:
        print("sitemap: %d problem(s)\n  " % len(errs) + "\n  ".join(errs), file=sys.stderr)
        return 1
    print("sitemap: OK — %d URL(s)%s" % (len(urls), ", all HTTP 200" if a.live else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
