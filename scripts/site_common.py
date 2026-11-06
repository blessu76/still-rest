"""Shared constants and helpers for the still.ipe.rest build scripts (stdlib only, Python 3.9+ — the vendored ipe_web_kit needs it)."""
import datetime as dt
import re
import sys
from pathlib import Path

SITE = "https://still.ipe.rest"

# Organization hub / meta description / escape / localtime come from the vendored ipe_web_kit (vendor/ipe_web_kit, v0.1.0 — never edit the copy;
# update it with `python3 -m ipe_web_kit.vendor update`). The names stay here so build_*.py and the tests keep importing them from site_common.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vendor"))
from ipe_web_kit.localtime import with_localtime  # noqa: E402,F401
from ipe_web_kit.seo import META_DESC_MAX, ORG, ORG_ID, ORG_LOGO, esc, meta_desc  # noqa: E402,F401

# The 13 languages of the still() site (the app's 11, decision 0087, plus ar·hi, which match ipe.rest). name = the language's own name (language select), og = og:locale.
# Order = order of the language select, hreflang lists and the sitemap.
LANGS = {
    "en": {"name": "English", "og": "en_US", "dir": "ltr"},
    "ko": {"name": "한국어", "og": "ko_KR", "dir": "ltr"},
    "ja": {"name": "日本語", "og": "ja_JP", "dir": "ltr"},
    "zh": {"name": "中文", "og": "zh_CN", "dir": "ltr"},
    "es": {"name": "Español", "og": "es_ES", "dir": "ltr"},
    "pt": {"name": "Português", "og": "pt_BR", "dir": "ltr"},
    "id": {"name": "Bahasa Indonesia", "og": "id_ID", "dir": "ltr"},
    "ru": {"name": "Русский", "og": "ru_RU", "dir": "ltr"},
    "vi": {"name": "Tiếng Việt", "og": "vi_VN", "dir": "ltr"},
    "fr": {"name": "Français", "og": "fr_FR", "dir": "ltr"},
    "de": {"name": "Deutsch", "og": "de_DE", "dir": "ltr"},
    "ar": {"name": "العربية", "og": "ar_AR", "dir": "rtl"},
    "hi": {"name": "हिन्दी", "og": "hi_IN", "dir": "ltr"},
}
# Google Fonts CSS. A plain <link rel="stylesheet"> blocks rendering until fonts.googleapis.com answers (~0.9 s on mobile, Lighthouse FCP 3.4 s),
# so every page loads it the non-blocking way: media="print" (fetched at low priority, never blocks paint) flipped to "all" on load, with a
# <noscript> fallback. The font files themselves still come from fonts.gstatic.com; display=swap shows the fallback font until they arrive.
FONT_CSS = "https://fonts.googleapis.com/css2?family=Gentium+Book+Plus:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap"


def font_links(css=FONT_CSS):
    """preconnect x2 + the non-blocking Google Fonts stylesheet (+ noscript fallback) — the one block every page head uses."""
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="%s" media="print" onload="this.media=\'all\'">\n'
            '<noscript><link rel="stylesheet" href="%s"></noscript>' % (css, css))


# GA4 — the same property as ipe.rest (a sub-domain of it, so no cross-domain setup). ONE snippet, inserted into the <head> of every page:
# generated pages through head() / the home template ({{GA_SNIPPET}}), the hand-written pages (privacy, terms, 404) through sync_static_ga().
# The privacy policy (section 2), the FAQ answer (content/info/pages.json), llms.txt and README say so -> change them together with this.
GA_MEASUREMENT_ID = "G-XG4BH800J0"
GA_SNIPPET = (
    "<script>(function(){var GA_ID='%s';"
    "window.dataLayer=window.dataLayer||[];window.gtag=function(){window.dataLayer.push(arguments)};"
    # a local preview (python -m http.server, a test render) must not count as a visit
    "if(/^(localhost|127\\.0\\.0\\.1|\\[::1\\])$/.test(location.hostname))return;"
    "var s=document.createElement('script');s.async=true;s.src='https://www.googletagmanager.com/gtag/js?id='+GA_ID;document.head.appendChild(s);"
    "window.gtag('js',new Date());window.gtag('config',GA_ID);"
    # clicks on links that leave the site (link address only); *.ipe.rest is the same studio, not an exit
    "function out(e){if(e.type==='auxclick'&&e.button!==1)return;"
    "var a=e.target.closest&&e.target.closest('a[href^=\"http\"]');if(!a)return;"
    "var h=a.hostname;if(h===location.hostname||h==='ipe.rest'||/\\.ipe\\.rest$/.test(h))return;"
    "window.gtag('event','outbound_click',{link_url:a.href,link_domain:h,transport_type:'beacon'})}"
    "document.addEventListener('click',out);document.addEventListener('auxclick',out)})();</script>") % GA_MEASUREMENT_ID
GA_START, GA_END = "<!-- ga4:start — scripts/site_common.py GA_SNIPPET -->", "<!-- ga4:end -->"
STATIC_PAGES = ("privacy/index.html", "terms/index.html", "404.html")  # hand-written, not generated: they only get the GA4 block


def sync_static_ga(root):
    """put GA_SNIPPET (between the ga4 markers, just before </head>) into the hand-written pages; idempotent. Returns the paths written."""
    from pathlib import Path
    written = []
    for rel in STATIC_PAGES:
        path = Path(root) / rel
        text = path.read_text(encoding="utf-8")
        block = "%s\n%s\n%s\n" % (GA_START, GA_SNIPPET, GA_END)
        i, j = text.find("<!-- ga4:start"), text.find(GA_END)
        if i != -1 and j > i:
            new = text[:i] + block.rstrip("\n") + text[j + len(GA_END):]
        elif i == -1 and j == -1 and text.count("</head>") == 1:
            new = text.replace("</head>", block + "</head>")
        else:
            raise SystemExit("%s: ga4 markers are broken (or no single </head>)" % rel)
        if new != text:
            path.write_text(new, encoding="utf-8")
        written.append(path)
    return written


KST = dt.timezone(dt.timedelta(hours=9))
GEN_MARK = "generated by scripts/build_journal.py"


# Language rule shared by every ipe website (Davy 2026-11-01; _ipe/context/REACH_PROCESS.md "웹사이트 공통 언어 규칙"):
#   1. the URL (/xx/ path, ?lang=xx)  2. the language the visitor chose (localStorage still_lang)  3. the browser's list (navigator.languages,
#   first supported match, ko-KR -> ko)  4. English.
# Only the language-neutral entries run this (the root /, the journal hub /journal/); every /xx/ page is already decided by its URL and never
# moves the visitor. English (stored, browser or fallback) stays where it is - the root is the English page. Crawlers send no language, so they stay.
AUTO_LANG_JS = (
    "<script>(function(){try{"
    "var ALL=__ALL__,OK=__OK__,PRE=__PRE__,u=new URLSearchParams(location.search),q=u.get('lang'),pick=null,url=false;"
    "if(q&&ALL.indexOf(q)>=0){pick=q;url=true;try{localStorage.setItem('still_lang',q)}catch(e){}}"
    "if(!pick){var s=null;try{s=localStorage.getItem('still_lang')}catch(e){}if(s&&ALL.indexOf(s)>=0)pick=s}"
    "if(!pick){var b=navigator.languages&&navigator.languages.length?navigator.languages:[navigator.language||''];"
    "for(var i=0;i<b.length&&!pick;i++){var c=String(b[i]).toLowerCase().split('-')[0];if(ALL.indexOf(c)>=0)pick=c}}"
    "if(pick&&OK.indexOf(pick)>=0&&(pick!=='en'||url)){u.delete('lang');var r=u.toString();"
    "location.replace(PRE+pick+'/'+(r?'?'+r:'')+location.hash)}"
    "}catch(e){}})();</script>\n")


def auto_lang_script(prefix, targets):
    """the language-decision script for a neutral entry page. prefix: where the language pages live ('/' or '/journal/'); targets: the
    languages that have a page there (a language outside it - e.g. vi for the journal - falls to English, i.e. the page stays)."""
    import json
    return (AUTO_LANG_JS.replace("__ALL__", json.dumps(list(LANGS))).replace("__OK__", json.dumps([l for l in LANGS if l in targets]))
            .replace("__PRE__", json.dumps(prefix)))


# ipe.rest (the studio hub) has a page for these languages at /<lang>/; the other still() languages go to its root with ?lang=<lang> (the hub
# reads that query). Links from here to another ipe site carry the page's language - never a bare https://ipe.rest in a translated page.
IPE_REST_LANG_PATHS = ("en", "ko", "ja", "zh", "es", "pt", "id", "ru", "fr", "de", "ar", "hi")


def ipe_rest_url(lang):
    return "https://ipe.rest/%s/" % lang if lang in IPE_REST_LANG_PATHS else "https://ipe.rest/?lang=%s" % lang


def lang_url(lang):
    """absolute URL of the static home page of a language."""
    return "%s/%s/" % (SITE, lang)


def replace_between(text, start_re, end_marker, new, where):
    """replace what sits between a start marker (regex) and an end marker (literal); markers stay."""
    m = re.search(start_re, text)
    e = text.find(end_marker)
    if not m or e == -1 or e < m.end():
        raise SystemExit("marker not found in %s: %s ... %s" % (where, start_re, end_marker))
    return text[:m.end()] + "\n" + new + ("\n" if new and not new.endswith("\n") else "") + text[e:]


def stamped_date(root, sources, stamp):
    """date the files `sources` (paths under root) last changed. Kept in the json file `stamp` ({hash, date}) next to a hash of the
    sources: when the hash differs the stamp is rewritten with today's date, so a sitemap lastmod follows the copy by itself."""
    import datetime
    import hashlib
    import json
    from pathlib import Path
    root = Path(root)
    h = hashlib.sha256()
    for f in sources:
        h.update((root / f).read_bytes())
    digest = h.hexdigest()[:16]
    path = root / stamp
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    if cur.get("hash") == digest and cur.get("date"):
        return cur["date"]
    date = datetime.date.today().isoformat()
    path.write_text(json.dumps({"hash": digest, "date": date}, indent=1) + "\n", encoding="utf-8")
    return date


def check_fresh(root, build_fn):
    """Build into a temp copy of the site and compare with what is committed. Returns a list of differing paths."""
    import filecmp
    import shutil
    import tempfile
    from pathlib import Path
    root = Path(root)
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(root, tmp / "site", ignore=shutil.ignore_patterns(".git", "__pycache__"))
        build_fn(tmp / "site")
        diffs = []
        for f in sorted((tmp / "site").rglob("*")):
            rel = f.relative_to(tmp / "site")
            if f.is_file() and not (root / rel).is_file() or (f.is_file() and not filecmp.cmp(f, root / rel, shallow=False)):
                diffs.append(str(rel))
        return diffs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def parse_when(value):
    """`2026-10-24 11:00` / `2026-10-24T11:00:00+09:00` -> aware datetime; no offset = KST. `now` = the current time. Raises ValueError."""
    value = str(value).strip()
    if value.lower() == "now":
        return dt.datetime.now(KST)
    d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=KST)
