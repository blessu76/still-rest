"""ipe-localtime v2: a byte-identical copy, inlined once (right before </body>) into every page that has a <time data-ipe-time> — nowhere else"""
import hashlib
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
from test_build_journal import POST, Base, run, write_post  # noqa: E402

JS = REPO / "scripts/ipe-localtime.js"
SHA256 = "57326449ddf5050eabadd1394d69eb2b0f61c88f084ec83ee4aff6fcad0f74b8"
CSP_HASH = "sha256-VzJkSd31BQ6rrdE5TWnrKw9hyI8ITsg+5K/2/K0PdLg="  # only needed if a Content-Security-Policy is ever added (none today)
TIME = re.compile(r"<time ([^>]*)>([^<]*)</time>")  # text only inside: no child tags


def inlined():
    return "<script>" + JS.read_bytes().decode("utf-8") + "</script>"


def post(slug, extra):
    return POST.replace("slug: hello", "slug: " + slug).replace("2026-10-22", "2026-10-24") % dict(l="ko", extra="bible_version: WEB\n" + extra)


class Copy(unittest.TestCase):
    def test_copy_is_the_v2_original(self):
        data = JS.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), SHA256)
        self.assertEqual(len(data), 1639)
        self.assertTrue(data.endswith(b"\n"))
        self.assertIn(b"ipe-localtime v2", data)

    def test_no_csp_so_nothing_to_allow(self):
        # the site has no Content-Security-Policy (no meta, no _headers). If one is added, script-src must carry CSP_HASH.
        self.assertFalse((REPO / "_headers").exists())
        for f in [REPO / "index.html", REPO / "privacy/index.html", *REPO.glob("journal/**/index.html")]:
            self.assertNotIn("content-security-policy", f.read_text(encoding="utf-8").lower(), f)


class Pages(Base):
    """a timed post and a date-only post (ko)"""

    def setUp(self):
        super().setUp()
        write_post(self.tmp, "ko", "timed", text=post("timed", "published_at: 2026-10-24 09:09\n"))
        write_post(self.tmp, "ko", "dated", text=post("dated", ""))
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def script_once_before_body_end(self, rel):
        h = self.page(rel)
        self.assertEqual(h.count(inlined()), 1, rel)
        self.assertEqual(h.count("ipe-localtime v2"), 1, rel)
        self.assertTrue(h.endswith(inlined() + "\n</body>\n</html>\n"), rel)
        self.assertNotRegex(h, r"<script[^>]+ipe-localtime", rel)  # inline, never an external src

    def test_timed_post_list_and_home_carry_the_script_once(self):
        for rel in ("journal/ko/timed/index.html", "journal/ko/index.html", "journal/index.html", "ko/index.html", "index.html"):
            self.script_once_before_body_end(rel)

    def test_time_markup(self):
        for rel in ("journal/ko/timed/index.html", "journal/ko/index.html", "ko/index.html"):
            times = [m for m in TIME.finditer(self.page(rel)) if "data-ipe-time" in m.group(1)]
            self.assertTrue(times, rel)
            for m in times:
                self.assertEqual(m.group(1), 'datetime="2026-10-24T09:09:00+09:00" data-ipe-time', rel)
                self.assertEqual(m.group(2), "2026년 10월 24일&nbsp;09:09 KST", rel)

    def test_date_only_post_has_a_plain_time_and_no_script(self):
        h = self.page("journal/ko/dated/index.html")
        self.assertIn('<time datetime="2026-10-24">2026년 10월 24일</time>', h)
        self.assertNotIn("data-ipe-time", h)
        self.assertNotIn("ipe-localtime", h)

    def test_pages_without_a_timed_time_have_no_script(self):
        for rel in ("ko/faq/index.html", "ko/about/index.html"):
            self.assertNotIn("ipe-localtime", self.page(rel), rel)
        (self.tmp / "content/journal/ko/timed.md").unlink()  # only the date-only post is left: no page needs the script
        self.assertEqual(run(self.tmp).returncode, 0)
        for rel in ("journal/ko/index.html", "journal/index.html", "ko/index.html", "index.html", "journal/ko/dated/index.html"):
            self.assertNotIn("ipe-localtime", self.page(rel), rel)

    def test_safety_block_has_no_time_markup(self):
        h = self.page("journal/ko/timed/index.html")
        i = h.index('data-safety="block"')
        self.assertNotIn("data-ipe-time", h[i:h.index("</section>", i)])


class Committed(unittest.TestCase):
    """the committed pages (what is deployed): a page with a timed <time> has the script exactly once, before </body>; every other page has none"""

    def test_committed_pages(self):
        timed = 0
        for f in REPO.glob("**/index.html"):
            if any(part in (".git", "content", "scripts", "tests") for part in f.relative_to(REPO).parts):
                continue
            h = f.read_text(encoding="utf-8")
            marks = [m for m in TIME.finditer(h) if "data-ipe-time" in m.group(1)]
            if marks:
                timed += 1
                self.assertEqual(h.count(inlined()), 1, f)
                self.assertTrue(h.endswith(inlined() + "\n</body>\n</html>\n"), f)
                for m in marks:
                    self.assertRegex(m.group(1), r'^datetime="\d{4}-\d\d-\d\dT\d\d:\d\d:00\+09:00" data-ipe-time$', f)
                    self.assertRegex(m.group(2), r"&nbsp;\d\d:\d\d KST$", f)
            else:
                self.assertNotIn("ipe-localtime", h, f)
        self.assertGreater(timed, 0)


if __name__ == "__main__":
    unittest.main()
