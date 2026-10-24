#!/usr/bin/env python3
"""Pick a random KST publish time for a still() journal post — stdlib only (Python 3.8+).

  python3 scripts/pick_publish_time.py 2026-10-26 am      # -> 2026-10-26 10:43
  python3 scripts/pick_publish_time.py 2026-10-26 pm --not-before 16:40

Slots (KST): am = 09:00-11:59, pm = 16:00-17:59. Output = `YYYY-MM-DD HH:MM`, ready for the `publish_at:` front matter line.
Rules: never on :00 or :30 (round numbers look scheduled), and at least 15 minutes away (time of day) from the time the SAME
slot had on the previous day, found in content/journal/*/*.md (`publish_at` / `published_at`; none found -> no constraint).
`--not-before HH:MM` = the post is prepared late today, pick at or after that time. Exit 1 when no time is left.
"""
import argparse
import datetime as dt
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_common import KST, parse_when  # noqa: E402

WINDOWS = {"am": (9 * 60, 11 * 60 + 59), "pm": (16 * 60, 17 * 60 + 59)}  # minutes of the day, inclusive
MIN_GAP = 15  # minutes from the same slot's time on the previous day
AVOID_MINUTES = (0, 30)


def slot_of(minute):
    """which slot a time of day (minutes) belongs to: am before 12:00, pm from 12:00."""
    return "am" if minute < 12 * 60 else "pm"


def front_matter(path):
    """-> dict of the `key: value` lines of a post's front matter (comments and blanks skipped); {} when there is none."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    meta = {}
    for line in text[4:end].split("\n"):
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        v = re.sub(r"\s+#.*$", "", v.strip())  # trailing comment
        meta[k.strip().lower()] = v.strip().strip("\"'")
    return meta


def times_on(root, day):
    """all post times (minutes of the day, KST) on `day` (date) from publish_at / published_at in content/journal/*/*.md."""
    out = []
    for f in sorted((Path(root) / "content" / "journal").glob("*/*.md")):
        try:
            meta = front_matter(f)
            raw = meta.get("publish_at") or meta.get("published_at")
            if not raw:
                continue
            when = parse_when(raw).astimezone(KST)
        except (OSError, ValueError):
            continue
        if when.date() == day:
            out.append(when.hour * 60 + when.minute)
    return out


def candidates(slot, previous=None, not_before=None):
    """every allowed minute of the day for the slot, ascending."""
    lo, hi = WINDOWS[slot]
    if not_before is not None:
        lo = max(lo, not_before)
    return [m for m in range(lo, hi + 1)
            if m % 60 not in AVOID_MINUTES and (previous is None or abs(m - previous) >= MIN_GAP)]


def pick(day, slot, root=".", not_before=None, rng=None):
    """-> `YYYY-MM-DD HH:MM`. day = datetime.date. rng = random.Random (inject a seeded one in tests). Raises ValueError when nothing is allowed."""
    if slot not in WINDOWS:
        raise ValueError("slot must be am or pm: %r" % slot)
    rng = rng or random.SystemRandom()
    prev = [m for m in times_on(root, day - dt.timedelta(days=1)) if slot_of(m) == slot]
    pool = candidates(slot, prev[0] if prev else None, not_before)
    if not pool:
        raise ValueError("no allowed time left in the %s window (not-before=%s)" % (slot, not_before))
    m = rng.choice(pool)
    return "%s %02d:%02d" % (day.isoformat(), m // 60, m % 60)


def parse_hhmm(s):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise argparse.ArgumentTypeError("HH:MM expected: %r" % s)
    return int(m.group(1)) * 60 + int(m.group(2))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date", help="publication date YYYY-MM-DD (KST)")
    ap.add_argument("slot", choices=sorted(WINDOWS), help="am = 09:00-11:59, pm = 16:00-17:59")
    ap.add_argument("--not-before", type=parse_hhmm, metavar="HH:MM", help="pick at or after this time of day (post prepared late)")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="site repo root (default: this repo)")
    ap.add_argument("--seed", type=int, help="fixed random seed (tests/debugging)")
    a = ap.parse_args(argv)
    try:
        day = dt.date.fromisoformat(a.date)
        print(pick(day, a.slot, a.root, a.not_before, random.Random(a.seed) if a.seed is not None else None))
    except ValueError as ex:
        print("pick_publish_time: %s" % ex, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
