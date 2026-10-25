#!/usr/bin/env python3
"""Build the still.ipe.rest home page as 11 static language pages — stdlib only (Python 3.8+).

Source   content/home/template.html   English markup with data-i18n / data-i18n-ph hooks and {{PLACEHOLDERS}}
         content/home/i18n.json       strings per language (a missing key falls back to English)
Writes   /<lang>/index.html           en ko ja zh es pt id ru vi fr de — html lang/dir, own title·description·og:locale,
                                      canonical = itself, hreflang 11 + x-default
         /index.html                  x-default: English content, canonical "/", plus a *non-forcing* language hint
                                      (no automatic redirect for crawlers or people; old ?lang=xx links go to /xx/)
         sitemap.xml                  between <!-- home:start --> / <!-- home:end -->
         llms.txt                     between <!-- home:llms:start --> / <!-- home:llms:end -->

`python3 scripts/build_journal.py` calls build() here too, so one command builds journal + home (the home page shows the
latest journal posts). Running this file alone builds the home pages without journal cards.

    python3 scripts/build_home.py            # write the pages
    python3 scripts/build_home.py --check    # fail if the committed pages are not what the build would write
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import LANGS, SITE, check_fresh, esc, lang_url, replace_between, stamped_date, with_localtime  # noqa: E402

TEMPLATE = Path("content") / "home" / "template.html"
STRINGS = Path("content") / "home" / "i18n.json"
STAMP = Path("content") / "home" / "stamp.json"  # {hash, date}: when template/i18n last changed (sitemap lastmod); written by this script
LANG_ATTR = re.compile(r'(<(?P<tag>[a-zA-Z0-9]+)(?P<attrs>[^>]*?\sdata-i18n="(?P<key>[^"]+)"[^>]*)>)(?P<inner>.*?)(</(?P=tag)>)', re.S)
PH_ATTR = re.compile(r'<[a-zA-Z0-9]+[^>]*?\sdata-i18n-ph="([^"]+)"[^>]*>')
NAV_SCRIPT = """<script>
(function () {
  var sel = document.getElementById('lang');
  if (sel) sel.addEventListener('change', function () {
    try { localStorage.setItem('still_lang', this.value); } catch (e) {}
    location.href = '/' + this.value + '/';
  });
%s})();
</script>"""
HINT_JS = """  // root only: suggest (never force) the visitor's language — stored choice first, then the browser's list
  var hint = document.getElementById('langHint');
  var NAMES = %s, CLOSE = %s;
  if (hint) {
    var off = false; try { off = sessionStorage.getItem('still_hint_off') === '1'; } catch (e) {}
    var pick = null, stored = null;
    try { stored = localStorage.getItem('still_lang'); } catch (e) {}
    if (stored && NAMES[stored]) pick = stored;
    else { try { var list = navigator.languages || [navigator.language || '']; for (var i = 0; i < list.length && !pick; i++) { var c = String(list[i]).toLowerCase().split('-')[0]; if (NAMES[c]) pick = c; } } catch (e) {} }
    if (pick && pick !== 'en' && !off) {
      hint.innerHTML = '<a href="/' + pick + '/" hreflang="' + pick + '" lang="' + pick + '">' + NAMES[pick] + ' <span aria-hidden="true">→</span></a><button type="button" aria-label="' + CLOSE + '">×</button>';
      hint.hidden = false;
      hint.querySelector('button').addEventListener('click', function () { hint.hidden = true; try { sessionStorage.setItem('still_hint_off', '1'); } catch (e) {} });
    }
  }
"""
LEGACY_JS = ("<script>(function(){try{var l=new URLSearchParams(location.search).get('lang');"
             "if(l&&/^(%s)$/.test(l))location.replace('/'+l+'/'+location.hash);}catch(e){}})();</script>\n")
HINT_CSS_ID = "langHint"
ARIA_KEYS = ("aria_lang", "aria_verse_card", "aria_save", "aria_listen", "aria_email", "aria_footer", "og_image_alt")  # {{key}} in the template


def render_page(tpl, strings, lang, root, cards_html=None, journal_href="/journal/", has_journal=None):
    """one home page. root=True -> /index.html (x-default); lang is then 'en'. cards_html: journal cards or None.
    journal_href: where this page's Journal links go (/journal/<lang>/ when that language has posts, else the hub).
    has_journal: show the Journal links (top bar + footer) — True once ANY post exists, in any language (a language without
    posts links to the hub); None -> only when this page has cards."""
    d = dict(strings["en"], **strings[lang])
    canonical = SITE + "/" if root else lang_url(lang)
    out = tpl

    def i18n(m):
        val = d.get(m.group("key"))
        if val is None:
            return m.group(0)
        return m.group(1) + html.escape(str(val), quote=False) + m.group(6)
    out = LANG_ATTR.sub(i18n, out)

    def placeholder(m):
        v = d.get(m.group(1))
        if v is None:
            return m.group(0)
        tag = m.group(0)
        if 'placeholder="' in tag:
            return re.sub(r'placeholder="[^"]*"', lambda _: 'placeholder="%s"' % esc(v), tag, count=1)
        return tag[:-1] + ' placeholder="%s">' % esc(v)
    out = PH_ATTR.sub(placeholder, out)

    hreflang = "\n".join('<link rel="alternate" hreflang="%s" href="%s">' % (l, lang_url(l)) for l in LANGS)
    hreflang += '\n<link rel="alternate" hreflang="x-default" href="%s/">' % SITE
    og = '<meta property="og:locale" content="%s">' % LANGS[lang]["og"] + "".join(
        '\n<meta property="og:locale:alternate" content="%s">' % LANGS[l]["og"] for l in LANGS if l != lang)
    options = "\n".join('    <option value="%s"%s>%s</option>' % (l, " selected" if l == lang else "", LANGS[l]["name"]) for l in LANGS)
    page_dict = {k: d[k] for k in ("letters_thanks",) if k in d}
    page_script = "<script>window.__PAGE=%s;</script>" % json.dumps({"lang": lang, "dict": page_dict}, ensure_ascii=False)
    names = json.dumps({l: LANGS[l]["name"] for l in LANGS}, ensure_ascii=False)
    ld_desc = strings[lang].get("ld_desc") or d["meta_desc"]  # structured data: English has its own long text, the others reuse their meta description
    lang_links = '<nav class="foot-langs" aria-label="%s">\n%s\n    </nav>' % (esc(d["aria_lang"]), "\n".join(
        '      <a href="%s/" hreflang="%s" lang="%s"%s>%s</a>' % ("/" + l, l, l, ' aria-current="true"' if l == lang and not root else "", LANGS[l]["name"]) for l in LANGS))
    subs = {
        "LANG": lang, "DIR": LANGS[lang]["dir"], "CANONICAL": esc(canonical), "HREFLANG": hreflang, "OG_LOCALE": og,
        "LANG_OPTIONS": options, "LEGACY_SCRIPT": LEGACY_JS % "|".join(LANGS) if root else "", "PAGE_SCRIPT": page_script,
        "LANG_HINT": '<div class="lang-hint" id="%s" hidden></div>\n' % HINT_CSS_ID if root else "",
        "NAV_SCRIPT": NAV_SCRIPT % (HINT_JS % (names, json.dumps(d["aria_close"], ensure_ascii=False)) if root else ""),
        "meta_title": esc(d["meta_title"]), "meta_desc": esc(d["meta_desc"]),
        # social cards: English keeps its own two short texts; other languages reuse their meta description
        "og_desc": esc(strings[lang].get("og_desc") or d["meta_desc"]), "tw_desc": esc(strings[lang].get("tw_desc") or d["meta_desc"]),
        "JOURNAL_HREF": journal_href, "LD_DESC": json.dumps(ld_desc, ensure_ascii=False), "LANG_LINKS": lang_links,
    }
    subs.update({k: esc(d[k]) for k in ARIA_KEYS})
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: subs[m.group(1)], out)
    if cards_html is not None:  # journal section (present in the template once the journal exists)
        out = journal_section(out, cards_html)
    return with_localtime(journal_links(out, bool(cards_html) if has_journal is None else has_journal))


def journal_links(out, has_posts):
    """the Journal links (marked data-journal-top = top bar, data-journal-link = footer in the template): shown only while there is a
    post to read — like the journal section, they appear on their own once the first post is published. Without posts (also when
    build_home runs alone) they go."""
    link = re.compile(r'[ \t]*<a [^>]*\bdata-journal-(?:link|top)\b[^>]*>.*?</a>\n?', re.S)
    if has_posts:
        return out.replace(" data-journal-link", "").replace(" data-journal-top", "")
    return link.sub("", out)


def journal_section(out, cards_html):
    """fill the journal cards between the template markers; no cards -> hide the whole section."""
    if "<!-- journal:home:start" not in out:
        return out
    out = replace_between(out, r"<!-- journal:home:start[^>]*-->", "<!-- journal:home:end -->", cards_html, "home template")
    out, n = re.subn(r'(<section class="journal"[^>]*?)( hidden)?>',
                     lambda m: m.group(1) + ("" if cards_html else " hidden") + ">", out, count=1)
    if n != 1:
        raise SystemExit('home template: <section class="journal"> not found')
    return out


def home_updated(root):
    """date the home copy (template + i18n) last changed (content/home/stamp.json, see site_common.stamped_date)."""
    return stamped_date(root, (TEMPLATE, STRINGS), STAMP)


def sitemap_block(home_date, newest_post_date=None):
    last = max(home_date, newest_post_date or "")
    links = "".join('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>\n' % (l, lang_url(l)) for l in LANGS)
    links += '    <xhtml:link rel="alternate" hreflang="x-default" href="%s/"/>\n' % SITE
    img = "    <image:image>\n      <image:loc>%s/og-image.png</image:loc>\n    </image:image>\n" % SITE
    rows = ["  <url>\n    <loc>%s/</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>1.0</priority>\n%s%s  </url>" % (SITE, last, links, img)]
    for l in LANGS:
        rows.append("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>%s</priority>\n%s%s  </url>"
                    % (lang_url(l), last, "0.9" if l in ("en", "ko") else "0.8", links, img))
    return "\n".join(rows) + "\n"


def llms_block():
    lines = ["## Home page in %d languages (static pages, one URL per language)" % len(LANGS)]
    lines += ["- [%s](%s)" % (LANGS[l]["name"], lang_url(l)) for l in LANGS]
    return "\n".join(lines) + "\n"


def build(root, cards_by_lang=None, href_by_lang=None, newest_post_date=None):
    """write /index.html + /<lang>/index.html and the home blocks of sitemap.xml and llms.txt.
    cards_by_lang / href_by_lang: {lang: ...} from build_journal (None -> no journal cards, links go to the hub)."""
    tpl = (root / TEMPLATE).read_text(encoding="utf-8")
    strings = json.loads((root / STRINGS).read_text(encoding="utf-8"))
    missing = [l for l in LANGS if l not in strings]
    if missing:
        raise SystemExit("home i18n.json lacks: " + " ".join(missing))
    any_posts = bool(cards_by_lang) and any(cards_by_lang.values())  # a post in any language -> every home page links the Journal (hub if its own language has none)
    written = []
    for lang, is_root in [("en", True)] + [(l, False) for l in LANGS]:
        cards = None if cards_by_lang is None else cards_by_lang.get(lang, "")
        page = render_page(tpl, strings, lang, is_root, cards, (href_by_lang or {}).get(lang, "/journal/"), any_posts)
        path = root / "index.html" if is_root else root / lang / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
        written.append(path)
    sm = root / "sitemap.xml"
    sm.write_text(replace_between(sm.read_text(encoding="utf-8"), r"<!-- home:start[^>]*-->", "  <!-- home:end -->",
                                  sitemap_block(home_updated(root), newest_post_date), "sitemap.xml"), encoding="utf-8")
    llms = root / "llms.txt"
    llms.write_text(replace_between(llms.read_text(encoding="utf-8"), r"<!-- home:llms:start[^>]*-->",
                                    "<!-- home:llms:end -->", llms_block(), "llms.txt"), encoding="utf-8")
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="site root (default: this repo)")
    ap.add_argument("--check", action="store_true", help="write nothing; fail if the committed pages differ from a fresh build")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    if (root / "content" / "journal" / "ui.json").is_file():
        # the journal owns the home pages once it exists (cards of the newest posts): build and check through it
        import build_journal
        if a.check:
            code, msg = build_journal.build(root, check_only=True)
            diffs = check_fresh(root, lambda r: build_journal.build(r)) if code == 0 else [msg]
            if diffs:
                print("home: out of date — run python3 scripts/build_journal.py\n  " + "\n  ".join(diffs), file=sys.stderr)
                return 1
            print("home: OK — pages are up to date")
            return 0
        code, msg = build_journal.build(root)
        print(msg, file=sys.stderr if code else sys.stdout)
        return code
    if a.check:
        diffs = check_fresh(root, build)
        if diffs:
            print("home: out of date — run python3 scripts/build_home.py\n  " + "\n  ".join(diffs), file=sys.stderr)
            return 1
        print("home: OK — pages are up to date")
        return 0
    written = build(root)
    print("home: built %d page(s)" % len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
