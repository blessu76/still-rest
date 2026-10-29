#!/usr/bin/env python3
"""Build the still.ipe.rest Journal — no dependencies (Python 3.8+ stdlib only).

Reads   content/journal/<lang>/<slug>.md   (front matter + Markdown; one folder per language, ko and en included)
        content/journal/safety.json        the fixed safety block of every article (disclaimer, crisis lines, ...) — 11 languages
        content/journal/ui.json            list/hub/UI strings — 11 languages
Writes  journal/index.html                 x-default hub (language links + the originals)
        journal/<lang>/index.html          one list page per language that has posts
        journal/page/<n>/index.html        page 2, 3, ... of the hub and of every language list (journal/<lang>/page/<n>/): 10 posts a page,
                                           newest first; page 1 keeps the plain address (there is no .../page/1/)
        journal/<lang>/<slug>/index.html   one page per post and language  (11 languages: en ko ja zh es pt id ru vi fr de)
        <old alias path>/index.html        static redirect stubs (front matter `aliases`) — not in the sitemap
        journal/feed.xml                   RSS 2.0 (originals = posts without translation_of)
        sitemap.xml                        between <!-- journal:start --> / <!-- journal:end -->
        llms.txt                           "Journal" section between <!-- journal:llms:start --> / <!-- journal:llms:end -->
        index.html + <lang>/index.html     home page, 11 static language pages (scripts/build_home.py)

All language versions of a post share ONE slug (that is what groups them for hreflang / translationOfWork).

Numbers: every post has a number "No. N" = its place in publication order (oldest = No. 1; order = date, then time of day, then slug), counted
per slug (translation group), so the same article has the same number in every language. Only published posts are counted (no drafts, no
scheduled post before it is due), so a post that goes live later (always newer) never changes an existing number. Shown on the list cards,
the article head and the home cards. Do not give an already public post an older `date` than the posts that follow it — that would renumber them.

Front matter (between two `---` lines):
    title:       required
    date:        required, YYYY-MM-DD (publication date, KST)
    slug:        required, [a-z0-9-]+ (= file name), same in every language; not a language code, not "feed"
    lang:        required, one of en ko ja zh es pt id ru vi fr de (= folder name)
    description: required, one sentence (meta description, cards, RSS)
    category:    required, free text in the post's language (e.g. 우울 · panic · work)
    verse:       optional, `책 장:절` as written in the post's language (e.g. `시편 121:2`) — the verse chip on the home card. Without it the chip is read
                 from the article's single quotation block (`> 구절` / `>` / `> 시편 121:2 (개역한글)`); if that is not unambiguous, no chip.
    draft:       optional, true → skipped everywhere (output, list, home, sitemap, feed)
    publish_at:  optional, `YYYY-MM-DD HH:MM` (KST; an offset like +09:00 is also accepted) → scheduled: the post is published only by a
                 build whose clock (`--now`) is at or after this time. Its date must be the same day as `date`. A build without
                 `--now` (the committed output) treats every scheduled post as not yet published — see "Scheduled posts" below.
    published_at: optional, `YYYY-MM-DD HH:MM` (KST) — the time an ALREADY PUBLIC post went live (no `publish_at`; same day as `date`). Together
                 with `publish_at` it is the post's time of day: shown as HH:MM next to the date (24 h, KST, no seconds, every language),
                 and written as +09:00 ISO in <time datetime>, JSON-LD datePublished/dateModified, article:published_time and the RSS
                 pubDate. A post with neither shows the date only — never invent a time. When you delete `publish_at` to commit a
                 scheduled post, write its time here instead. Giving both is an error.
    translation_of: ko | en — the original language this version was translated from. Required for every language except
                    ko and en; optional on those two (en: `translation_of: ko`). A post with it shows the "AI translation" notice.
    bible_version:  name of the Bible translation quoted in the post (e.g. "WEB", "개역한글(1961)"). Shown under the text.
                    REQUIRED when the body has a quotation block (`> ...`); write `bible_version: none` when the quote is not Scripture.
    aliases:     optional, comma separated old site paths (/journal/old-slug/) → static redirect stubs to this page
  Optional GEO fields (omitted → simply not emitted):
    updated:        YYYY-MM-DD, dateModified / sitemap lastmod
    image:          hero image, /assets/journal/<slug>/x.jpg (or https URL); default = first body image, else og-image
    image_alt:      alt text of the hero image (ImageObject.caption)
    keywords:       comma separated
    citations:      "Title @ url | Title @ url"  → citation (external links in the body are added automatically)

Every article page carries the same fixed safety block in its own language, taken from content/journal/safety.json
(never from the post): ① "not medical advice" disclaimer ② crisis-line box ③ "woven from many people's experiences"
notice ④ Bible translation name (bible_version).

Scheduled posts (publish_at): the committed output (plain build / --check) never contains a scheduled post, so it does not go stale
as the clock moves. The deploy workflow builds again with `--now now` (the real clock) in the runner before uploading to Pages — on every
push and on a cron schedule — and never commits that build. Replace `publish_at` with `published_at` (same value, keep `date`) to make a post part of the committed output.

Usage:
    python3 scripts/build_journal.py            # build into this repo (scheduled posts held back)
    python3 scripts/build_journal.py --now now  # ...publishing scheduled posts that are due (what the deploy runner does; do not commit)
    python3 scripts/build_journal.py --now "2026-10-24 11:00"   # same, as of a given KST time
    python3 scripts/build_journal.py --check    # validate posts + safety data and fail if the committed output is stale
    python3 scripts/build_journal.py --check --strict-safety
        # also fail while any language that has a published post still has unreviewed (draft) crisis-line data
    python3 scripts/build_journal.py --root /tmp/preview --drafts
        # preview: include drafts (marked DRAFT + noindex). Use only on a COPY of the site.
"""
import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import GEN_MARK, KST, LANGS, ORG, SITE, check_fresh, esc, font_links, lang_url, meta_desc, parse_when, replace_between, with_localtime  # noqa: E402

ASSET_V = "20261027c"  # ?v= of assets/journal.css — bump when the file changes
CF_TOKEN = "eab6249a56894cb084b7bcc8f1a860a6"  # Cloudflare Web Analytics (cookieless), same as the home page
REQUIRED = ("title", "date", "slug", "lang", "description", "category")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ROOT = Path(__file__).resolve().parent.parent  # overwritten in main() from --root (image sizes are read from here)
IMG_NS = "http://www.google.com/schemas/sitemap-image/1.1"
SOCIAL_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "x.com", "twitter.com", "facebook.com", "ipe.rest")  # never auto-cited
ORIGINAL_LANGS = ("ko", "en")  # may be an original without translation_of; every other language is a translation
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' "
           "fill='%230F1218'/%3E%3Ctext x='16' y='22' font-family='Georgia,serif' font-size='18' fill='%23C9A84C' text-anchor='middle'"
           "%3E()%3C/text%3E%3Ccircle cx='16' cy='15.5' r='1.6' fill='%23F5F0E8'/%3E%3C/svg%3E")
UI_KEYS = ("journal", "sub", "empty", "back", "read_more", "view_all", "skip", "rss", "ai_note", "ai_orig", "other_langs", "aria_home", "aria_primary",
           "page", "prev_page", "next_page", "page_word")  # page = title/crumb template with {n}; page_word = the same word alone (pager nav label)
PER_PAGE = 10  # posts on one list page (hub and every language list)
RESERVED_SLUGS = ("feed", "page")  # "page" = the URL segment of list pages 2+ (/journal/<lang>/page/<n>/), so no post may use it as its slug
SAFETY_KEYS = ("fiction", "disclaimer", "jump", "help_title", "help_intro", "fallback", "bible_label")
FALLBACK_HELPLINE = "https://findahelpline.com"  # decision D2 (CRISIS_PROTOCOL): the worldwide directory for places without a listed line

UI = {}      # {lang: {...}}  loaded from content/journal/ui.json
HOME = {}    # {lang: {...}}  content/home/i18n.json (footer wording is shared with the home page)
SAFETY = {}  # content/journal/safety.json
HELD = {}    # content/journal/hold.json  {lang: reason} — languages whose journal is on hold: a post there may only be `draft: true`
             # (the build fails otherwise), so the language gets no list page and no sitemap/hreflang/feed entry. Delete the entry to lift.
SCRIPTURE = None  # content/journal/scripture.json (scripts/fetch_scripture.py): verse text of each language, copied from its public-domain
                  # source. None = the file is absent (test copies of the site) -> translated quotes are not checked against it.
LIST_LANGS = None  # set by main(): languages that have a list page; None = assume all (other scripts importing this module)
NUMBERS = {}  # set by build(): {slug: N} publication-order number of every published post (see assign_numbers); {} = no numbers shown


def load_data(root):
    """read the three data files into the module globals; returns a list of problems (empty = fine)."""
    global UI, HOME, SAFETY, HELD, SCRIPTURE
    errs = []
    try:
        SCRIPTURE = json.loads((root / "content" / "journal" / "scripture.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        SCRIPTURE = None
    except (OSError, ValueError) as ex:
        return ["content/journal/scripture.json: %s" % ex]
    try:
        HELD = {k: v for k, v in json.loads((root / "content" / "journal" / "hold.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
    except FileNotFoundError:
        HELD = {}
    except (OSError, ValueError) as ex:
        return ["content/journal/hold.json: %s" % ex]
    bad = [l for l in HELD if l not in LANGS]
    if bad:
        errs.append("hold.json: unknown language %s" % ", ".join(bad))
    try:
        UI = json.loads((root / "content" / "journal" / "ui.json").read_text(encoding="utf-8"))
        SAFETY = json.loads((root / "content" / "journal" / "safety.json").read_text(encoding="utf-8"))
        HOME = json.loads((root / "content" / "home" / "i18n.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return ["data files: %s" % ex]
    for l in LANGS:
        for k in UI_KEYS:
            if not UI.get(l, {}).get(k):
                errs.append("ui.json: %s lacks %r" % (l, k))
        for k in SAFETY_KEYS:
            if not SAFETY.get("text", {}).get(l, {}).get(k):
                errs.append("safety.json: text.%s lacks %r (every article needs the full safety block in every language)" % (l, k))
        ent = SAFETY.get("lines", {}).get(l)
        if ent is None or ent.get("status") not in ("draft", "verified") or not isinstance(ent.get("regions"), list):
            errs.append("safety.json: lines.%s needs status draft|verified and a regions list (may be empty)" % l)
            continue
        for r in ent["regions"]:
            for it in r.get("items", []):
                if not it.get("name") or not it.get("number"):
                    errs.append("safety.json: lines.%s has an entry without name/number" % l)
                elif it.get("status") not in ("draft", "verified"):
                    errs.append("safety.json: lines.%s %r needs status draft|verified (only verified numbers are shown)" % (l, it["number"]))
                elif it["status"] == "verified" and not it.get("checked_on"):
                    errs.append("safety.json: lines.%s %r is verified but has no checked_on date" % (l, it["number"]))
    return errs


def strict_safety_errors(langs):
    """crisis-line data that is still a draft for languages that have published posts (deploy gate)."""
    return ["safety.json: crisis lines for %s are still `draft` (not verified by a native reviewer) but %s has published posts"
            % (l, l) for l in LANGS if l in langs and SAFETY["lines"][l]["status"] != "verified"]


def ui(lang):
    return UI.get(lang) or UI["en"]


# ---------------------------------------------------------------- front matter
def parse_post(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("missing front matter (file must start with ---)")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("front matter is not closed with ---")
    meta = {}
    for line in text[4:end].split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("bad front matter line: %r" % line)
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        meta[k.strip().lower()] = v
    body = text[end + 4:].lstrip("\n")
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ValueError("missing front matter: " + ", ".join(missing))
    if not SLUG_RE.match(meta["slug"]):
        raise ValueError("slug must match [a-z0-9-]+: %r" % meta["slug"])
    if meta["slug"] in LANGS or meta["slug"] in RESERVED_SLUGS:
        raise ValueError("slug %r is reserved (language codes, 'feed' and 'page' are URL segments)" % meta["slug"])
    if meta["lang"] not in LANGS:
        raise ValueError("lang must be one of %s: %r" % (" ".join(LANGS), meta["lang"]))
    of = meta.get("translation_of")
    if meta["lang"] not in ORIGINAL_LANGS and not of:
        raise ValueError("lang %s is a translation: `translation_of: ko` (or en) is required" % meta["lang"])
    if of and (of not in ORIGINAL_LANGS or of == meta["lang"]):
        raise ValueError("translation_of must be the language code of the ko/en original (ko or en, not this post's own language): %r" % of)
    try:
        meta["_date"] = dt.date.fromisoformat(meta["date"])
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD: %r" % meta["date"])
    meta["draft"] = str(meta.get("draft", "false")).lower() in ("true", "yes", "1")
    meta["_publish_at"] = None
    if meta.get("publish_at"):
        try:
            meta["_publish_at"] = parse_when(meta["publish_at"])
        except ValueError:
            raise ValueError("publish_at must be `YYYY-MM-DD HH:MM` (KST): %r" % meta["publish_at"])
        if meta["_publish_at"].astimezone(KST).date() != meta["_date"]:
            raise ValueError("publish_at %s (KST) is not on the post's date %s" % (meta["publish_at"], meta["date"]))
    meta["_published_at"] = None
    if meta.get("published_at"):
        if meta["_publish_at"]:
            raise ValueError("`publish_at` and `published_at` are both set — keep only one (publish_at while it is scheduled, published_at once it is public)")
        try:
            meta["_published_at"] = parse_when(meta["published_at"])
        except ValueError:
            raise ValueError("published_at must be `YYYY-MM-DD HH:MM` (KST): %r" % meta["published_at"])
        if meta["_published_at"].astimezone(KST).date() != meta["_date"]:
            raise ValueError("published_at %s (KST) is not on the post's date %s" % (meta["published_at"], meta["date"]))
    if meta.get("updated"):
        try:
            dt.date.fromisoformat(meta["updated"])
        except ValueError:
            raise ValueError("updated must be YYYY-MM-DD: %r" % meta["updated"])
    meta["_aliases"] = []
    for a in [x.strip() for x in meta.get("aliases", "").split(",") if x.strip()]:
        if not re.match(r"^/journal/[a-z0-9/-]*$", a):
            raise ValueError("alias must be a site path like /journal/old-slug/ : %r" % a)
        meta["_aliases"].append(a if a.endswith("/") else a + "/")
    meta["_keywords"] = [x.strip() for x in meta.get("keywords", "").split(",") if x.strip()]
    meta["_citations"] = parse_entries(meta.get("citations", ""))
    bv = meta.get("bible_version", "").strip()
    meta["_bible"] = None if bv.lower() == "none" else (bv or None)
    if meta["_bible"] is None and bv.lower() != "none" and re.search(r"(?m)^\s*>", body):
        raise ValueError("the text has a quotation block (`> ...`) but no `bible_version:` — name the Bible translation "
                         "(e.g. bible_version: WEB), or write `bible_version: none` if the quote is not Scripture")
    meta["_body"] = body
    meta["_src"] = path.name
    return meta


def parse_entries(v):
    """'Title @ url | Title @ url' -> [(title, url|None)]. url must be http(s) or site-relative."""
    out = []
    for part in v.split("|"):
        part = part.strip()
        if not part:
            continue
        title, _, url = part.rpartition(" @ ") if " @ " in part else (part, "", "")
        title, url = title.strip(), url.strip()
        if url and not re.match(r"^(https?://|/)", url):
            raise ValueError("bad url in %r (need http(s):// or /path)" % part)
        out.append((title, abs_url(url) if url else None))
    return out


def abs_url(u):
    return SITE + u if u.startswith("/") else u


def image_size(rel):
    """(w, h) of a site image (png/jpeg/gif/webp) read from its header, or None. stdlib only."""
    if not rel.startswith("/"):
        return None
    f = ROOT / rel.lstrip("/")
    try:
        b = f.read_bytes()[:262144]
    except OSError:
        return None
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
        if b[:6] in (b"GIF87a", b"GIF89a"):
            return int.from_bytes(b[6:8], "little"), int.from_bytes(b[8:10], "little")
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            k = b[12:16]
            if k == b"VP8X":
                return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
            if k == b"VP8 ":
                return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
            if k == b"VP8L":
                v = int.from_bytes(b[21:25], "little")
                return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
        if b[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(b):
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                n = int.from_bytes(b[i + 2:i + 4], "big")
                if m in range(0xC0, 0xCF) and m not in (0xC4, 0xC8, 0xCC):
                    return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
                i += 2 + n
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- markdown (small, safe subset)
def safe_url(u):
    u = u.strip()
    if re.match(r"^(https?://|/|#|mailto:)", u):
        return u
    if re.match(r"^[\w./-]+$", u) and ":" not in u:  # relative path
        return u
    return "#"


def img_tag(src, alt):
    wh = image_size(src)
    dims = ' width="%d" height="%d"' % wh if wh else ""
    return '<img src="%s" alt="%s"%s loading="lazy" decoding="async">' % (esc(src), esc(alt), dims)


FIG_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')


def inline(text):
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append("<code>%s</code>" % esc(p[1:-1]))
            continue
        s = esc(p)
        s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                   lambda m: img_tag(safe_url(html.unescape(m.group(2))), html.unescape(m.group(1))), s)

        def link(m):
            url = safe_url(html.unescape(m.group(2)))
            ext = url.startswith("http") and not url.startswith(SITE)
            return '<a href="%s"%s>%s</a>' % (esc(url), ' rel="noopener"' if ext else "", m.group(1))
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", s)
        out.append(s)
    return "".join(out)


def markdown(src):
    lines = src.split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(x.strip() for x in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if st.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % esc("\n".join(code)))
            i += 1
            continue
        if not st:
            flush()
            i += 1
            continue
        fm = FIG_RE.match(st)
        if fm:  # a line that is only an image -> <figure>; optional "caption" after the url
            flush()
            cap = "<figcaption>%s</figcaption>" % inline(fm.group(3)) if fm.group(3) else ""
            out.append("<figure>%s%s</figure>" % (img_tag(safe_url(fm.group(2)), fm.group(1)), cap))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", st)
        if m:
            flush()
            level = {1: 2, 2: 2, 3: 3, 4: 4}[len(m.group(1))]
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", st):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if st.startswith(">"):
            flush()
            paras, cur = [], []
            while i < len(lines) and lines[i].strip().startswith(">"):
                t = lines[i].strip()[1:].strip()
                if t:
                    cur.append(t)
                elif cur:  # an empty `>` line splits the quote into paragraphs (verse text, then the reference)
                    paras.append(cur)
                    cur = []
                i += 1
            if cur:
                paras.append(cur)
            out.append("<blockquote>%s</blockquote>" % "".join("<p>%s</p>" % inline(" ".join(x)) for x in paras))
            continue
        if re.match(r"^[-*+]\s+", st) or re.match(r"^\d+[.)]\s+", st):
            flush()
            ordered = bool(re.match(r"^\d", st))
            pat = r"^\d+[.)]\s+" if ordered else r"^[-*+]\s+"
            items = []
            while i < len(lines) and re.match(pat, lines[i].strip()):
                items.append(re.sub(pat, "", lines[i].strip()))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue
        para.append(line)
        i += 1
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- page chrome
# visible date, written the way the page's language writes it (the <time datetime> next to it stays ISO)
MONTHS = {
    "en": "January February March April May June July August September October November December",
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre",
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro",
    "id": "Januari Februari Maret April Mei Juni Juli Agustus September Oktober November Desember",
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря",  # genitive, as after a day number
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
}
DATE_FORMATS = {
    "en": "{month} {d}, {y}", "ko": "{y}년 {m}월 {d}일", "ja": "{y}年{m}月{d}日", "zh": "{y}年{m}月{d}日",
    "es": "{d} de {month} de {y}", "pt": "{d} de {month} de {y}", "id": "{d} {month} {y}", "ru": "{d} {month} {y} г.",
    "vi": "{d} tháng {m}, {y}", "fr": "{d} {month} {y}", "de": "{d}. {month} {y}",
}


def fmt_date(d, lang="en"):
    months = MONTHS.get(lang, "").split()
    day = "1er" if lang == "fr" and d.day == 1 else d.day
    return DATE_FORMATS.get(lang, DATE_FORMATS["en"]).format(
        y=d.year, m=d.month, d=day, month=months[d.month - 1] if months else "")


def post_when(p):
    """the post's time of day: `publish_at` (scheduled) or `published_at` (already public), as an aware KST datetime cut to the minute; None = unknown."""
    w = p.get("_publish_at") or p.get("_published_at")
    return w.astimezone(KST).replace(second=0, microsecond=0) if w else None


def fmt_when(p):
    """visible date + ` HH:MM` (24 h, KST, no seconds, same in every language); the date alone when the time is unknown.
    The no-break space keeps the time on the date's line when the eyebrow wraps."""
    w = post_when(p)
    return fmt_date(p["_date"], p["lang"]) + ("&nbsp;" + w.strftime("%H:%M") if w else "")


def iso_when(p):
    """machine form: `2026-10-24T11:00:00+09:00`, or `2026-10-24` when the time is unknown."""
    w = post_when(p)
    return w.isoformat() if w else p["_date"].isoformat()


def time_tag(p):
    """<time> of a post. With a known time of day it is marked data-ipe-time and reads `<date>&nbsp;HH:MM KST`: scripts/ipe-localtime.js
    (inlined by site_common.with_localtime) then shows it in the reader's own time zone; without JS the static KST text stays.
    Date only (time unknown) -> plain <time>, nothing to convert."""
    if not post_when(p):
        return '<time datetime="%s">%s</time>' % (iso_when(p), fmt_when(p))
    return '<time datetime="%s" data-ipe-time>%s KST</time>' % (iso_when(p), fmt_when(p))


def lang_path(lang):
    """site path of a language's journal list: /journal/<lang>/ (all 11 languages; /journal/ itself is the x-default hub)."""
    return "/journal/%s/" % lang


def jhome(lang):
    """where a page in `lang` sends its 'Journal' link: that language's list if it exists, else the x-default hub."""
    return lang_path(lang) if LIST_LANGS is None or lang in LIST_LANGS else "/journal/"


def post_path(p):
    return "%s%s/" % (lang_path(p["lang"]), p["slug"])


def post_url(p):
    return SITE + post_path(p)


def order_key(p):
    """publication order of one post: date, time of day (unknown time sorts first within its day), slug."""
    return (p["_date"], post_when(p).strftime("%H:%M") if post_when(p) else "", p["slug"])


def assign_numbers(posts):
    """{slug: N} — the publication-order number, oldest published article = 1. One number per slug (= per translation group, so every
    language of an article carries the same number), taken from the group's original (else from its earliest member). `posts` = the
    published posts only: a draft or a not-yet-due scheduled post takes no number, so when it goes live (it is newer) nothing before it moves."""
    by = {}
    for p in posts:
        by.setdefault(p["slug"], []).append(p)
    key = lambda g: min(order_key(m) for m in ([m for m in g if not m.get("translation_of")] or g))
    return {g[0]["slug"]: i + 1 for i, g in enumerate(sorted(by.values(), key=key))}


def no_tag(p):
    """`<span class="j-no">No. 7</span>` — the post's number, or "" when numbers are not computed (a module used on its own)."""
    n = NUMBERS.get(p["slug"])
    return '<span class="j-no">No.&nbsp;%d</span>' % n if n else ""


def with_no(p, rest):
    """number + ` · ` + the rest of an eyebrow line (just the rest when the post has no number)."""
    n = no_tag(p)
    return "%s · %s" % (n, rest) if n else rest


def paginate(items):
    """items (newest first) -> pages of PER_PAGE; an empty list is still one (empty) page."""
    return [items[i:i + PER_PAGE] for i in range(0, len(items), PER_PAGE)] or [[]]


def list_path(lang, n=1):
    """site path of page n of a list: lang=None -> the hub /journal/, else /journal/<lang>/. Page 1 is the plain address, page n>=2 is <list>page/<n>/."""
    base = lang_path(lang) if lang else "/journal/"
    return base if n == 1 else "%spage/%d/" % (base, n)


def list_scopes(posts, list_langs):
    """{None: the originals (hub), lang: that language's posts} — each in the order given (newest first for the real pages)."""
    scopes = {None: [p for p in posts if not p.get("translation_of")]}
    for l in list_langs:
        scopes[l] = [p for p in posts if p["lang"] == l]
    return scopes


def page_counts(scopes):
    return {k: len(paginate(v)) for k, v in scopes.items()}


def page_label(lang, n):
    return ui(lang)["page"].replace("{n}", str(n))


def og_image_alt(lang):
    return (HOME.get(lang) or {}).get("og_image_alt") or HOME["en"]["og_image_alt"]


def head(title, desc, canonical, lang, noindex, extra="", hint="edit content/journal/*.md and rebuild", image=None, alternates="", locales=(), image_alt=None):
    image_alt = image_alt if image else og_image_alt(lang)  # the default card has a description in the page's language
    image = image or SITE + "/og-image.png"
    desc = meta_desc(desc)  # meta / og / twitter descriptions stay within 160 characters (the visible text, JSON-LD and RSS keep the full text)
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
    alts = "".join('<meta property="og:locale:alternate" content="%s">\n' % LANGS[l]["og"] for l in locales if l != lang)
    return f"""<!DOCTYPE html>
<html lang="{esc(lang)}" dir="{LANGS[lang]["dir"]}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- {GEN_MARK} — do not hand-edit; {hint} -->
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="author" content="ipe Studio">
<meta name="robots" content="{robots}">
<meta name="theme-color" content="#F7F2E9">
<link rel="icon" href="{FAVICON}">
<link rel="canonical" href="{esc(canonical)}">
{alternates}<link rel="alternate" type="application/rss+xml" title="still() Journal" href="{SITE}/journal/feed.xml">
<meta property="og:site_name" content="still()">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="{LANGS[lang]["og"]}">
{alts}<meta property="og:image" content="{esc(image)}">
{'<meta property="og:image:alt" content="%s">' % esc(image_alt) + chr(10) if image_alt else ''}<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(image)}">
{extra}{font_links()}
<link rel="stylesheet" href="/assets/journal.css?v={ASSET_V}">
<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{{"token": "{CF_TOKEN}"}}'></script>
</head>
<body>
"""


def lang_select(lang, targets, neutral=None):
    """the home page's language <select> (same look), option value = site path of the same page in that language.
    targets = {lang: path}; only languages that really have this page. neutral = (label, path): a first, selected
    option for pages that belong to no single language (the x-default hub). No targets -> no select at all."""
    if not targets:
        return ""
    opts = ('      <option value="%s" selected>%s</option>\n' % (esc(neutral[1]), esc(neutral[0])) if neutral else "") + "\n".join('      <option value="%s"%s>%s</option>' % (esc(targets[l]), " selected" if l == lang and not neutral else "", esc(LANGS[l]["name"]))
                     for l in LANGS if l in targets)
    return f"""<label class="langsel">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.8 5.8 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.8-3.8-9S9.5 5.5 12 3z"/></svg>
    <select id="lang" aria-label="{esc(ui(lang)['other_langs'])}">
{opts}
    </select>
  </label>"""


def header(lang, targets, neutral=None, nav="current"):
    """nav: "current" = the Journal link marked as the current page (journal pages) · "link" = a plain Journal link · "none" = no nav."""
    t = ui(lang)
    bar = "" if nav == "none" else '<nav class="bar-nav" aria-label="%s"><a href="%s"%s>%s</a></nav>' % (
        esc(t['aria_primary']), jhome(lang), ' aria-current="page"' if nav == "current" else "", esc(t['journal']))
    return f"""<a class="skip-link" href="#main">{esc(t['skip'])}</a>
<header class="topbar">
  <div class="wrap-wide bar">
    <a class="brand" href="/{lang}/" aria-label="{esc(t['aria_home'])}">still<span class="paren">(</span><span class="paren">)</span></a>
    {bar}
    {lang_select(lang, targets, neutral)}
  </div>
</header>
"""


def lang_links(lang, targets, label):
    """the language switch as plain links (the <select> needs JS): one <a href> per language this page exists in."""
    if not targets:
        return ""
    links = "\n".join('      <a href="%s" hreflang="%s" lang="%s"%s>%s</a>' % (esc(targets[l]), l, l, ' aria-current="true"' if l == lang else "", esc(LANGS[l]["name"]))
                      for l in LANGS if l in targets)
    return '    <nav class="foot-langs" aria-label="%s">\n%s\n    </nav>\n' % (esc(label), links)


def footer(lang, targets=None, current=None, journal=True):
    """journal=False: no Journal/RSS links (info pages while there is no post — like the home page)."""
    t, h = ui(lang), HOME.get(lang) or HOME["en"]
    g = lambda k: h.get(k) or HOME["en"][k]
    journal_links = ('      <a href="%s">%s</a>\n      <a href="/journal/feed.xml">%s</a>\n' % (jhome(lang), esc(t['journal']), esc(t['rss']))) if journal else ""
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="foot-mark">still<span class="paren">(</span><span class="paren">)</span></div>
    <div class="foot-verse">{esc(g('hero_tag'))}</div>
    <nav class="foot-links" aria-label="{esc(g('aria_footer'))}">
      <a href="/{lang}/">still()</a>
{journal_links}      <a href="/{lang}/faq/">{esc(g('foot_faq'))}</a>
      <a href="/{lang}/about/">{esc(g('foot_about'))}</a>
      <a href="/privacy/">{esc(g('foot_privacy'))}</a>
      <a href="/terms/">{esc(g('foot_terms'))}</a>
      <a href="mailto:ipe.haven@gmail.com">{esc(g('foot_support'))}</a>
    </nav>
{lang_links(lang if current is None else current, targets, g('aria_lang'))}    <div class="foot-studio">{esc(g('foot_studio'))}</div>
  </div>
</footer>
<script>
(function () {{
  var sel = document.getElementById('lang');
  if (sel) sel.addEventListener('change', function () {{
    var m = String(this.value).match(/^\\/journal\\/([a-z]{{2}})\\//);
    try {{ if (m) localStorage.setItem('still_lang', m[1]); }} catch (e) {{}}
    location.href = this.value;
  }});
}})();
</script>
</body>
</html>
"""


def ld(obj):
    return '<script type="application/ld+json">\n%s\n</script>\n' % json.dumps(obj, ensure_ascii=False, indent=2).replace("</", "<\\/")


# ---------------------------------------------------------------- safety block (fixed on every article, every language)
def render_help(lang):
    """the crisis-line box. Wording + numbers come only from content/journal/safety.json."""
    txt, ent = SAFETY["text"][lang], SAFETY["lines"][lang]
    regions = []
    for r in ent["regions"]:
        rows = []
        for it in r.get("items", []):
            if it.get("status") != "verified":  # a number nobody has confirmed is never shown to a person in crisis
                continue
            num = esc(it["number"])
            num = '<a class="help-num" href="tel:%s">%s</a>' % (esc(it["tel"]), num) if it.get("tel") else '<span class="help-num">%s</span>' % num
            hours = ' <span class="help-hours">%s</span>' % esc(it["hours"]) if it.get("hours") else ""
            rows.append('        <li><span class="help-name">%s</span> %s%s</li>' % (esc(it["name"]), num, hours))
        if rows:
            regions.append('      <div class="help-region">\n        <h3>%s</h3>\n        <ul>\n%s\n        </ul>\n      </div>' % (esc(r["country"]), "\n".join(rows)))
    more = txt["fallback"]
    return f"""    <div class="help" id="help" data-crisis-lines="{esc(ent['status'])}">
      <h2>{esc(txt['help_title'])}</h2>
      <p>{esc(txt['help_intro'])}</p>
{chr(10).join(regions)}
      <p class="help-more">{esc(more)} <a href="{FALLBACK_HELPLINE}" rel="noopener">findahelpline.com</a></p>
    </div>
"""


def render_notice(lang):
    """short strip under the title: creative-work notice + disclaimer + jump link to the crisis box."""
    txt = SAFETY["text"][lang]
    return f"""    <aside class="notice" data-safety="notice">
      <p>{esc(txt['fiction'])}</p>
      <p>{esc(txt['disclaimer'])} <a href="#help">{esc(txt['jump'])}</a></p>
    </aside>
"""


def render_safety(p):
    """bottom block: Bible translation, crisis lines, disclaimer again. Same for every post; only bible_version is per post."""
    txt = SAFETY["text"][p["lang"]]
    bible = ('    <p class="bible-version" data-safety="bible"><strong>%s</strong> %s</p>\n' % (esc(txt["bible_label"]), esc(p["_bible"]))) if p["_bible"] else ""
    return f"""{bible}  <section class="safety" data-safety="block" aria-label="{esc(txt['help_title'])}">
{render_help(p['lang'])}    <p class="small-print">{esc(txt['fiction'])} {esc(txt['disclaimer'])}</p>
  </section>
"""


# ---------------------------------------------------------------- pages
def hero_image(p):
    """front matter image -> first body asset image -> None (caller falls back to og-image)."""
    if p.get("image"):
        return p["image"]
    m = re.search(r"!\[[^\]]*\]\((/assets/journal/[^)\s]+)", p["_body"])
    return m.group(1) if m else None


def body_images(p):
    seen, out = set(), []
    for u in ([p["image"]] if p.get("image") else []) + re.findall(r"!\[[^\]]*\]\((/assets/[^)\s]+)", p["_body"]):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def check_post_images(p):
    """Errors for local images (front matter `image` + body `![](/assets/...)`) that are not real files."""
    errs = []
    for u in body_images(p):
        if not u.startswith("/"):
            continue  # external URL — not ours to check
        f = (ROOT / urllib.parse.unquote(re.split(r"[?#]", u, 1)[0]).lstrip("/")).resolve()
        if ROOT not in f.parents or not f.is_file():
            errs.append("%s: image file not found: %s" % (p["_src"], u))
    return errs


def groups(posts):
    """{id(post): [published posts with the same slug]} — one post in every language it exists in."""
    by = {}
    for p in posts:
        by.setdefault(p["slug"], []).append(p)
    return {id(p): by[p["slug"]] for p in posts}


def check_translations(posts, all_posts, drafts_ok):
    """Errors for translation groups (= posts sharing a slug): one post per language; `translation_of: <lang>` names a
    ko/en version of the same slug that is published (not missing, not a hidden draft). Alias paths must be unique."""
    errs = []
    for g in {id(g): g for g in groups(posts).values()}.values():
        langs = {}
        for m in g:
            if m["lang"] in langs:
                errs.append("%s and %s are both lang %s of slug %r (one post per language)" % (m["_src"], langs[m["lang"]]["_src"], m["lang"], m["slug"]))
            langs[m["lang"]] = m
    for p in posts:
        of = p.get("translation_of")
        if not of:
            continue
        other = all_posts.get((p["slug"], of))
        if other is None:
            errs.append("%s: translation_of %s but there is no %s post with slug %r (content/journal/%s/%s.md)" % (p["_src"], of, of, p["slug"], of, p["slug"]))
        elif (other["draft"] or other.get("_held")) and not drafts_ok:
            errs.append("%s: translation_of %s refers to a draft or not-yet-published post (%s) — it is not published" % (p["_src"], of, other["_src"]))
    pages = {post_path(p) for p in posts} | {lang_path(l) for l in LANGS} | {"/journal/"}
    seen = {}
    for p in posts:
        for al in p["_aliases"]:
            if al in pages or re.match(r"^/journal/(?:[a-z]{2}/)?page/", al):
                errs.append("%s: alias %s is a real page" % (p["_src"], al))
            elif al in seen:
                errs.append("%s: alias %s already used by %s" % (p["_src"], al, seen[al]))
            seen[al] = p["_src"]
    return errs


def image_obj(rel, caption=None):
    """JSON-LD ImageObject (always an object, never a bare URL string: Google wants width/height/caption where they are known)."""
    o = {"@type": "ImageObject", "url": abs_url(rel)}
    wh = image_size(rel)
    if wh:
        o["width"], o["height"] = wh
    if caption:
        o["caption"] = caption
    return o


def word_count(text, lang):
    """words; ja/zh have no spaces between words -> count characters (excluding whitespace/punctuation) instead."""
    if lang in ("ja", "zh"):
        return len(re.findall(r"\w", text))
    return len(text.split())


def plain_text(html_body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html_body))).strip()


def citations(p):
    out, seen = [], set()
    for t, u in p["_citations"]:
        if u not in seen:
            seen.add(u)
            out.append({"@type": "CreativeWork", "name": t or u, "url": u})
    for m in re.finditer(r'<a href="(https?://[^"]+)" rel="noopener">(.*?)</a>', p["_html"]):
        u = html.unescape(m.group(1))
        host = re.sub(r"^www\.", "", u.split("/")[2].lower())
        if u in seen or any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
            continue
        seen.add(u)
        out.append({"@type": "CreativeWork", "name": plain_text(m.group(2)) or u, "url": u})
    return out


def breadcrumb(lang, name, url, jurl=None):
    t = ui(lang)
    items = [("still()", lang_url(lang)), (t["journal"], jurl or SITE + lang_path(lang))] + ([(name, url)] if name else [])
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}


def pair_urls(p, grp):
    """{hreflang: url} of the whole translation group (published members only) + x-default (en, else the original)."""
    pair = {m["lang"]: post_url(m) for m in grp.get(id(p), [p])}
    pair.setdefault(p["lang"], post_url(p))
    default = pair.get("en") or pair.get("ko") or post_url(p)
    return pair, default


def alternates(p, grp):
    """hreflang <link>s: every language of the group (incl. self) + x-default. Same set on every member -> always mutual."""
    pair, default = pair_urls(p, grp)
    rows = ['<link rel="alternate" hreflang="%s" href="%s">' % (esc(l), esc(u)) for l, u in sorted(pair.items())]
    rows.append('<link rel="alternate" hreflang="x-default" href="%s">' % esc(default))
    return "\n".join(rows) + "\n"


def render_post(p, grp=None):
    grp = grp or {}
    members = grp.get(id(p), [p])
    t = ui(p["lang"])
    url = post_url(p)
    hero = hero_image(p)
    data = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": p["title"], "description": p["description"],
        "datePublished": iso_when(p), "dateModified": p.get("updated") or iso_when(p),
        "inLanguage": p["lang"], "articleSection": p["category"],
        "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url,
        "image": image_obj(hero, p.get("image_alt")) if hero else image_obj("/og-image.png", og_image_alt(p["lang"])),
        "wordCount": word_count(plain_text(p["_html"]), p["lang"]),
        "author": dict(ORG), "publisher": dict(ORG),
        "isPartOf": {"@type": "Blog", "name": "still() Journal", "url": SITE + lang_path(p["lang"])},
    }
    if p["_keywords"]:
        data["keywords"] = ", ".join(p["_keywords"])
    cites = citations(p)
    if cites:
        data["citation"] = cites
    ref = lambda m: {"@type": "BlogPosting", "@id": post_url(m), "url": post_url(m), "headline": m["title"], "inLanguage": m["lang"]}
    source = next((m for m in members if m["lang"] == p.get("translation_of")), None)
    if source:
        data["translationOfWork"] = ref(source)
    derived = [ref(m) for m in members if m is not p and m.get("translation_of") == p["lang"]]
    if derived:
        data["workTranslation"] = derived[0] if len(derived) == 1 else derived
    translated = bool(p.get("translation_of"))
    if translated:
        data["translator"] = dict(ORG, description="AI translation of the original post")
    extra = ('<meta property="og:type" content="article">\n'
             '<meta property="article:published_time" content="%s">\n'
             '<meta property="article:modified_time" content="%s">\n'
             '<meta property="article:section" content="%s">\n' % (iso_when(p), p.get("updated") or iso_when(p), esc(p["category"]))
             + "".join('<meta property="article:tag" content="%s">\n' % esc(k) for k in p["_keywords"])
             ) + ld(data) + ld(breadcrumb(p["lang"], p["title"], url))
    draft = '<span class="draft-flag">DRAFT</span>' if p["draft"] else ""
    ai_note = ""
    if translated:
        ai_note = '    <p class="ai-note"><span class="ai-badge">AI</span> %s%s</p>\n' % (
            esc(t["ai_note"]),
            (' <a href="%s" hreflang="%s" lang="%s">%s</a>' % (esc(post_path(source)), source["lang"], source["lang"], esc(t["ai_orig"] + " (" + LANGS[source["lang"]]["name"] + ")"))) if source else "")
    pair, _ = pair_urls(p, grp)
    targets = {l: urllib.parse.urlsplit(u).path for l, u in pair.items()}
    return with_localtime(head("%s — still() %s" % (p["title"], t["journal"]), p["description"], url, p["lang"], p["draft"], extra,
                 image=abs_url(hero) if hero else None, image_alt=p.get("image_alt"), alternates=alternates(p, grp),
                 locales=[m["lang"] for m in members])
            + header(p["lang"], targets) + f"""<main id="main" class="wrap">
  <article class="article">
    <header class="article-head">
      <p class="eyebrow">{with_no(p, time_tag(p) + " · " + esc(p['category']))}{draft}</p>
      <h1>{esc(p['title'])}</h1>
      <p class="lede">{esc(p['description'])}</p>
    </header>
{render_notice(p['lang'])}{ai_note}    <div class="prose">
{p['_html']}
    </div>
{render_safety(p)}    <nav class="article-foot" aria-label="{esc(t['journal'])}">
      <a class="more-link" href="{jhome(p['lang'])}"><span aria-hidden="true">←</span> {esc(t['back'])}</a>
    </nav>
  </article>
</main>
""" + footer(p["lang"], targets))


def list_pairs(list_langs, n=1, counts=None):
    """{hreflang: url} of the journal list pages that exist: /journal/<lang>/ (page n of it) for every language with a post — and, for
    n >= 2, only for the languages that have that page (counts = {lang: number of pages})."""
    return {l: SITE + list_path(l, n) for l in list_langs if n == 1 or (counts or {}).get(l, 1) >= n}


def render_pager(lang, n, total):
    """ipe-common pager of a list page (markup shared with idle.ipe.rest): prev step · one number per page (the current one a span with
    aria-current=page) · next step. Newest first: page n-1 = newer posts, n+1 = older ones. Page 1 links to the plain list, never /page/1/.
    The nav's aria-label is the language's own page word (ui page_word — the word inside its "· <Page> N" title; the hub uses English). "" when there is one page."""
    if total <= 1:
        return ""
    t = ui(lang)
    rows = []
    if n > 1:
        rows.append('<a class="pg-step" rel="prev" href="%s"><span aria-hidden="true">←</span> %s</a>' % (list_path(lang, n - 1), esc(t["prev_page"])))
    for k in range(1, total + 1):
        rows.append('<span class="pg-num" aria-current="page">%d</span>' % k if k == n else '<a class="pg-num" href="%s">%d</a>' % (list_path(lang, k), k))
    if n < total:
        rows.append('<a class="pg-step" rel="next" href="%s">%s <span aria-hidden="true">→</span></a>' % (list_path(lang, n + 1), esc(t["next_page"])))
    return '  <nav class="pager" aria-label="%s">\n%s\n  </nav>' % (esc(t["page_word"]), "\n".join("    " + r for r in rows))


HUB_TAG = "All languages"  # title tag of the /journal/ hub (English originals; the x-default of the language lists)
HUB_NOTE = "Originals in English, with AI translations."


def hub_desc(sub):
    """description of the hub: the first sentence of the shared summary + a line saying this list holds the originals."""
    m = re.search(r"[.!?。！？](?=\s|$)", sub)
    return (sub[:m.end()] if m else sub) + " " + HUB_NOTE


def render_list(posts, lang=None, list_langs=("en",), page=1, counts=None):
    """lang=None -> /journal/ (x-default hub: language select + the originals). lang=xx -> /journal/xx/ (that language only).
    posts = ALL posts of that list (newest first); page n shows posts[(n-1)*PER_PAGE : n*PER_PAGE]. counts = {lang|None: number of pages}
    of every list (hreflang of page n names only the languages that have page n); default = every list has the pages of its own posts only."""
    loc = lang or "en"
    t = ui(loc)
    chunks = paginate(posts)
    total = len(chunks)
    page = max(1, min(page, total))
    chunk = chunks[page - 1]
    counts = dict(counts or {})
    counts[lang] = total
    pages = list_pairs(list_langs, page, counts)
    url = SITE + list_path(lang, page)
    first_url = SITE + list_path(lang, 1)
    suffix = " · %s" % page_label(loc, page) if page > 1 else ""
    data = {"@context": "https://schema.org", "@type": "Blog", "name": "still() %s" % t["journal"], "url": url,
            "publisher": dict(ORG), "inLanguage": sorted({p["lang"] for p in posts}) if not lang else lang,
            "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": post_url(p),
                          "datePublished": iso_when(p), "inLanguage": p["lang"]} for p in chunk]}
    itemlist = {"@context": "https://schema.org", "@type": "ItemList", "name": "still() %s%s" % (t["journal"], suffix), "url": url,
                "numberOfItems": len(chunk), "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "itemListElement": [{"@type": "ListItem", "position": (page - 1) * PER_PAGE + i + 1, "url": post_url(p), "name": p["title"]}
                                    for i, p in enumerate(chunk)]}
    if posts:
        items = "\n".join(f"""      <li lang="{esc(p['lang'])}">
        <p class="eyebrow">{with_no(p, time_tag(p) + " · " + esc(p['category']) + (' <span class="draft-flag">DRAFT</span>' if p['draft'] else ''))}</p>
        <h2><a href="{post_path(p)}">{esc(p['title'])}</a></h2>
        <p>{esc(p['description'])}</p>
        <a class="more-link" href="{post_path(p)}" aria-label="{esc(ui(p['lang'])['read_more'])}: {esc(p['title'])}"><span>{esc(ui(p['lang'])['read_more'])}</span> <span aria-hidden="true">→</span></a>
      </li>""" for p in chunk)
        body = '    <ol class="j-list">\n%s\n    </ol>' % items + ("\n" + render_pager(lang, page, total) if total > 1 else "")
    else:
        body = f'    <div class="empty-note"><strong>{esc(t["empty"])}</strong></div>'
    alts = "".join('<link rel="alternate" hreflang="%s" href="%s">\n' % (l, u) for l, u in sorted(pages.items()))
    xdef = SITE + list_path(None, page if page <= counts.get(None, 1) else 1)  # x-default = the hub's same page (its first page when it has no such page)
    alts += '<link rel="alternate" hreflang="x-default" href="%s">\n' % xdef
    if page > 1:
        alts += '<link rel="prev" href="%s">\n' % (SITE + list_path(lang, page - 1))
    if page < total:
        alts += '<link rel="next" href="%s">\n' % (SITE + list_path(lang, page + 1))
    # the language switch goes to the same page number when that language has it, else to its first page
    targets = {l: list_path(l, page if counts.get(l, 1) >= page else 1) for l in list_langs} if lang else {l: lang_path(l) for l in list_langs}
    jurl = first_url if page > 1 else (SITE + "/journal/" if not lang else None)
    crumb = breadcrumb(loc, page_label(loc, page), url, first_url) if page > 1 else breadcrumb(loc, None, url, jurl)
    # every list has its own title and description: a language list names its language (several languages share the word "Journal"),
    # the hub (English originals, x-default) says it is the all-languages entry — so no two list pages repeat each other
    scope = LANGS[lang]["name"] if lang else HUB_TAG
    list_desc = t["sub"] if lang else hub_desc(t["sub"])
    if suffix:  # keep the "· Page N" marker inside the 160-character meta limit: shorten the sentence, never the marker (page 2 must differ from page 1)
        list_desc = meta_desc(list_desc, 160 - len(suffix))
    return with_localtime(head("%s — still() · %s%s" % (t["journal"], scope, suffix), list_desc + suffix, url, loc, not posts,
                 '<meta property="og:type" content="website">\n' + ld(data) + ld(itemlist) + ld(crumb), alternates=alts, locales=list(pages))
            + header(loc, targets, None if lang else (t['other_langs'], list_path(None, page))) + f"""<main id="main" class="wrap">
  <div class="page-head">
    <p class="eyebrow">still(){esc(suffix)}</p>
    <h1>{esc(t['journal'])}</h1>
    <p class="lede">{esc(t['sub'])}</p>
  </div>
{body}
  <p class="rss-line"><a class="more-link" href="/journal/feed.xml">RSS</a></p>
</main>
""" + footer(loc, targets, loc if lang else ""))


def card_posts(lang, posts):
    """journal cards on a home page: that language's posts; none yet -> the English originals (else Korean)."""
    own = [p for p in posts if p["lang"] == lang]
    return (own or [p for p in posts if p["lang"] == "en"] or [p for p in posts if p["lang"] == "ko"])[:3]


# ---- verse chip on the home cards -------------------------------------------------------------------------------------------
# A wrong verse shown for an article is the worst failure of a faith app, so the chip is conservative: it is shown only when the
# reference is unambiguous — and otherwise left out. The expected value of every shipped post is pinned in tests/test_home_journal.py
# against the app's verse file (assets/verses/daily_verses.json).
BOOKS_KO = ("창세기 출애굽기 레위기 민수기 신명기 여호수아 사사기 룻기 사무엘상 사무엘하 열왕기상 열왕기하 역대상 역대하 에스라 느헤미야 에스더 욥기 시편 "
            "잠언 전도서 아가 이사야 예레미야 예레미야애가 에스겔 다니엘 호세아 요엘 아모스 오바댜 요나 미가 나훔 하박국 스바냐 학개 스가랴 말라기 "
            "마태복음 마가복음 누가복음 요한복음 사도행전 로마서 고린도전서 고린도후서 갈라디아서 에베소서 빌립보서 골로새서 데살로니가전서 "
            "데살로니가후서 디모데전서 디모데후서 디도서 빌레몬서 히브리서 야고보서 베드로전서 베드로후서 요한일서 요한이서 요한삼서 유다서 요한계시록").split()
BOOKS_EN = ("Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|1 Samuel|2 Samuel|1 Kings|2 Kings|1 Chronicles|2 Chronicles|Ezra|"
            "Nehemiah|Esther|Job|Psalm|Psalms|Proverbs|Ecclesiastes|Song of Solomon|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|"
            "Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|1 Corinthians|2 Corinthians|"
            "Galatians|Ephesians|Philippians|Colossians|1 Thessalonians|2 Thessalonians|1 Timothy|2 Timothy|Titus|Philemon|Hebrews|James|1 Peter|"
            "2 Peter|1 John|2 John|3 John|Jude|Revelation").split("|")
BOOKS = {"ko": set(BOOKS_KO), "en": set(BOOKS_EN)}
USFM = ("GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON "
        "MIC NAM HAB ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN "
        "JUD REV").split()  # book codes in the order of BOOKS_KO (scripture.json keys: "PSA 46:10", Korean = English numbering)
BOOK_CODE = {"ko": dict(zip(BOOKS_KO, USFM)), "en": dict(zip([b for b in BOOKS_EN if b != "Psalms"], USFM), Psalms="PSA")}  # other languages: only an explicit `verse:` in the front matter (same shape check)
VERSE_RE = re.compile(r"^(?P<book>\d? ?[^\d:()]+?) (?P<ch>[1-9]\d{0,2}):(?P<v>[1-9]\d{0,2})(?:[-\u2013](?P<v2>[1-9]\d{0,2}))?$")
REF_LINE_RE = re.compile(r"^> (?P<ref>[^()]+?) \((?P<ver>[^()]+)\)$")


def verse_shape_ok(ref, lang):
    """`책 장:절` (or `장:절-절`) — and, for ko/en, the book must be a real book name of that language."""
    m = VERSE_RE.match(ref)
    if not m or (m.group("v2") and int(m.group("v2")) <= int(m.group("v"))):
        return False
    return lang not in BOOKS or m.group("book") in BOOKS[lang]


def verse_ref(p):
    """the reference (`시편 121:2`) for the card's verse chip, or None when it is not certain.
    From the article's quotation block: the text must hold exactly ONE block `> quote / > / > <ref> (<Bible version>)` (nothing else quoted;
    the version in the parentheses must be the post's `bible_version`). An optional front matter `verse:` is the preferred value for the chip;
    when the block gives a different reference too, the two disagree -> no chip."""
    lang = p["lang"]
    explicit = (p.get("verse") or "").strip()
    if explicit and not verse_shape_ok(explicit, lang):
        explicit = ""  # malformed -> as if absent (and never shown)
    found = None
    quote = [l for l in p["_body"].split("\n") if l.startswith(">")]
    if len(quote) == 3 and quote[0] != ">" and quote[1] == ">":
        m = REF_LINE_RE.match(quote[2])
        bv = p.get("_bible") or ""
        if m and verse_shape_ok(m.group("ref"), lang) and bv and m.group("ver").strip() and bv.startswith(m.group("ver").strip()):
            found = m.group("ref")
    if explicit and found and explicit != found:
        return None
    return explicit or found or None


def verse_key(p):
    """"PSA 46:10" for a ko/en original's quoted verse (from verse_ref), or None."""
    ref = verse_ref(p)
    m = VERSE_RE.match(ref) if ref else None
    code = BOOK_CODE.get(p["lang"], {}).get(m.group("book")) if m else None
    return "%s %s:%s%s" % (code, m.group("ch"), m.group("v"), "-" + m.group("v2") if m.group("v2") else "") if code else None


def scripture_block(key, lang):
    """the quotation block a translation in `lang` must carry for the verse `key`, as its `>` lines + the front matter it implies:
    -> (lines, bible_version, verse) or None when scripture.json has no such verse/language.
    text mode: `> verse` / `>` / `> ref (version)` with bible_version = version. reference mode (no confirmed public-domain text):
    the reference alone, `bible_version: none` (no Scripture text is quoted) and `verse: ref` (the card chip)."""
    ver = (SCRIPTURE or {}).get("versions", {}).get(lang)
    ent = (SCRIPTURE or {}).get("verses", {}).get(key, {}).get(lang)
    if not ver or not ent:
        return None
    if ver["mode"] == "text":
        return ["> " + ent["text"], ">", "> %s (%s)" % (ent["ref"], ver["version"])], ver["version"], None
    return ["> " + ent["ref"]], "none", ent["ref"]


def scripture_errors(posts, all_posts):
    """a translation may quote Scripture only as copied from scripture.json for its original's verse — nothing else, to the letter."""
    if SCRIPTURE is None:
        return []
    errs = []
    for p in posts:
        of = p.get("translation_of")
        if not of or p["draft"]:
            continue
        quote = [l for l in p["_body"].split("\n") if l.startswith(">")]
        orig = all_posts.get((p["slug"], of))
        key = verse_key(orig) if orig else None
        if not key:
            if quote:
                errs.append("%s: quotes something, but the %s original has no readable verse reference to take the verse from" % (p["_src"], of))
            continue
        want = scripture_block(key, p["lang"])
        if want is None:
            errs.append("%s: no %s text for %s in content/journal/scripture.json — run python3 scripts/fetch_scripture.py" % (p["_src"], p["lang"], key))
            continue
        lines, bible, verse = want
        if quote != lines:
            errs.append("%s: the quotation block must be exactly the %s verse of scripture.json (%s) — run python3 scripts/journal_i18n.py apply\n"
                        "      want: %s\n      have: %s" % (p["_src"], p["lang"], key, " / ".join(lines), " / ".join(quote) or "(none)"))
        if (p.get("bible_version") or "").strip() != bible:
            errs.append("%s: bible_version must be %r (scripture.json versions.%s)" % (p["_src"], bible, p["lang"]))
        if verse and (p.get("verse") or "").strip() != verse:
            errs.append("%s: `verse: %s` is required (reference-only language: the chip comes from the front matter)" % (p["_src"], verse))
    return errs


def render_home_cards(posts, lang=None):
    """journal cards of the home page (<= 3): each card is ONE <a> (chips · date · title · summary · "read"), so the whole card is the click
    target — the chips are plain <span>s, never links. lang = the page's language: a card whose post is in another language (the
    card_posts fallback) gets a language badge. The grid class carries the card count (j-n1/j-n2/j-n3): 3 cards -> 3 columns on desktop,
    fewer -> never an empty slot."""
    posts = posts[:3]
    if not posts:
        return ""

    def card(p):
        verse = verse_ref(p)
        top = '<span class="j-cat">%s</span>' % esc(p["category"]) + ('<span class="j-verse">%s</span>' % esc(verse) if verse else "")
        badge = '<span class="j-lang">%s</span>' % esc(LANGS[p["lang"]]["name"]) if lang and p["lang"] != lang else ""
        return f"""      <a class="j-card" href="{post_path(p)}" lang="{esc(p['lang'])}">
        <div class="j-top">{top}</div>
        <p class="j-date">{with_no(p, time_tag(p))}</p>
        <h3 class="j-title">{esc(p['title'])}</h3>
        <p class="j-desc">{esc(p['description'])}</p>
        <div class="j-foot"><span class="j-more"><span>{esc(ui(p['lang'])['read_more'])}</span> <span aria-hidden="true">→</span></span>{badge}</div>
      </a>"""
    return '    <div class="journal-grid j-n%d">\n%s\n    </div>' % (len(posts), "\n".join(card(p) for p in posts))


def render_redirect(new_url):
    """static redirect stub for a moved URL: canonical + meta refresh + visible link (no JS, no ?lang=)."""
    u = esc(new_url)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<!-- {GEN_MARK} — redirect stub for a moved page -->
<title>Moved — still()</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="canonical" href="{u}">
<meta http-equiv="refresh" content="0; url={u}">
<meta name="robots" content="noindex, follow">
</head>
<body>
<p><a href="{u}">{u}</a></p>
</body>
</html>
"""


def sweep_generated(root, written):
    """delete pages this script generated earlier (posts that are gone / now draft, dropped aliases) and empty dirs."""
    base = root / "journal"
    if not base.is_dir():
        return
    for idx in sorted(base.rglob("index.html")):
        if idx not in written and GEN_MARK in idx.read_text(encoding="utf-8"):
            idx.unlink()
    for d in sorted((x for x in base.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def rfc822(p):
    """RSS date of a post: its real time when known, else 09:00 KST of its date."""
    w = post_when(p) or dt.datetime(p["_date"].year, p["_date"].month, p["_date"].day, 9, 0, tzinfo=KST)
    return w.strftime("%a, %d %b %Y %H:%M:%S +0900")


def render_feed(posts):
    items = "\n".join(f"""    <item>
      <title>{esc(p['title'])}</title>
      <link>{post_url(p)}</link>
      <guid isPermaLink="true">{post_url(p)}</guid>
      <pubDate>{rfc822(p)}</pubDate>
      <category>{esc(p['category'])}</category>
      <description>{esc(p['description'])}</description>
    </item>""" for p in posts)
    last = rfc822(posts[0]) if posts else rfc822({"_date": dt.date(2026, 10, 22)})
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>still() Journal</title>
    <link>{SITE}/journal/</link>
    <atom:link href="{SITE}/journal/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{esc(UI['en']['sub'])}</description>
    <language>en</language>
    <lastBuildDate>{last}</lastBuildDate>
{items}
  </channel>
</rss>
"""


def render_sitemap_block(posts, grp, list_langs):
    if not posts:
        return ""
    xl = lambda pairs, default: "".join('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>\n' % (l, u) for l, u in sorted(pairs.items())) \
        + '    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>\n' % default
    scopes = list_scopes(posts, list_langs)
    counts = page_counts(scopes)
    last = lambda ps: max(p.get("updated") or p["_date"].isoformat() for p in ps)  # every page of a list: a new post reshuffles all of them
    rows = []
    for key in [None] + list(list_langs):  # the hub, then each language that has at least one post
        for n in range(1, counts[key] + 1):
            hub_n = SITE + list_path(None, n if n <= counts[None] else 1)
            hub = key is None
            rows.append("  <url>\n    <loc>%s%s</loc>\n    <lastmod>%s</lastmod>\n%s    <priority>%s</priority>\n%s  </url>" % (
                SITE, list_path(key, n), last(posts if hub else scopes[key]), "    <changefreq>daily</changefreq>\n" if hub and n == 1 else "",
                ("0.6" if n == 1 else "0.4") if hub else ("0.4" if n == 1 else "0.3"), xl(list_pairs(list_langs, n, counts), hub_n)))
    for p in posts:
        pair, default = pair_urls(p, grp)
        links = xl(pair, default)
        imgs = body_images(p) or ["/og-image.png"]
        imgs = "".join("    <image:image>\n      <image:loc>%s</image:loc>\n    </image:image>\n" % esc(abs_url(u)) for u in imgs)
        rows.append("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <priority>0.5</priority>\n%s%s  </url>"
                    % (post_url(p), (p.get("updated") or p["_date"].isoformat()), links, imgs))
    return "\n".join(rows) + "\n"


def render_llms_block(posts):
    if not posts:
        return ""
    lines = ["## Journal", "%s Feed: %s/journal/feed.xml · Index: %s/journal/ · Every post exists at /journal/<lang>/<slug>/ in each language listed below. "
             "These are stories, not medical advice, and they do not replace professional care; each page lists crisis lines." % (UI["en"]["sub"], SITE, SITE)]
    for l in LANGS:  # one section per language that has posts
        ps = [p for p in posts if p["lang"] == l]
        if ps:
            lines += ["", "### Journal — %s (%s) · Index: %s%s" % (LANGS[l]["name"], l, SITE, lang_path(l)), ""]
            lines += ["- [%s](%s) — %s (%s, %s%s)" % (p["title"], post_url(p), p["description"], l, p["_date"].isoformat(), ", AI translation" if p.get("translation_of") else "") for p in ps]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- sources
def read_posts(root, drafts, now=None):
    """-> (published posts [with _html], all posts {(slug, lang): post}, errors). Drafts are skipped unless `drafts`.
    A scheduled post (`publish_at`) counts as published only when `now` (aware datetime) is given and has reached it."""
    src = root / "content" / "journal"
    posts, errors, all_posts = [], [], {}
    files = sorted(src.glob("*/*.md")) if src.is_dir() else []
    for f in (sorted(src.glob("*.md")) if src.is_dir() else []):
        if f.name.lower() != "readme.md":
            errors.append("%s: move to content/journal/<lang>/%s (one folder per language, ko and en included)" % (f.name, f.name))
    for f in files:
        if f.name.lower() == "readme.md":
            continue
        name = str(f.relative_to(src))
        try:
            p = parse_post(f)
            p["_src"] = name
            if f.parent.name != p["lang"]:
                raise ValueError("file is in %s/ but lang is %s" % (f.parent.name, p["lang"]))
            if f.stem != p["slug"]:
                raise ValueError("file name must be <slug>.md (slug is %r)" % p["slug"])
        except ValueError as ex:
            errors.append("%s: %s" % (name, ex))
            continue
        all_posts[(p["slug"], p["lang"])] = p
        if p["lang"] in HELD and not p["draft"]:
            errors.append("%s: the %s journal is on hold (%s) — keep the post `draft: true`" % (name, p["lang"], HELD[p["lang"]]))
            continue
        p["_held"] = bool(p["_publish_at"]) and (now is None or p["_publish_at"] > now)
        if (p["draft"] or p["_held"]) and not drafts:
            continue
        if p["_held"]:
            p["draft"] = True  # preview (--drafts) shows it as a draft: DRAFT flag + noindex
        p["_html"] = markdown(p["_body"])
        posts.append(p)
    return posts, all_posts, errors


def expected_sitemap_urls(root, now=None):
    """URLs check_sitemap.py requires in sitemap.xml for the journal (published = non-draft, due posts). May raise ValueError."""
    root = Path(root)
    global ROOT
    ROOT = root
    posts, _, errors = read_posts(root, drafts=False, now=now)
    if errors:
        raise ValueError("; ".join(errors))
    want = {SITE + "/journal/"} if posts else set()
    for p in posts:
        want.add(post_url(p))
    if posts:
        scopes = list_scopes(posts, [l for l in LANGS if any(p["lang"] == l for p in posts)])
        for key, n in page_counts(scopes).items():
            want.update(SITE + list_path(key, i) for i in range(1, n + 1))
    return want


def build(root, drafts=False, strict_safety=False, check_only=False, now=None):
    """validate everything and (unless check_only) write the site. Returns (exit code, message)."""
    global ROOT, LIST_LANGS
    ROOT = root
    errors = load_data(root)
    if errors:
        return 1, "journal: errors\n  " + "\n  ".join(errors)
    posts, all_posts, errors = read_posts(root, drafts, now)
    if not errors:
        errors += check_translations(posts, all_posts, drafts)
        errors += scripture_errors(posts, all_posts)
        for p in posts:
            errors += check_post_images(p)
    if strict_safety:
        errors += strict_safety_errors({p["lang"] for p in posts})
    if errors:
        return 1, "journal: errors\n  " + "\n  ".join(errors)
    posts.sort(key=lambda p: order_key(p) + (p["lang"],), reverse=True)  # newest first; same day: later time first
    NUMBERS.clear()
    NUMBERS.update(assign_numbers(posts))
    grp = groups(posts)
    list_langs = [l for l in LANGS if any(p["lang"] == l for p in posts)]
    LIST_LANGS = set(list_langs)
    scopes = list_scopes(posts, list_langs)
    originals = scopes[None]
    counts = page_counts(scopes)
    if check_only:
        return 0, "journal: OK — %d post(s) ready%s" % (len(posts), " (incl. drafts)" if drafts else "")

    out = root / "journal"
    out.mkdir(exist_ok=True)
    written = set()

    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.add(path)

    for p in posts:
        write(root / post_path(p).strip("/") / "index.html", render_post(p, grp))
        for al in p["_aliases"]:  # old URL -> static redirect stub to the new address
            write(root / al.strip("/") / "index.html", render_redirect(post_url(p)))
    for key, scope in scopes.items():  # hub + every language list: page 1 at the plain address, pages 2+ at <list>page/<n>/
        for n in range(1, counts[key] + 1):
            write(root / list_path(key, n).strip("/") / "index.html", render_list(scope, key, list_langs, n, counts))
    write(out / "feed.xml", render_feed(originals))
    sweep_generated(root, written)

    sm = root / "sitemap.xml"
    sm_xml = replace_between(sm.read_text(encoding="utf-8"), r"<!-- journal:start[^>]*-->",
                             "  <!-- journal:end -->", render_sitemap_block(posts, grp, list_langs), "sitemap.xml")
    if "xmlns:image=" not in sm_xml:
        sm_xml = sm_xml.replace("<urlset ", '<urlset xmlns:image="%s"\n        ' % IMG_NS, 1)
    sm.write_text(sm_xml, encoding="utf-8")
    llms = root / "llms.txt"
    llms.write_text(replace_between(llms.read_text(encoding="utf-8"), r"<!-- journal:llms:start[^>]*-->",
                                    "<!-- journal:llms:end -->", render_llms_block(posts), "llms.txt"), encoding="utf-8")
    import build_home  # home page: 11 static language pages + their sitemap/llms blocks
    build_home.build(root, {l: render_home_cards(card_posts(l, posts), l) for l in LANGS}, {l: jhome(l) for l in LANGS},
                     max([p.get("updated") or p["_date"].isoformat() for p in posts], default=None))
    import build_info  # FAQ + "how still() is different" pages, 11 languages (uses this module's header/footer/head)
    build_info.build(root, sys.modules[__name__], bool(posts))
    return 0, "journal: built %d post(s)%s → %s" % (len(posts), " (incl. drafts)" if drafts else "", out)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="site root (default: this repo)")
    ap.add_argument("--drafts", action="store_true", help="include draft posts (preview only — never commit the result)")
    ap.add_argument("--check", action="store_true", help="validate posts + safety data and require the committed output to be up to date; write nothing")
    ap.add_argument("--now", metavar="WHEN", help="publish scheduled posts (publish_at) that are due at WHEN: `now` or `YYYY-MM-DD HH:MM` (KST). "
                    "Default: none are (the committed output). The deploy runner uses this; never commit the result.")
    ap.add_argument("--strict-safety", action="store_true",
                    help="fail while a language with published posts still has draft (unreviewed) crisis-line data — the deploy gate")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    try:
        now = parse_when(a.now) if a.now else None
    except ValueError as ex:
        print("journal: --now: %s" % ex, file=sys.stderr)
        return 1
    if a.check:
        code, msg = build(root, a.drafts, a.strict_safety, check_only=True, now=now)
        if code == 0 and not a.drafts and now is None:  # freshness only for the committed (clock-free) output
            diffs = check_fresh(root, lambda r: build(r, False, False))
            if diffs:
                code, msg = 1, "journal: out of date — run python3 scripts/build_journal.py\n  " + "\n  ".join(diffs)
    else:
        code, msg = build(root, a.drafts, a.strict_safety, now=now)
    print(msg, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
