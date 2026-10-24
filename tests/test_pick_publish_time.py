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
    def test_always_inside_window_and_never_round(self):
        with tempfile.TemporaryDirectory() as root:
            for slot, (lo, hi) in ppt.WINDOWS.items():
                for seed in range(300):
                    out = ppt.pick(DAY, slot, root, rng=random.Random(seed))
                    self.assertRegex(out, r"^2026-10-26 \d\d:\d\d$")
                    m = minutes(out)
                    self.assertTrue(lo <= m <= hi, out)
                    self.assertNotIn(m % 60, (0, 30), out)

    def test_windows_are_09_to_1159_and_16_to_1759(self):
        self.assertEqual(ppt.WINDOWS["am"], (540, 719))
        self.assertEqual(ppt.WINDOWS["pm"], (960, 1079))

    def test_seed_is_deterministic(self):
        with tempfile.TemporaryDirectory() as root:
            a = ppt.pick(DAY, "am", root, rng=random.Random(7))
            b = ppt.pick(DAY, "am", root, rng=random.Random(7))
            self.assertEqual(a, b)

    def test_keeps_15_minutes_from_same_slot_yesterday(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, "ko", "a", "publish_at: 2026-10-25 11:17")
            post(root, "ko", "b", "publish_at: 2026-10-25 16:28")
            for seed in range(400):
                self.assertGreaterEqual(abs(minutes(ppt.pick(DAY, "am", root, rng=random.Random(seed))) - (11 * 60 + 17)), 15)
                self.assertGreaterEqual(abs(minutes(ppt.pick(DAY, "pm", root, rng=random.Random(seed))) - (16 * 60 + 28)), 15)

    def test_published_at_counts_and_other_slot_is_ignored(self):
        with tempfile.TemporaryDirectory() as root:
            post(root, "ko", "a", "published_at: 2026-10-25 09:10")
            # yesterday's pm time must not constrain the am slot: forbid nothing around it
            self.assertEqual(ppt.times_on(root, dt.date(2026, 10, 25)), [550])
            cands = ppt.candidates("am", 550)
            self.assertNotIn(550, cands)
            self.assertNotIn(536 + 14, cands)  # 09:10 +- 14
            self.assertIn(565, cands)  # 09:25 is 15 away
            self.assertNotIn(564, cands)  # 09:24 is 14 away

    def test_other_days_ignored_and_missing_ok(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ppt.times_on(root, DAY), [])
            post(root, "ko", "a", "publish_at: 2026-10-20 10:00")
            self.assertEqual(ppt.times_on(root, dt.date(2026, 10, 25)), [])

    def test_not_before(self):
        with tempfile.TemporaryDirectory() as root:
            for seed in range(200):
                self.assertGreaterEqual(minutes(ppt.pick(DAY, "pm", root, not_before=17 * 60 + 40, rng=random.Random(seed))), 17 * 60 + 40)
            self.assertEqual(ppt.pick(DAY, "pm", root, not_before=17 * 60 + 59), "2026-10-26 17:59")  # the last minute is still allowed
            with self.assertRaises(ValueError):
                ppt.pick(DAY, "pm", root, not_before=18 * 60)

    def test_bad_slot(self):
        with self.assertRaises(ValueError):
            ppt.pick(DAY, "noon", ".")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as root, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ppt.main(["2026-10-26", "am", "--root", root, "--seed", "1"]), 0)
            self.assertEqual(ppt.main(["2026-10-26", "pm", "--root", root, "--not-before", "18:00"]), 1)


if __name__ == "__main__":
    unittest.main()
