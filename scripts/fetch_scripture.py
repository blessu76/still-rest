#!/usr/bin/env python3
"""Fetch the Scripture quoted by the journal, verse by verse, from the public-domain source texts — never written or translated by hand/AI.

Why: a translated article must quote the verse of ITS language's public-domain Bible (decision 0088) to the letter. A verse made up by a
translator (human or AI) is the worst failure a faith app can have, so the verse text in a translated post comes only from here.

    python3 scripts/fetch_scripture.py            # download the sources, rewrite content/journal/scripture.json
    python3 scripts/fetch_scripture.py --verify   # download again and fail if scripture.json differs from the sources (writes nothing)
    python3 scripts/fetch_scripture.py --cache DIR  # keep/reuse the downloaded zips in DIR (default: a temp dir)

Which verses: every reference quoted by a Korean original (`> 시편 46:10 (개역한글)` line of content/journal/ko/*.md, drafts included).
Sources: the USFM zips of ebible.org (https://ebible.org/Scriptures/<id>_usfm.zip), each marked public domain on its copyright page.
Languages whose public-domain text could not be confirmed (MODE "reference") get the reference only — no verse text — until someone
confirms a source (then add it to SOURCES and run this again). Languages on hold (content/journal/hold.json) are skipped.

Versification: the reference written in a post is the chapter:verse OF ITS SOURCE TEXT. Psalms are numbered differently in some
Bibles (Russian Synodal = Septuagint numbering, Louis Segond counts a psalm's title as verse 1), so for those languages a Psalm
reference must be mapped by hand in VERSIFICATION after reading the source — never by a formula. A missing entry is an error.
stdlib only (Python 3.8+).
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_journal import BOOKS_KO, USFM  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "journal" / "scripture.json"
EBIBLE = "https://ebible.org/Scriptures/%s_usfm.zip"

# lang -> source. version = the short name printed in the post (`> Psalm 46:10 (WEB)`) and its `bible_version`.
SOURCES = {
    "en": {"mode": "text", "ebible": "engwebp", "version": "WEB", "name": "World English Bible",
           "copyright": "https://ebible.org/engwebp/copyright.htm"},
    "zh": {"mode": "text", "ebible": "cmn-cu89s", "version": "和合本", "name": "和合本（新标点，简体）",
           "copyright": "https://ebible.org/cmn-cu89s/copyright.htm"},
    "es": {"mode": "text", "ebible": "spaRV1909", "version": "Reina-Valera 1909", "name": "Santa Biblia — Reina Valera 1909",
           "copyright": "https://ebible.org/spaRV1909/copyright.htm"},
    "ru": {"mode": "text", "ebible": "russyn", "version": "Синодальный перевод", "name": "Синодальный перевод",
           "copyright": "https://ebible.org/russyn/copyright.htm"},
    "vi": {"mode": "text", "ebible": "vie1934", "version": "Kinh Thánh 1925", "name": "Kinh Thánh (Cadman; Tân Ước 1923, Cựu Ước 1925)",
           "copyright": "https://ebible.org/vie1934/copyright.htm"},
    "fr": {"mode": "text", "ebible": "fraLSG", "version": "Louis Segond 1910", "name": "Louis Segond 1910",
           "copyright": "https://ebible.org/fraLSG/copyright.htm"},
    "de": {"mode": "text", "ebible": "deu1912", "version": "Lutherbibel 1912", "name": "Lutherbibel 1912",
           "copyright": "https://ebible.org/deu1912/copyright.htm"},
    # reference only: decision 0088 names the version, but no public-domain copy of its text could be confirmed (room note 20261022-221259)
    "ja": {"mode": "reference", "version": "口語訳",
           "why": "口語訳(1955) public-domain status is unconfirmed (no statement from the Japan Bible Society; the Japanese Wikisource copy is "
                  "under a copyright deletion review, checked 2026-10-25). Verse text is left out until it is confirmed."},
    "pt": {"mode": "reference", "version": "Almeida",
           "why": "no confirmed public-domain copy of Almeida Revista e Corrigida (1898) was found (ebible has none; later ARC/ACF "
                  "editions are copyrighted). Verse text is left out until a source is confirmed."},
}

# the name a reference is written with, per language (a citation label, not Scripture text). Add a book here before its first use.
BOOK_NAMES = {
    "en": {"PSA": "Psalm", "ISA": "Isaiah", "LAM": "Lamentations", "MAT": "Matthew", "1PE": "1 Peter"},
    "ja": {"PSA": "詩篇", "ISA": "イザヤ書", "LAM": "哀歌", "MAT": "マタイによる福音書", "1PE": "ペテロの第一の手紙"},
    "zh": {"PSA": "诗篇", "ISA": "以赛亚书", "LAM": "耶利米哀歌", "MAT": "马太福音", "1PE": "彼得前书"},
    "es": {"PSA": "Salmos", "ISA": "Isaías", "LAM": "Lamentaciones", "MAT": "Mateo", "1PE": "1 Pedro"},
    "pt": {"PSA": "Salmos", "ISA": "Isaías", "LAM": "Lamentações", "MAT": "Mateus", "1PE": "1 Pedro"},
    "ru": {"PSA": "Псалом", "ISA": "Исаия", "LAM": "Плач Иеремии", "MAT": "От Матфея", "1PE": "1 Петра"},
    "vi": {"PSA": "Thi Thiên", "ISA": "Ê-sai", "LAM": "Ca Thương", "MAT": "Ma-thi-ơ", "1PE": "1 Phi-e-rơ"},
    "fr": {"PSA": "Psaume", "ISA": "Ésaïe", "LAM": "Lamentations", "MAT": "Matthieu", "1PE": "1 Pierre"},
    "de": {"PSA": "Psalm", "ISA": "Jesaja", "LAM": "Klagelieder", "MAT": "Matthäus", "1PE": "1. Petrus"},
}
# Korean (= English) Psalm numbering -> the numbering of the source text, checked by reading the source (2026-10-25, Paul).
# ru Synodal: LXX chapter numbers + titles counted as verses. fr LSG: titles counted as verse 1. de deu1912 on ebible is already
# renumbered to the English scheme (decision 0088 "46,11 -> 46:10"), so it needs no entry.
VERSIFICATION = {
    "ru": {"PSA 4:8": "PSA 4:9", "PSA 23:2": "PSA 22:2", "PSA 46:10": "PSA 45:11", "PSA 121:2": "PSA 120:2"},
    "fr": {"PSA 4:8": "PSA 4:9", "PSA 23:2": "PSA 23:2", "PSA 46:10": "PSA 46:11", "PSA 121:2": "PSA 121:2"},
}
HAND_MAPPED = {"ru": ("PSA",), "fr": ("PSA",)}  # books whose numbering differs in that language: every reference needs an entry above
NO_SPACE = ("zh", "ja")  # scripts without spaces between words: the line breaks of poetry are joined without a space


def ko_books():
    return dict(zip(BOOKS_KO, USFM))


REF_RE = re.compile(r"^> (?P<book>.+?) (?P<ch>\d+):(?P<v>\d+) \((?P<ver>[^()]+)\)\s*$")


def ko_refs(root):
    """{"PSA 46:10": "시편 46:10"} for every verse reference quoted by a Korean original."""
    books, out = ko_books(), {}
    for f in sorted((root / "content" / "journal" / "ko").glob("*.md")):
        for line in f.read_text(encoding="utf-8").split("\n"):
            m = REF_RE.match(line.strip())
            if m and m.group("book") in books:
                out["%s %s:%s" % (books[m.group("book")], m.group("ch"), m.group("v"))] = "%s %s:%s" % (m.group("book"), m.group("ch"), m.group("v"))
    return out


def ref_order(key):
    book, cv = key.split()
    return (USFM.index(book),) + tuple(int(x) for x in cv.split(":"))


def source_key(lang, key):
    book = key.split()[0]
    if book in HAND_MAPPED.get(lang, ()):
        if key not in VERSIFICATION.get(lang, {}):
            raise SystemExit("fetch_scripture: %s %s needs a hand-checked entry in VERSIFICATION[%r] (its numbering differs) — read the source "
                             "and add it" % (lang, key, lang))
        return VERSIFICATION[lang][key]
    return VERSIFICATION.get(lang, {}).get(key, key)


def usfm_verse(text, ch, v, lang):
    """the plain text of verse ch:v of a USFM book: footnotes, cross references, headings and word markup removed."""
    m = re.search(r"\\c %d\s(.*?)(?=\\c \d+\s|\Z)" % ch, text, re.S)
    if not m:
        raise ValueError("chapter %d not found" % ch)
    m = re.search(r"\\v %d\s(.*?)(?=\\v \d+[\s-]|\Z)" % v, m.group(1), re.S)
    if not m:
        raise ValueError("verse %d:%d not found" % (ch, v))
    s = m.group(1)
    s = re.sub(r"\\f\s.*?\\f\*", "", s, flags=re.S)        # footnotes
    s = re.sub(r"\\fe\s.*?\\fe\*", "", s, flags=re.S)
    s = re.sub(r"\\x\s.*?\\x\*", "", s, flags=re.S)        # cross references
    s = re.sub(r"(?m)^\\(s\d?|ms\d?|mr|d|r|sp|cl|sr)\b[^\n]*$", "", s)  # headings / psalm titles on their own line
    s = re.sub(r"\\\+?w ([^|\\]*)(?:\|[^\\]*)?\\\+?w\*", r"\1", s)    # \w word|strong="H1234"\w*
    s = re.sub(r"\\\+?[a-z]+\d*\*", "", s)                # closing character markers (\nd* \wj* \add*): nothing
    s = re.sub(r"\\\+?[a-z]+\d* ?", " ", s)             # every other marker (\q1 \p \add \nd \wj ...) with its delimiting space
    s = re.sub(r"[ \t\r\n]+", " ", s).strip()            # ASCII whitespace only (keeps the CUV's ideographic space before 神)
    if lang in NO_SPACE:
        s = s.replace(" ", "")
    return s


def fetch(eid, cache):
    path = Path(cache) / ("%s_usfm.zip" % eid)
    if not path.is_file():
        req = urllib.request.Request(EBIBLE % eid, headers={"User-Agent": "still.ipe.rest journal build (scripts/fetch_scripture.py)"})
        with urllib.request.urlopen(req, timeout=120) as r:
            path.write_bytes(r.read())
    return path


def build(root, cache):
    refs = ko_refs(root)
    held = {k for k in json.loads((root / "content/journal/hold.json").read_text(encoding="utf-8")) if not k.startswith("_")}
    versions, verses = {}, {k: {"ko": {"ref": refs[k]}} for k in sorted(refs, key=ref_order)}
    for lang, src in SOURCES.items():
        if lang in held:
            continue
        meta = {k: v for k, v in src.items() if k != "ebible"}
        if src["mode"] == "text":
            z = fetch(src["ebible"], cache)
            meta["source"] = EBIBLE % src["ebible"]
            meta["sha256"] = hashlib.sha256(z.read_bytes()).hexdigest()
            arc = zipfile.ZipFile(z)
        versions[lang] = meta
        for key in verses:
            book, cv = key.split()
            name = BOOK_NAMES[lang].get(book)
            if not name:
                raise SystemExit("fetch_scripture: no %s name for book %s — add it to BOOK_NAMES" % (lang, book))
            skey = source_key(lang, key) if src["mode"] == "text" else key
            sbook, scv = skey.split()
            ent = {"ref": "%s %s" % (name, scv)}
            if src["mode"] == "text":
                member = [n for n in arc.namelist() if re.search(r"-%s%s\.usfm$" % (re.escape(sbook), re.escape(src["ebible"])), n)]
                if len(member) != 1:
                    raise SystemExit("fetch_scripture: %s: book file %s not found in %s" % (lang, sbook, z.name))
                ch, v = (int(x) for x in scv.split(":"))
                ent["src"] = skey
                ent["text"] = usfm_verse(arc.read(member[0]).decode("utf-8-sig"), ch, v, lang)
            verses[key][lang] = ent
    return {
        "_readme": [
            "GENERATED by scripts/fetch_scripture.py — do not edit by hand. Verse text copied to the letter from the public-domain source of each "
            "language (versions.<lang>.source, sha256 of the downloaded file). Never translate or retype a verse.",
            "verses.<USFM ref, Korean/English numbering>.<lang>: ref = how the reference is written in that language (chapter:verse OF ITS SOURCE), "
            "text = the verse. A language with mode 'reference' has no text: its posts give the reference only.",
            "A translated post's quotation block must be exactly `> {text}` / `>` / `> {ref} ({version})` (build_journal.py checks it).",
        ],
        "fetched_on": dt.date.today().isoformat(),
        "versions": versions,
        "verses": verses,
    }


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--cache", help="directory for the downloaded zips (reused when present)")
    ap.add_argument("--verify", action="store_true", help="download again and compare with scripture.json; write nothing")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    cache = a.cache or tempfile.mkdtemp(prefix="still-scripture-")
    Path(cache).mkdir(parents=True, exist_ok=True)
    data = build(root, cache)
    out = root / "content" / "journal" / "scripture.json"
    if a.verify:
        cur = json.loads(out.read_text(encoding="utf-8"))
        cur.pop("fetched_on", None)
        data.pop("fetched_on", None)
        if cur != data:
            print("fetch_scripture: scripture.json differs from the sources — run python3 scripts/fetch_scripture.py and review the diff", file=sys.stderr)
            return 1
        print("fetch_scripture: OK — scripture.json matches the sources (%d verses)" % len(data["verses"]))
        return 0
    old = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    if {k: v for k, v in old.items() if k != "fetched_on"} == {k: v for k, v in data.items() if k != "fetched_on"}:
        data["fetched_on"] = old.get("fetched_on", data["fetched_on"])  # nothing changed: keep the file as it is
    out.write_text(dump(data), encoding="utf-8")
    print("fetch_scripture: %d verses x %d languages -> %s" % (len(data["verses"]), len(data["versions"]), out.relative_to(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
