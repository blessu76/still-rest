"""Tests for scripts/dispatch_due.py — network and gh are injected. Run: python3 -m unittest discover -s tests"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import dispatch_due as dd  # noqa: E402
from site_common import KST  # noqa: E402


def post(root, lang, slug, extra):
    d = Path(root) / "content/journal" / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / (slug + ".md")).write_text("---\ntitle: T\ndate: 2026-10-26\nslug: %s\nlang: %s\ndescription: d\ncategory: c\n%s\n---\n\nbody\n" % (slug, lang, extra), encoding="utf-8")


def at(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST)


class DueTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = self._t.name
        post(self.root, "ko", "due", "publish_at: 2026-10-26 10:43")
        post(self.root, "en", "due", "publish_at: 2026-10-26 10:43")
        post(self.root, "ko", "later", "publish_at: 2026-10-26 16:28")
        post(self.root, "ko", "draft", "publish_at: 2026-10-26 10:00\ndraft: true")
        post(self.root, "ko", "public", "published_at: 2026-10-26 09:10")
        post(self.root, "ko", "old", "publish_at: 2026-10-20 11:00")
        self.log = []

    def tearDown(self):
        self._t.cleanup()

    def go(self, now, status, runs=(), dry=False):
        calls = []
        code = dd.run(self.root, at(now), dry, status_fn=status, runs_fn=lambda: list(runs), dispatch_fn=lambda: calls.append(1), log=self.log.append)
        return code, calls

    def test_due_posts_filters(self):
        got = sorted((l, s) for l, s, _ in dd.due_posts(self.root, at("2026-10-26 11:00")))
        self.assertEqual(got, [("en", "due"), ("ko", "due")])  # not later / draft / published_at / older than 72 h

    def test_live_url(self):
        self.assertEqual(dd.live_url("ko", "x"), "https://still.ipe.rest/journal/ko/x/")

    def test_404_dispatches_once(self):
        code, calls = self.go("2026-10-26 11:00", lambda u: 404)
        self.assertEqual((code, len(calls)), (0, 1))

    def test_all_live_does_nothing(self):
        code, calls = self.go("2026-10-26 11:00", lambda u: 200)
        self.assertEqual((code, calls), (0, []))

    def test_network_error_or_500_does_not_dispatch(self):
        for st in (None, 500):
            self.assertEqual(self.go("2026-10-26 11:00", lambda u: st)[1], [])

    def test_one_404_among_many_is_enough(self):
        code, calls = self.go("2026-10-26 11:00", lambda u: 404 if "/en/" in u else 200)
        self.assertEqual(len(calls), 1)

    def test_nothing_due_checks_nothing(self):
        seen = []
        code, calls = self.go("2026-10-26 10:00", lambda u: seen.append(u) or 404)
        self.assertEqual((seen, calls), ([], []))

    def test_active_run_blocks(self):
        for status in ("in_progress", "queued"):
            code, calls = self.go("2026-10-26 11:00", lambda u: 404, [{"status": status, "createdAt": "2026-10-26T00:00:00Z"}])
            self.assertEqual(calls, [], status)

    def test_cooldown_blocks_recent_run(self):
        # 11:00 KST = 02:00 UTC; run created 02:55 -> 5 min before 11:00?? use 01:55Z = 10:55 KST
        runs = [{"status": "completed", "createdAt": "2026-10-26T01:55:00Z"}]
        self.assertEqual(self.go("2026-10-26 11:00", lambda u: 404, runs)[1], [])
        runs = [{"status": "completed", "createdAt": "2026-10-26T01:40:00Z"}]
        self.assertEqual(len(self.go("2026-10-26 11:00", lambda u: 404, runs)[1]), 1)

    def test_dry_run_never_dispatches(self):
        code, calls = self.go("2026-10-26 11:00", lambda u: 404, dry=True)
        self.assertEqual((code, calls), (0, []))
        self.assertTrue(any("dry-run" in l for l in self.log))

    def test_gh_failure_exit_1(self):
        def boom():
            raise RuntimeError("no auth")
        self.assertEqual(dd.run(self.root, at("2026-10-26 11:00"), False, status_fn=lambda u: 404, runs_fn=boom, dispatch_fn=lambda: None, log=self.log.append), 1)


if __name__ == "__main__":
    unittest.main()
