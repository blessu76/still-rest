import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import indexnow  # noqa: E402

KEY = "0123456789abcdef0123456789abcdef"
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url><loc>https://example.test/</loc>
    <xhtml:link rel="alternate" hreflang="ko" href="https://example.test/?lang=ko"/></url>
  <url><loc>https://example.test/a/</loc></url>
  <url><loc>https://example.test/a/</loc></url>
</urlset>
"""


class IndexNow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_find_key(self):
        (self.dir / "notes.txt").write_text("x\n")
        (self.dir / (KEY + ".txt")).write_text(KEY + "\n")
        self.assertEqual(indexnow.find_key(self.dir), KEY)

    def test_find_key_ignores_mismatch_and_long_names(self):
        (self.dir / (KEY + ".txt")).write_text("other\n")
        (self.dir / ("a" * 64 + ".txt")).write_text("a" * 64)
        with self.assertRaises(SystemExit):
            indexnow.find_key(self.dir)

    def test_sitemap_urls(self):
        (self.dir / "sitemap.xml").write_text(SITEMAP)
        self.assertEqual(indexnow.sitemap_urls(self.dir / "sitemap.xml"),
                         ["https://example.test/", "https://example.test/a/"])

    def test_payload(self):
        p = indexnow.build_payload(KEY, ["https://example.test/", "https://example.test/a/"])
        self.assertEqual(p["host"], "example.test")
        self.assertEqual(p["key"], KEY)
        self.assertEqual(p["keyLocation"], "https://example.test/%s.txt" % KEY)
        self.assertEqual(len(p["urlList"]), 2)

    def test_payload_rejects_empty_and_mixed_hosts(self):
        with self.assertRaises(SystemExit):
            indexnow.build_payload(KEY, [])
        with self.assertRaises(SystemExit):
            indexnow.build_payload(KEY, ["https://a.test/", "https://b.test/"])

    def test_dry_run_sends_nothing(self):
        (self.dir / "sitemap.xml").write_text(SITEMAP)
        (self.dir / (KEY + ".txt")).write_text(KEY)
        orig = indexnow.send
        indexnow.send = lambda *a, **k: self.fail("network call in dry-run")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(indexnow.main(["--root", str(self.dir), "--dry-run"]), 0)
        finally:
            indexnow.send = orig

    def test_repo_has_valid_key_and_sitemap(self):
        key = indexnow.find_key(ROOT)
        urls = indexnow.sitemap_urls(ROOT / "sitemap.xml")
        indexnow.build_payload(key, urls)


def sm(rows):
    """a sitemap from [(path, lastmod)] on https://still.test"""
    body = "".join("  <url><loc>https://still.test%s</loc>%s</url>\n" % (p, "<lastmod>%s</lastmod>" % d if d else "") for p, d in rows)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "</urlset>\n"


TODAY = "2026-10-30"
ENTRIES = [("https://still.test" + p, d) for p, d in [
    ("/", TODAY), ("/en/", TODAY), ("/journal/", TODAY), ("/journal/en/", TODAY), ("/journal/en/page/2/", TODAY),
    ("/journal/en/friday-morning/", TODAY), ("/journal/ko/friday-morning/", TODAY),
    ("/journal/en/old-one/", "2026-10-29"), ("/journal/en/future-one/", "2026-10-31"), ("/privacy/", "2026-10-25")]]


class ChangedUrls(unittest.TestCase):
    """P0-3: after a deploy only what changed is sent, and never a post that is not public yet"""

    def test_only_todays_lastmod_is_sent_and_the_sitemap_itself(self):
        urls = indexnow.changed_urls(ENTRIES, TODAY)
        self.assertEqual(urls, ["https://still.test/", "https://still.test/en/", "https://still.test/journal/", "https://still.test/journal/en/",
                                "https://still.test/journal/en/page/2/", "https://still.test/journal/en/friday-morning/",
                                "https://still.test/journal/ko/friday-morning/", "https://still.test/sitemap.xml"])

    def test_future_lastmod_is_never_sent(self):
        self.assertNotIn("https://still.test/journal/en/future-one/", indexnow.changed_urls(ENTRIES, TODAY))
        self.assertNotIn("https://still.test/journal/en/future-one/", indexnow.changed_urls(ENTRIES, TODAY, previous=[]))
        self.assertEqual(indexnow.changed_urls(ENTRIES, "2026-10-28"), [])  # a clock before everything: nothing is public that day

    def test_nothing_new_nothing_sent(self):
        self.assertEqual(indexnow.changed_urls(ENTRIES, TODAY, previous=list(ENTRIES)), [])  # the hourly backup run after the morning post
        self.assertEqual(indexnow.changed_urls([("https://still.test/", "2026-10-29")], TODAY), [])
        self.assertEqual(indexnow.changed_urls([], TODAY), [])

    def test_a_new_post_sends_it_with_every_list_and_home_page_of_the_day(self):
        before = [e for e in ENTRIES if "friday-morning" not in e[0]]  # live sitemap before the post opened (lists already had today's lastmod)
        urls = indexnow.changed_urls(ENTRIES, TODAY, previous=before)
        self.assertIn("https://still.test/journal/en/friday-morning/", urls)
        self.assertIn("https://still.test/journal/ko/friday-morning/", urls)
        for aggregate in ("/", "/en/", "/journal/", "/journal/en/", "/journal/en/page/2/"):  # a date-only lastmod did not move, the cards did
            self.assertIn("https://still.test" + aggregate, urls)
        self.assertNotIn("https://still.test/journal/en/old-one/", urls)
        self.assertEqual(urls[-1], "https://still.test/sitemap.xml")

    def test_a_post_already_live_is_not_resent_when_another_one_opens(self):
        before = [e for e in ENTRIES if "friday-morning" in e[0] or "future" in e[0]]
        later = ENTRIES + [("https://still.test/journal/en/friday-evening/", TODAY)]
        urls = indexnow.changed_urls(later, TODAY, previous=before + [e for e in later if e[0] == "https://still.test/"])
        self.assertIn("https://still.test/journal/en/friday-evening/", urls)
        self.assertNotIn("https://still.test/journal/en/friday-morning/", urls)

    def test_an_article_is_not_a_list(self):
        self.assertTrue(indexnow.ARTICLE_RE.match("/journal/ko/some-slug/"))
        for path in ("/journal/", "/journal/ko/", "/journal/page/2/", "/journal/ko/page/2/", "/ko/faq/"):
            self.assertFalse(indexnow.ARTICLE_RE.match(path), path)


class ChangedCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / (KEY + ".txt")).write_text(KEY)
        (self.dir / "sitemap.xml").write_text(sm([(p[len("https://still.test"):], d) for p, d in ENTRIES]))
        self.sent = []
        self.orig = indexnow.send
        indexnow.send = lambda payload, *a, **k: self.sent.append(payload) or 200
        self.addCleanup(lambda: setattr(indexnow, "send", self.orig))

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = indexnow.main(["--root", str(self.dir), *args])
        return code, out.getvalue()

    def test_scheduled_post_goes_out_at_its_own_run_only(self):
        # 10-29 evening run: the 10-30 post is not in the runner's sitemap yet (it is built only once due), so 10-29's URLs are all there is
        (self.dir / "sitemap.xml").write_text(sm([("/", "2026-10-29"), ("/journal/en/thu/", "2026-10-29")]))
        code, out = self.run_main("--changed", "--now", "2026-10-29 17:40")
        self.assertEqual(code, 0)
        self.assertEqual(self.sent[0]["urlList"], ["https://still.test/", "https://still.test/journal/en/thu/", "https://still.test/sitemap.xml"])
        # 10-30 10:06 run: sitemap now holds the new post -> it is sent, with the lists
        self.sent.clear()
        (self.dir / "sitemap.xml").write_text(sm([("/", TODAY), ("/journal/en/thu/", "2026-10-29"), ("/journal/en/fri/", TODAY)]))
        code, out = self.run_main("--changed", "--now", "2026-10-30 10:06")
        self.assertEqual(self.sent[0]["urlList"], ["https://still.test/", "https://still.test/journal/en/fri/", "https://still.test/sitemap.xml"])
        self.assertNotIn(KEY, out)  # the key never goes to the log

    def test_previous_sitemap_filters_and_a_missing_one_means_send_all(self):
        prev = self.dir / "prev.xml"
        prev.write_text(sm([(p[len("https://still.test"):], d) for p, d in ENTRIES]))
        code, out = self.run_main("--changed", "--now", TODAY + " 10:06", "--previous", str(prev))
        self.assertEqual((code, self.sent), (0, []))
        self.assertIn("nothing", out)
        code, out = self.run_main("--changed", "--now", TODAY + " 10:06", "--previous", str(self.dir / "does-not-exist.xml"))
        self.assertEqual(code, 0)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("previous sitemap unknown", out)

    def test_dry_run_prints_and_sends_nothing(self):
        code, out = self.run_main("--changed", "--now", TODAY + " 10:06", "--dry-run")
        self.assertEqual((code, self.sent), (0, []))
        self.assertIn('"urlList"', out)

    def test_changed_rejects_explicit_urls(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_main("--changed", "https://still.test/")


class Retry(unittest.TestCase):
    def test_403_and_5xx_are_retried_then_given_up(self):
        calls, sleeps = [], []
        orig = indexnow._post
        try:
            for statuses, want_calls, want in (([403, 403, 202], 3, 202), ([200], 1, 200), ([422], 1, 422), ([503, 503, 503, 200], 3, 503), ([0, 200], 2, 200)):
                calls.clear()
                seq = iter(statuses)
                indexnow._post = lambda *a, **k: calls.append(1) or next(seq)
                self.assertEqual(indexnow.send({}, sleep=sleeps.append), want, statuses)
                self.assertEqual(len(calls), want_calls, statuses)
        finally:
            indexnow._post = orig
        self.assertTrue(sleeps)


class DeployWorkflow(unittest.TestCase):
    """the deploy workflow calls IndexNow after the deploy, never lets it fail the deploy, and uses the build's clock"""

    @classmethod
    def setUpClass(cls):
        cls.wf = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        cls.steps = re.split(r"\n      - name: ", cls.wf)[1:]

    def step(self, start):
        return next(s for s in self.steps if s.startswith(start))

    def test_indexnow_runs_after_deploy_and_before_the_slack_notices(self):
        names = [s.split("\n", 1)[0] for s in self.steps]
        i = next(n for n, name in enumerate(names) if name.startswith("IndexNow"))
        self.assertEqual(names[i - 1], "Deploy")
        self.assertTrue(names[i + 1].startswith("Notify Slack"))

    def test_indexnow_failure_keeps_the_deploy(self):
        s = self.step("IndexNow")
        self.assertIn("continue-on-error: true", s)
        self.assertNotIn("if:", s.split("run:")[0].replace("# ", ""))  # default if: success() -> never runs when the deploy failed
        self.assertIn("scripts/indexnow.py --changed", s)
        self.assertIn('--now "$PUBLISH_NOW"', s)
        self.assertIn("--previous", s)

    def test_clock_is_shared_with_the_build(self):
        build = self.step("Publish scheduled posts")
        self.assertIn('echo "PUBLISH_NOW=$NOW" >> "$GITHUB_ENV"', build)
        self.assertIn('build_journal.py --now "$NOW"', build)

    def test_live_sitemap_is_saved_before_the_deploy_replaces_it(self):
        names = [s.split("\n", 1)[0] for s in self.steps]
        snap = next(n for n, name in enumerate(names) if name.startswith("Remember the sitemap"))
        self.assertLess(snap, names.index("Deploy"))
        self.assertIn("continue-on-error: true", self.steps[snap])

    def test_no_secret_in_the_indexnow_step_and_the_key_file_is_public(self):
        self.assertNotIn("secrets.", self.step("IndexNow"))
        key = indexnow.find_key(ROOT)
        self.assertTrue((ROOT / (key + ".txt")).is_file())
        self.assertNotIn("/" + key, self.wf)  # nothing spells the key out in the workflow


if __name__ == "__main__":
    unittest.main()
