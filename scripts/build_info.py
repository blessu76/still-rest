#!/usr/bin/env python3
"""Build the still.ipe.rest info pages — FAQ and "how still() is different from other apps called Still" — stdlib only (Python 3.8+).

Source   content/info/pages.json    one entry per language (11): questions/answers, the about paragraph, titles, meta descriptions
         content/home/i18n.json     verse_text / hero_tag (the {verse} / {psalm} placeholders) and footer labels
Writes   /<lang>/faq/index.html     FAQPage JSON-LD (the same questions and answers that are visible on the page)
         /<lang>/about/index.html   AboutPage JSON-LD (the app as mainEntity; no sameAs / downloadUrl until a store page exists)
         sitemap.xml                between <!-- info:start --> / <!-- info:end -->  (22 URLs with hreflang)
         llms.txt                   between <!-- info:llms:start --> / <!-- info:llms:end -->
         content/info/stamp.json    {hash, date} of pages.json — the sitemap lastmod of these pages

It is called by scripts/build_journal.py (one command builds journal + home + info) and borrows its head/header/footer, so the
pages look like the journal pages. The privacy policy stays ONE page (/privacy/, en + ko toggle): legal text is not machine
translated into 11 languages; the FAQ answers it in every language and links to it.

    python3 scripts/build_journal.py         # builds these pages too (they need its journal list state for the footer links)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import LANGS, ORG, SITE, esc, lang_url, replace_between, stamped_date  # noqa: E402

PAGES = ("faq", "about")
SOURCE = Path("content") / "info" / "pages.json"
STAMP = Path("content") / "info" / "stamp.json"
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def page_url(lang, page):
    return "%s/%s/%s/" % (SITE, lang, page)


def load(root):
    data = json.loads((root / SOURCE).read_text(encoding="utf-8"))
    return {l: data[l] for l in LANGS}


def fill(text, lang, home):
    """{L} -> the language folder; {psalm}/{verse} -> the home page's own wording of Psalm 46:10 in that language."""
    d = dict(home["en"], **home[lang])
    psalm = d["hero_tag"].split("—")[-1].strip()
    return text.replace("{L}", lang).replace("{psalm}", psalm).replace("{verse}", d["verse_text"])


def plain(text):
    return LINK.sub(r"\1", text)


def alternates(page):
    rows = ['<link rel="alternate" hreflang="%s" href="%s">' % (l, page_url(l, page)) for l in LANGS]
    rows.append('<link rel="alternate" hreflang="x-default" href="%s">' % page_url("en", page))
    return "\n".join(rows) + "\n"


def breadcrumb(lang, name, url):
    items = [("still()", lang_url(lang)), (name, url)]
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}


def render(bj, lang, page, T, home, has_posts):
    """one page. bj = the build_journal module (head/header/footer/ld/inline), already loaded with the data files."""
    h = dict(home["en"], **home[lang])
    url = page_url(lang, page)
    targets = {l: "/%s/%s/" % (l, page) for l in LANGS}
    other = "about" if page == "faq" else "faq"
    if page == "faq":
        title, meta, lede = T["faq_title"], T["faq_meta"], T["faq_lede"]
        qa = [(fill(q, lang, home), fill(a, lang, home)) for q, a in T["faq"]]
        body = "\n".join('    <h2>%s</h2>\n    <p>%s</p>' % (esc(q), bj.inline(a)) for q, a in qa)
        data = {"@context": "https://schema.org", "@type": "FAQPage", "name": title, "url": url, "inLanguage": lang,
                "isPartOf": {"@type": "WebSite", "name": "still()", "url": lang_url(lang)}, "publisher": dict(ORG),
                "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in qa]}
    else:
        title, meta, lede = T["about_title"], T["about_meta"], None
        paras = [fill(p, lang, home) for p in T["about"]]
        body = "\n".join("    <p>%s</p>" % bj.inline(p) for p in paras)
        data = {"@context": "https://schema.org", "@type": "AboutPage", "name": title, "url": url, "inLanguage": lang,
                "description": meta, "isPartOf": {"@type": "WebSite", "name": "still()", "url": lang_url(lang)},
                "mainEntity": {"@type": "MobileApplication", "name": "still()", "url": lang_url(lang), "operatingSystem": "iOS",
                               "applicationCategory": "LifestyleApplication", "publisher": dict(ORG)}}
    lede_html = '\n    <p class="lede">%s</p>' % esc(lede) if lede else ""
    extra = '<meta property="og:type" content="website">\n' + bj.ld(data) + bj.ld(breadcrumb(lang, title, url))
    nav = "link" if has_posts else "none"
    # "<title> — still()" repeats the site name when the page title already names it ("... about still()"): then the title stands alone
    return (bj.head(title if "still()" in title else "%s — still()" % title, meta, url, lang, False, extra, hint="edit content/info/pages.json and rebuild",
                    alternates=alternates(page), locales=list(LANGS))
            + bj.header(lang, targets, None, nav) + f"""<main id="main" class="wrap">
  <div class="page-head">
    <p class="eyebrow">still()</p>
    <h1>{esc(title)}</h1>{lede_html}
  </div>
  <div class="prose info">
{body}
  </div>
  <nav class="article-foot" aria-label="{esc(h['foot_' + other])}">
    <a class="more-link" href="/{lang}/"><span aria-hidden="true">←</span> still()</a>
    <a class="more-link" href="/{lang}/{other}/"><span>{esc(h['foot_' + other])}</span> <span aria-hidden="true">→</span></a>
  </nav>
</main>
""" + bj.footer(lang, targets, lang, journal=has_posts))


def sitemap_block(date):
    rows = []
    for page in PAGES:
        links = "".join('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>\n' % (l, page_url(l, page)) for l in LANGS)
        links += '    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>\n' % page_url("en", page)
        for l in LANGS:
            rows.append("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.7</priority>\n%s  </url>"
                        % (page_url(l, page), date, links))
    return "\n".join(rows) + "\n"


def llms_block(pages):
    lines = ["## Questions and answers about still() (FAQ) and how it differs from other apps called Still — 11 languages"]
    for page, key in (("faq", "faq_title"), ("about", "about_title")):
        lines += ["- [%s](%s) — %s" % (pages[l][key], page_url(l, page), LANGS[l]["name"]) for l in LANGS]
    return "\n".join(lines) + "\n"


def build(root, bj, has_posts=False):
    """write the 22 pages + the sitemap/llms blocks. bj = the RUNNING build_journal module (not a fresh import: its data files are
    loaded and its journal-list state decides where the footer's Journal link goes — build_journal.py usually runs as __main__)."""
    root = Path(root)
    pages = load(root)
    home = json.loads((root / "content" / "home" / "i18n.json").read_text(encoding="utf-8"))
    written = []
    for page in PAGES:
        for lang in LANGS:
            path = root / lang / page / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(bj, lang, page, pages[lang], home, has_posts), encoding="utf-8")
            written.append(path)
    sm = root / "sitemap.xml"
    sm.write_text(replace_between(sm.read_text(encoding="utf-8"), r"<!-- info:start[^>]*-->", "  <!-- info:end -->",
                                  sitemap_block(stamped_date(root, (SOURCE,), STAMP)), "sitemap.xml"), encoding="utf-8")
    llms = root / "llms.txt"
    llms.write_text(replace_between(llms.read_text(encoding="utf-8"), r"<!-- info:llms:start[^>]*-->", "<!-- info:llms:end -->",
                                    llms_block(pages), "llms.txt"), encoding="utf-8")
    return written
