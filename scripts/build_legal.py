#!/usr/bin/env python3
"""Build the still.ipe.rest legal pages (/privacy/, /terms/) from the common canonical text — stdlib only (Python 3.8+).

Source   content/legal/privacy.{en,ko}.md, terms.{en,ko}.md   copies of the ipe() canonical text (_ipe/site/legal/)
Writes   privacy/index.html, terms/index.html   the body between <!-- legal:start --> / <!-- legal:end -->
         (head, GA4 block, language toggle and footer are hand-written and left alone; scripts/build_info.py syncs the GA4 block)

The canonical text is copied, not edited: {시행일}, [확인 필요: …] and [confirm: …] stay as written until Quill settles them.

    python3 scripts/build_legal.py           # rewrite the two pages
    python3 scripts/build_legal.py --check   # exit 1 if the committed pages differ from a fresh build
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "content" / "legal"
PAGES = ("privacy", "terms")
START, END = "<!-- legal:start -->", "<!-- legal:end -->"
LANG_BLOCKS = (("en", "en"), ("ko", "ko"))

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,4}) (.*)$")
_UL = re.compile(r"^[-*] (.*)$")
_OL = re.compile(r"^\d+\. (.*)$")
_HR = re.compile(r"^-{3,}$")
_SEP_CELL = re.compile(r"^:?-{3,}:?$")


def inline(text):
    text = html.escape(text, quote=False)
    codes = []
    text = _CODE.sub(lambda m: codes.append(m.group(1)) or "\x00%d\x00" % (len(codes) - 1), text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _LINK.sub(r'<a href="\2">\1</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: "<code>%s</code>" % codes[int(m.group(1))], text)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html(md):
    lines = md.splitlines()
    out, para, items, kind = [], [], [], None
    seen_title = False

    def close():
        nonlocal kind
        if para:
            out.append("<p>%s</p>" % inline(" ".join(para)))
            para.clear()
        if items:
            out.append("<%s>\n%s\n</%s>" % (kind, "\n".join("<li>%s</li>" % inline(t) for t in items), kind))
            items.clear()
            kind = None

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            close()
        elif _HEADING.match(s):
            close()
            m = _HEADING.match(s)
            if len(m.group(1)) == 1 and not seen_title:
                seen_title = True  # the page has its own <h1>
            else:
                level = 2 if len(m.group(1)) <= 2 else 3
                out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
        elif s.startswith("|"):
            close()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            i -= 1
            head, body = rows[0], [r for r in rows[1:] if not all(_SEP_CELL.match(c) for c in r)]
            t = ["<div class=\"tblwrap\"><table>", "<thead><tr>%s</tr></thead>" % "".join("<th>%s</th>" % inline(c) for c in head), "<tbody>"]
            t += ["<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in body]
            t += ["</tbody>", "</table></div>"]
            out.append("\n".join(t))
        elif s.startswith(">"):
            close()
            quoted = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q = lines[i].strip()[1:].strip()
                if q:
                    quoted.append("<p>%s</p>" % inline(q))
                i += 1
            i -= 1
            out.append("<blockquote>\n%s\n</blockquote>" % "\n".join(quoted))
        elif _HR.match(s):
            close()
            out.append("<hr>")
        elif _UL.match(s) or _OL.match(s):
            want = "ul" if _UL.match(s) else "ol"
            if para or kind != want:
                close()
                kind = want
            items.append((_UL if want == "ul" else _OL).match(s).group(1))
        elif items and line[:1] in (" ", "\t"):
            items[-1] += " " + s
        else:
            if items:
                close()
            para.append(s)
        i += 1
    close()
    return "\n".join(out)


def body_for(page):
    blocks = []
    for lang, _ in LANG_BLOCKS:
        md = (SOURCE_DIR / ("%s.%s.md" % (page, lang))).read_text(encoding="utf-8")
        cls = ' class="on"' if lang == "en" else ""
        blocks.append('    <div data-lang-block="%s"%s>\n%s\n    </div>' % (lang, cls, md_to_html(md)))
    return "\n".join(blocks)


def rebuild(text, body):
    i, j = text.find(START), text.find(END)
    if i == -1 or j == -1 or j < i or text.count(START) != 1 or text.count(END) != 1:
        raise SystemExit("legal markers missing or broken")
    return text[:i] + START + "\n" + body + "\n    " + text[j:]


def main(argv):
    check = "--check" in argv
    stale = []
    for page in PAGES:
        path = ROOT / page / "index.html"
        text = path.read_text(encoding="utf-8")
        new = rebuild(text, body_for(page))
        if new != text:
            stale.append(page)
            if not check:
                path.write_text(new, encoding="utf-8")
    if check and stale:
        print("stale: %s — run python3 scripts/build_legal.py" % ", ".join(stale))
        return 1
    print("ok" if check else "built: %s" % ", ".join(PAGES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
