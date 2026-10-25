#!/usr/bin/env python3
"""Journal translations: what is missing, a translator brief, and the Scripture fix-up — no paid API, no network (stdlib only).

The flow for a new post (content/journal/README.md "번역"):
  1. Quill writes the Korean original  content/journal/ko/<slug>.md
  2. python3 scripts/fetch_scripture.py                 # its verse, copied from each language's public-domain Bible
  3. python3 scripts/journal_i18n.py brief <slug> > /tmp/brief.md
     -> hand the brief to a Claude Code session (Paul/Quill, the subscription we already use): it writes content/journal/<lang>/<slug>.md
        for every language the brief lists. The translator never writes a verse: the brief gives the exact quotation block.
  4. python3 scripts/journal_i18n.py apply               # (re)writes every translation's quotation block + bible_version/verse from
                                                          # scripture.json — so a verse can never be an AI translation
  5. python3 scripts/journal_i18n.py status              # every published original has every language (held languages excepted)
  6. build + gates as usual (build_journal.py checks the quotation blocks again; the tests pin them)

    python3 scripts/journal_i18n.py status [--strict]   # table: slug x language (--strict: exit 1 when a translation is missing)
    python3 scripts/journal_i18n.py block <slug> <lang>  # the quotation block that translation must carry
    python3 scripts/journal_i18n.py brief <slug> [--lang xx ...]
    python3 scripts/journal_i18n.py apply [--slug s] [--lang xx]   # rewrite quotation blocks from scripture.json
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
from site_common import LANGS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load(root):
    errs = bj.load_data(root)
    if errs:
        raise SystemExit("\n".join(errs))
    if bj.SCRIPTURE is None:
        raise SystemExit("content/journal/scripture.json is missing — run python3 scripts/fetch_scripture.py")


def originals(root):
    """ko originals (drafts excluded unless they are the sample) -> {slug: post}."""
    out = {}
    for f in sorted((root / "content/journal/ko").glob("*.md")):
        p = bj.parse_post(f)
        if not p["draft"]:
            out[p["slug"]] = p
    return out


def target_langs():
    """languages a ko original is translated into: every journal language except ko and the held ones."""
    return [l for l in LANGS if l != "ko" and l not in bj.HELD]


def path_of(root, lang, slug):
    return root / "content/journal" / lang / (slug + ".md")


def cmd_status(root, strict):
    orig = originals(root)
    langs = target_langs()
    missing = 0
    print("slug".ljust(40) + " ".join(l.ljust(3) for l in langs))
    for slug in orig:
        row = []
        for l in langs:
            ok = path_of(root, l, slug).is_file()
            missing += not ok
            row.append(("ok" if ok else "--").ljust(3))
        print(slug.ljust(40) + " ".join(row))
    held = ", ".join("%s (%s)" % (l, r) for l, r in bj.HELD.items())
    print("\nheld (not translated): %s" % (held or "none"))
    for l in langs:
        v = bj.SCRIPTURE["versions"].get(l, {})
        if v.get("mode") == "reference":
            print("reference only (no verse text): %s — %s" % (l, v.get("why", "")))
    print("missing translations: %d" % missing)
    return 1 if strict and missing else 0


def block_for(slug, lang, orig):
    p = orig.get(slug)
    if not p:
        raise SystemExit("no published ko original %s" % slug)
    key = bj.verse_key(p)
    if not key:
        return None, None
    want = bj.scripture_block(key, lang)
    if want is None:
        raise SystemExit("scripture.json has no %s text for %s — run python3 scripts/fetch_scripture.py" % (lang, key))
    return key, want


FRONT = ("title", "date", "slug", "lang", "description", "category", "keywords", "verse", "bible_version", "translation_of",
         "publish_at", "published_at", "draft")


def front_matter(p, lang, want):
    """the front matter a translation copies from its original (the rest — title, description, category, keywords — is translated)."""
    lines = ["title: (%s)" % LANGS[lang]["name"], "date: %s" % p["date"], "slug: %s" % p["slug"], "lang: %s" % lang,
             "description: (%s)" % LANGS[lang]["name"], "category: (%s)" % LANGS[lang]["name"]]
    if p.get("keywords"):
        lines.append("keywords: (%s, comma separated)" % LANGS[lang]["name"])
    if want and want[2]:
        lines.append("verse: %s" % want[2])
    lines.append("bible_version: %s" % (want[1] if want else "none"))
    lines.append("translation_of: ko")
    for k in ("publish_at", "published_at"):
        if p.get(k):
            lines.append("%s: %s" % (k, p[k]))
    return lines


RULES = """Rules (still() journal translation — read all of them):
- Translate the Korean original into a calm, natural {name} essay — how a native writer would tell the same story, not word for word.
  Keep every paragraph, the `##` subheadings, the closing `**...**` line and the first-person voice. Same length and structure, no new facts,
  no advice, no extra comfort lines, no prayer language, no claims about medicine. Local names for apps/streets/foods may stay generic.
- The front matter below is fixed: copy it exactly and only replace the parts in parentheses (title, description, category, keywords) with
  {name}. The description is one sentence; where the original names the verse, write the reference exactly as given below.
- SCRIPTURE (critical): never translate, retype or paraphrase a Bible verse. Put the quotation block below where the original has its
  `>` block, character for character. {echo}
- The page adds the safety notice, the crisis lines and the "AI translation" note by itself — do not write any of that.
- Write UTF-8, Unix newlines, the file must start with `---`."""
ECHO_TEXT = ("If the original echoes words of the verse in its prose (e.g. \"'가만히 있어'라는 말이…\"), quote only words that appear verbatim in the "
             "verse text below, exactly as written there; otherwise describe it without quoting.")
ECHO_REF = ("This language has no confirmed public-domain Bible text yet, so the block is the reference only. Where the original quotes or echoes "
            "words of the verse in its prose, do NOT quote any wording of the verse: refer to the verse by its reference or describe it in your "
            "own words without quotation marks (e.g. \"the verse told me to stop for a moment\").")


def cmd_brief(root, slug, langs):
    load(root)
    orig = originals(root)
    p = orig.get(slug)
    if not p:
        raise SystemExit("no published ko original %s (drafts are not translated)" % slug)
    src = path_of(root, "ko", slug).read_text(encoding="utf-8")
    out = ["# Translation brief — %s" % slug, "", "Original (Korean): content/journal/ko/%s.md" % slug, "", "```markdown", src.rstrip("\n"), "```", ""]
    for lang in langs or target_langs():
        key, want = block_for(slug, lang, orig)
        mode = bj.SCRIPTURE["versions"][lang]["mode"]
        out += ["## %s (%s) → content/journal/%s/%s.md" % (LANGS[lang]["name"], lang, lang, slug), "",
                RULES.format(name=LANGS[lang]["name"], echo=ECHO_TEXT if mode == "text" else ECHO_REF), "", "Front matter:", "```",
                "---"] + front_matter(p, lang, want) + ["---", "```", ""]
        if want:
            ref = bj.SCRIPTURE["verses"][key][lang]["ref"] + (" (%s)" % want[1] if mode == "text" else "")
            out += ["The verse reference in %s (use it in the description/prose where the original names the verse): %s" % (LANGS[lang]["name"], ref), "",
                    "Quotation block (%s, copy exactly):" % key, "```"] + want[0] + ["```", ""]
    print("\n".join(out))
    return 0


def quote_span(lines):
    """(start, end) of the first run of `>` lines, or None."""
    for i, l in enumerate(lines):
        if l.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            return i, j
    return None


def set_front(text, key, value):
    """set (or add before the closing ---) a front matter line."""
    end = text.index("\n---", 4)
    head, rest = text[:end], text[end:]
    pat = re.compile(r"(?m)^%s:.*$" % re.escape(key))
    if value is None:
        return pat.sub("", head).replace("\n\n", "\n") + rest
    if pat.search(head):
        return pat.sub("%s: %s" % (key, value), head, count=1) + rest
    return head + "\n%s: %s" % (key, value) + rest


def cmd_apply(root, slug=None, lang=None):
    load(root)
    orig = originals(root)
    changed, errs = 0, []
    for l in [lang] if lang else target_langs():
        for f in sorted((root / "content/journal" / l).glob("*.md")) if (root / "content/journal" / l).is_dir() else []:
            if slug and f.stem != slug or f.stem not in orig:
                continue
            text = f.read_text(encoding="utf-8")
            key, want = block_for(f.stem, l, orig)
            lines = text.split("\n")
            span = quote_span(lines)
            if not want:
                if span:
                    errs.append("%s: has a quotation block but the original has no verse" % f.relative_to(root))
                continue
            if not span:
                errs.append("%s: no quotation block (`>` lines) to fill — put `> verse` where the original has it" % f.relative_to(root))
                continue
            new = "\n".join(lines[:span[0]] + want[0] + lines[span[1]:])
            new = set_front(new, "bible_version", want[1])
            new = set_front(new, "verse", want[2])
            if new != text:
                f.write_text(new, encoding="utf-8")
                changed += 1
                print("updated %s" % f.relative_to(root))
    for e in errs:
        print("error: " + e, file=sys.stderr)
    print("apply: %d file(s) changed" % changed)
    return 1 if errs else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--strict", action="store_true")
    b = sub.add_parser("block")
    b.add_argument("slug")
    b.add_argument("lang")
    r = sub.add_parser("brief")
    r.add_argument("slug")
    r.add_argument("--lang", action="append")
    a = sub.add_parser("apply")
    a.add_argument("--slug")
    a.add_argument("--lang")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.cmd == "status":
        load(root)
        return cmd_status(root, args.strict)
    if args.cmd == "block":
        load(root)
        key, want = block_for(args.slug, args.lang, originals(root))
        print("\n".join(want[0]) if want else "(the original quotes no verse)")
        return 0
    if args.cmd == "brief":
        return cmd_brief(root, args.slug, args.lang)
    return cmd_apply(root, args.slug, args.lang)


if __name__ == "__main__":
    sys.exit(main())
