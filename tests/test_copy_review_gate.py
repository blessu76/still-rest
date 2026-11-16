"""Copy-review publish gate (Matt·w00 2026-11-14): an ORIGINAL post dated after 2026-11-14 needs `copy_review: iris YYYY-MM-DD` in its front matter,
or the build fails (CI deploy + `check.sh`) and `dispatch_due` does not dispatch for it. Posts dated on/before 11-14 are legacy and exempt;
translations follow their original. Run: python3 -m unittest discover -s tests"""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import dispatch_due as dd  # noqa: E402
from site_common import KST, copy_review_missing  # noqa: E402
from test_build_journal import Base, run  # noqa: E402
from test_publish_lint import post  # noqa: E402

NOW = "2026-11-20 12:00"


class Helper(unittest.TestCase):
    def test_rules(self):
        self.assertFalse(copy_review_missing({"date": "2026-11-14"}))  # legacy day
        self.assertTrue(copy_review_missing({"date": "2026-11-15"}))
        self.assertTrue(copy_review_missing({"date": "2026-11-15", "copy_review": ""}))
        self.assertTrue(copy_review_missing({"date": "2026-11-15", "copy_review": "iris"}))  # no date
        self.assertTrue(copy_review_missing({"date": "2026-11-15", "copy_review": "dane 2026-11-15"}))  # not Iris
        self.assertFalse(copy_review_missing({"date": "2026-11-15", "copy_review": "iris 2026-11-15"}))
        self.assertFalse(copy_review_missing({"date": "2026-11-15", "translation_of": "ko"}))  # a translation rides on its original


class BuildGate(Base):
    def test_unreviewed_new_post_blocks_the_build(self):
        post(self.tmp, lang="ko", slug="no-review", date="2026-11-18")
        r = run(self.tmp, "--now", NOW)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("copy_review", r.stdout + r.stderr)
        self.assertIn("no-review", r.stdout + r.stderr)

    def test_unreviewed_scheduled_post_blocks_too(self):
        post(self.tmp, lang="ko", slug="sched", date="2026-11-18", extra="publish_at: 2026-11-18 17:00\n")
        self.assertNotEqual(run(self.tmp, "--now", NOW).returncode, 0)

    def test_reviewed_post_passes(self):
        post(self.tmp, lang="ko", slug="ok", date="2026-11-18", extra="copy_review: iris 2026-11-17\n")
        self.assertEqual(run(self.tmp, "--now", NOW).returncode, 0)

    def test_legacy_dated_post_passes_without_review(self):
        post(self.tmp, lang="ko", slug="legacy", date="2026-11-14")
        self.assertEqual(run(self.tmp, "--now", NOW).returncode, 0)

    def test_draft_is_not_gated(self):
        post(self.tmp, lang="ko", slug="d", date="2026-11-18", extra="draft: true\n")
        self.assertEqual(run(self.tmp, "--now", NOW).returncode, 0)


class DispatchGate(unittest.TestCase):
    def test_dispatcher_ignores_an_unreviewed_due_post(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, lang="ko", slug="un", date="2026-11-18", extra="publish_at: 2026-11-18 10:00\n")
            post(root, lang="ko", slug="rv", date="2026-11-18", extra="publish_at: 2026-11-18 10:00\ncopy_review: iris 2026-11-17\n")
            now = dt.datetime(2026, 11, 18, 11, 0, tzinfo=KST)
            self.assertEqual([s for _, s, _ in dd.due_posts(root, now)], ["rv"])


if __name__ == "__main__":
    unittest.main()
