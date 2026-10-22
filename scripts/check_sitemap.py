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
"""
import argparse
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import LANGS, SITE  # noqa: E402

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


def check(root):
    errs = []
    try:
        tree = ET.parse(root / "sitemap.xml")
    except (ET.ParseError, OSError) as ex:
        return ["sitemap.xml: %s" % ex], []
    urls = {}
    for u in tree.getroot().findall("s:url", NS):
        loc = (u.findtext("s:loc", namespaces=NS) or "").strip()
        urls[loc] = [(l.get("hreflang"), l.get("href")) for l in u.findall("x:link", NS)]
    want = expected_urls(root)
    try:
        import build_journal as bj
        want |= bj.expected_sitemap_urls(root)
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
        if not mine and loc not in (SITE + "/journal/", SITE + "/"):  # hub and root are only the x-default of their language pages
            errs.append("%s: does not list itself in hreflang" % loc)
        for lang, href in links:
            if href not in urls:
                errs.append("%s: hreflang %s -> %s is not in the sitemap" % (loc, lang, href))
            elif lang != "x-default" and href != loc and mine and (mine[0], loc) not in urls[href]:
                errs.append("%s: hreflang %s -> %s is not reciprocal (it does not list %s as %s)" % (loc, lang, href, loc, mine[0]))
    return errs, list(urls)


def live(urls):
    errs = []
    for u in urls:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "check_sitemap/1"}), timeout=20) as r:
                if r.status != 200:
                    errs.append("HTTP %s: %s" % (r.status, u))
        except Exception as ex:  # noqa: BLE001 — any failure is a failed check
            errs.append("%s: %s" % (u, ex))
    return errs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--live", action="store_true", help="also GET every sitemap URL and require HTTP 200")
    a = ap.parse_args()
    errs, urls = check(Path(a.root).resolve())
    if a.live and not errs:
        errs += live(urls)
    if errs:
        print("sitemap: %d problem(s)\n  " % len(errs) + "\n  ".join(errs), file=sys.stderr)
        return 1
    print("sitemap: OK — %d URL(s)%s" % (len(urls), ", all HTTP 200" if a.live else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
