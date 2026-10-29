#!/usr/bin/env python3
"""Notify IndexNow (Bing, Naver, Yandex, ...) about new or changed URLs.

Run AFTER the site is published (the key file must already be live):

    python3 scripts/indexnow.py                 # every <loc> in sitemap.xml
    python3 scripts/indexnow.py URL [URL ...]   # only these URLs
    python3 scripts/indexnow.py --dry-run       # print the payload, send nothing
    python3 scripts/indexnow.py --changed --now "2026-10-30 10:06" --previous prev-sitemap.xml
        # what the deploy workflow runs: only the URLs that changed in THIS deploy (see changed_urls)

The key is the repo-root file named <32 hex>.txt whose single line is the key
itself. It is a public file (not a secret). Standard library only.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import KST, parse_when  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_FILE_RE = re.compile(r"^([0-9a-f]{32})\.txt$")
SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
LOC_TAG = SM_NS + "loc"
RETRY_STATUS = (0, 403, 500, 502, 503, 504)  # 0 = no answer (network error); 403 = the key file is not live yet right after a deploy; 5xx = a hiccup at the endpoint


def find_key(root):
    """Return the key whose <key>.txt file in `root` contains exactly that key."""
    for p in sorted(Path(root).iterdir()):
        m = KEY_FILE_RE.match(p.name)
        if m and p.read_text(encoding="utf-8").strip() == m.group(1):
            return m.group(1)
    raise SystemExit("no IndexNow key file (<32 hex>.txt containing its own name) in " + str(root))


def sitemap_urls(sitemap_path):
    """All <loc> values of a sitemap (xhtml:link alternates are not included)."""
    tree = ET.parse(sitemap_path)
    urls = [e.text.strip() for e in tree.iter(LOC_TAG) if e.text and e.text.strip()]
    return list(dict.fromkeys(urls))


def sitemap_entries(sitemap_path):
    """[(loc, lastmod or None)] of a sitemap, in file order (xhtml:link alternates are not included)."""
    out = []
    for u in ET.parse(sitemap_path).getroot().iter(SM_NS + "url"):
        loc = (u.findtext(LOC_TAG) or "").strip()
        if loc:
            out.append((loc, (u.findtext(SM_NS + "lastmod") or "").strip() or None))
    return out


ARTICLE_RE = re.compile(r"^/journal/[a-z]{2}/(?!page/)[a-z0-9-]+/$")  # one journal post; the lists, pages 2+, home pages and info pages are not


def changed_urls(entries, today, previous=None):
    """The URLs worth telling IndexNow about after a deploy: new pages, lists and home pages whose sitemap `lastmod` is TODAY (KST date string).
    entries/previous = [(loc, lastmod)] of the sitemap being deployed / of the one that was live before (None = unknown).
    * a lastmod after today is never sent (nothing in the future is public yet; the build only emits due posts, this is the second lock)
    * with `previous`: nothing new (no URL that is not already live with the same lastmod) -> nothing is sent, so the hourly backup runs and
      code-only pushes stay silent. When something IS new, a post already live with today's lastmod is skipped, but every list/home page of
      today is sent: a second post on the same day leaves their lastmod (a date) unchanged although their cards changed.
    * the sitemap itself is added when anything is sent. Order = sitemap order, no duplicates."""
    todays = [(loc, last) for loc, last in entries if last == today]
    if previous is None:
        urls = [loc for loc, _ in todays]
    else:
        live = set(previous)
        if all(e in live for e in todays):
            return []
        urls = [loc for loc, last in todays if (loc, last) not in live or not ARTICLE_RE.match(urlsplit(loc).path)]
    urls = list(dict.fromkeys(urls))
    if urls:
        host = urlsplit(urls[0])
        urls.append("%s://%s/sitemap.xml" % (host.scheme, host.netloc))
    return urls


def build_payload(key, urls):
    if not urls:
        raise SystemExit("no URLs to submit")
    hosts = {urlsplit(u).netloc for u in urls}
    if len(hosts) != 1 or "" in hosts:
        raise SystemExit("all URLs must share one host, got: " + ", ".join(sorted(hosts)))
    host = hosts.pop()
    return {
        "host": host,
        "key": key,
        "keyLocation": "https://%s/%s.txt" % (host, key),
        "urlList": list(urls),
    }


def send(payload, endpoint=ENDPOINT, timeout=30, retries=3, wait=15, sleep=time.sleep):
    """POST the payload; returns the HTTP status. A 403 (key file not reachable yet) or 5xx is retried `retries` times in total."""
    status = None
    for attempt in range(retries):
        status = _post(payload, endpoint, timeout)
        if status not in RETRY_STATUS or attempt == retries - 1:
            break
        sleep(wait)
    return status


def _post(payload, endpoint, timeout):
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="URLs to submit (default: every <loc> in sitemap.xml)")
    ap.add_argument("--root", default=str(ROOT), help="site root (default: this repo)")
    ap.add_argument("--dry-run", action="store_true", help="print the payload, send nothing")
    ap.add_argument("--changed", action="store_true", help="send only the URLs whose sitemap lastmod is today (see --now) and that are not already live (--previous)")
    ap.add_argument("--now", metavar="WHEN", help="with --changed: the clock of this deploy (`now` or `YYYY-MM-DD HH:MM` KST) — the same value the build used")
    ap.add_argument("--previous", metavar="SITEMAP", help="with --changed: the sitemap that was live before this deploy (a missing/unreadable file = unknown, send all of today's)")
    a = ap.parse_args(argv)

    root = Path(a.root)
    if a.changed:
        if a.urls:
            ap.error("--changed and explicit URLs exclude each other")
        today = (parse_when(a.now) if a.now else dt.datetime.now(KST)).astimezone(KST).date().isoformat()
        try:
            previous = sitemap_entries(a.previous) if a.previous else None
        except (OSError, ET.ParseError):
            previous = None
        urls = changed_urls(sitemap_entries(root / "sitemap.xml"), today, previous)
        if not urls:
            print("IndexNow: nothing changed today (%s) — nothing to send" % today)
            return 0
        print("IndexNow: %d URL(s) changed on %s%s" % (len(urls), today, "" if previous is not None else " (previous sitemap unknown)"))
    else:
        urls = a.urls or sitemap_urls(root / "sitemap.xml")
    payload = build_payload(find_key(root), urls)
    if a.dry_run:
        print("POST " + ENDPOINT)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    status = send(payload)
    print("IndexNow %s: HTTP %d (%d URLs)" % (payload["host"], status, len(urls)))
    if status in (200, 202):
        return 0
    print("200/202 = ok; 403 = key file not live yet / key mismatch; 422 = URL host mismatch; 429 = too many requests", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
