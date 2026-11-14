#!/usr/bin/env python3
"""Redirect pages for the ended-language folders zh/ ru/ ar/ hi/ — stdlib + ipe_web_kit.redirects (v0.7.x rules).

Rules (kit LEGACY_REDIRECTS, Davy): zh -> zh-Hant, ar/hi/ru -> en (pt -> pt-BR is written by build_home/build_info/build_journal via MOVED).
Every page that already exists under the old folder (home, faq, about, journal list/posts) is overwritten in place with a kit redirect page
pointing at the same page in the new language, or at the English one when the new language has no such page. Nothing is deleted.
The old folders are in no sitemap / hreflang / list (check: kit sitemap_leaks).

Usage:  python3 scripts/build_redirects.py [--root DIR] [--check]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import ENDED_DIRS, SITE, redirect_stub, kit_redirects  # noqa: E402


def pages_of(root, old):
    """[(rel path under root, kind, rest)] for every page that exists under the old language's folders."""
    out = []
    for f in sorted((root / old).rglob("index.html")) if (root / old).is_dir() else []:
        rest = f.parent.relative_to(root / old).as_posix()
        out.append((f.relative_to(root).as_posix(), "site", "" if rest == "." else rest + "/"))
    jd = root / "journal" / old
    for f in sorted(jd.rglob("index.html")) if jd.is_dir() else []:
        rest = f.parent.relative_to(jd).as_posix()
        out.append((f.relative_to(root).as_posix(), "journal", "" if rest == "." else rest + "/"))
    return out


def exists(root, url_path):
    return (root / url_path.strip("/") / "index.html").is_file()


def target(root, old, kind, rest):
    new = kit_redirects.LEGACY_REDIRECTS[old]
    if kind == "site":
        cands = ["/%s/%s" % (new, rest), "/en/%s" % rest, "/%s/" % new]
    else:
        cands = ["/journal/%s/%s" % (new, rest), "/journal/en/%s" % rest, "/journal/%s/" % new, "/journal/en/", "/journal/"]
    for c in cands:
        if exists(root, c):
            return new if c.startswith(("/%s/" % new, "/journal/%s/" % new)) else "en", SITE + c
    return "en", SITE + "/"


def build(root, check=False):
    bad = []
    for old in ENDED_DIRS:
        for rel, kind, rest in pages_of(root, old):
            lang, url = target(root, old, kind, rest)
            want = redirect_stub(url, lang=lang)
            f = root / rel
            if f.read_text(encoding="utf-8") != want:
                bad.append(rel)
                if not check:
                    f.write_text(want, encoding="utf-8")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    bad = build(Path(a.root), a.check)
    if a.check and bad:
        print("stale redirect pages (run scripts/build_redirects.py): " + ", ".join(bad), file=sys.stderr)
        return 1
    print("%s %d redirect page(s)" % ("stale" if a.check else "wrote", len(bad)) if bad else "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
