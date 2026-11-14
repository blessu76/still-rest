"""Tests for scripts/pick_publish_time.py — run: python3 -m unittest discover -s tests"""
import contextlib
import datetime as dt
import io
import random
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import pick_publish_time as ppt  # noqa: E402

DAY = dt.date(2026, 10, 26)


def post(root, lang, slug, when_line):
    d = Path(root) / "content/journal" / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / (slug + ".md")).write_text("---\ntitle: T\ndate: %s\nslug: %s\nlang: %s\ndescription: d\ncategory: c\n%s\n---\n\nbody\n" % (when_line[-16:-6], slug, lang, when_line), encoding="utf-8")


def minutes(s):
    return int(s[11:13]) * 60 + int(s[14:16])


class PickTests(unittest.TestCase):
    def test_window_is_12_to_1759(self):
        self.assertEqual(ppt.WINDOW, (720, 1079))

    def test_always_inside_window_and_never_round(self):
        with tempfile.TemporaryDirectory() as root:
            for seed in range(300):
                out = ppt.pick(DAY, root, rng=random.Random(seed))
                self.assertRegex(out, r"^2026-10-26 \d\d:\d\d$")
                m = minutes(out)
                self.assertTrue(720 <= m <= 1079, out)
                self.assertNotIn(m % 60, (0, 30), out)

    def test_seed_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ppt.pick(DAY, root, rng=random.Random(7)), ppt.pick(DAY, root, rng=random.Random(7)))

    def test_avoids_yesterdays_clock_hour_only(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, "ko", "a", "publish_at: 2026-10-25 13:17")
            post(root, "en", "a", "publish_at: 2026-10-25 13:17")
            for seed in range(400):
                m = minutes(ppt.pick(DAY, root, rng=random.Random(seed)))
                self.assertNotEqual(m // 60, 13, m)
            self.assertNotIn(13 * 60 + 45, ppt.candidates({13}))
            self.assertIn(14 * 60 + 5, ppt.candidates({13}))

    def test_published_at_counts_for_yesterday(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, "ko", "a", "published_at: 2026-10-25 17:10")
            self.assertEqual(ppt.times_on(root, dt.date(2026, 10, 25)), [17 * 60 + 10])
            self.assertNotIn(17 * 60 + 40, ppt.candidates({17}))
            self.assertIn(16 * 60 + 40, ppt.candidates({17}))

    def test_refuses_a_day_that_already_has_a_post(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, "ko", "a", "publish_at: 2026-10-26 12:20")
            with self.assertRaises(ValueError):
                ppt.pick(DAY, root)

    def test_other_days_ignored_and_missing_ok(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ppt.times_on(root, DAY), [])
            post(root, "ko", "a", "publish_at: 2026-10-20 10:00")
            self.assertEqual(ppt.times_on(root, dt.date(2026, 10, 25)), [])

    def test_not_before(self):
        with tempfile.TemporaryDirectory() as root:
            for seed in range(200):
                self.assertGreaterEqual(minutes(ppt.pick(DAY, root, not_before=17 * 60 + 40, rng=random.Random(seed))), 17 * 60 + 40)
            self.assertEqual(ppt.candidates(not_before=17 * 60 + 59), [17 * 60 + 59])
            with self.assertRaises(ValueError):
                ppt.pick(DAY, root, not_before=18 * 60)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ppt.main(["2026-10-26", "--root", root, "--seed", "1"]), 0)
            self.assertEqual(ppt.main(["2026-10-26", "--root", root, "--not-before", "18:00"]), 1)


if __name__ == "__main__":
    unittest.main()
