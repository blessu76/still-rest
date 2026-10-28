#!/usr/bin/env python3
"""Deploy scheduled journal posts on time — stdlib only (Python 3.8+). Runs on the Mac mini (launchd, every 5 minutes).

GitHub's own `schedule` cron can start hours late (2026-10-24: ~4h50m), so the Mac mini is the main trigger and the cron in
.github/workflows/deploy.yml is only a backup. This script:
  1. reads content/journal/*/*.md (the clone it lives in) for posts that are due: `publish_at` <= --now, not `draft`,
     and not older than --max-age-hours (long-published posts are not polled forever);
  2. GETs each live URL https://still.ipe.rest/journal/<lang>/<slug>/ (with a cache-busting query);
  3. if any answers 404 -> `gh workflow run deploy.yml -R blessu76/still-rest --ref main` ONCE, unless a deploy run is already
     queued / in progress or one was created less than --cooldown-min minutes ago (the 404 may be a cached one). A finished run
     created BEFORE the latest missing post's publish_at is ignored by the cooldown: it could not have included that post.

  python3 scripts/dispatch_due.py                      # --now = the real clock
  python3 scripts/dispatch_due.py --dry-run            # check and print, never start a run
  python3 scripts/dispatch_due.py --now "2026-10-26 10:43" --dry-run

Network errors / non-404 statuses never trigger a run (a site outage is not a missing post). Exit 0 unless the checks themselves failed.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pick_publish_time import front_matter  # noqa: E402
from site_common import KST, SITE, parse_when  # noqa: E402

REPO = "blessu76/still-rest"
WORKFLOW = "deploy.yml"
ACTIVE = ("in_progress", "queued", "waiting", "pending", "requested")


def due_posts(root, now, max_age_hours=72):
    """-> [(lang, slug, publish_at)] of scheduled, non-draft posts with now - max_age <= publish_at <= now."""
    out = []
    for f in sorted((Path(root) / "content" / "journal").glob("*/*.md")):
        if f.name.lower() == "readme.md":
            continue
        try:
            meta = front_matter(f)
            if not meta.get("publish_at") or meta.get("draft", "").lower() in ("true", "yes", "1"):
                continue
            when = parse_when(meta["publish_at"])
        except (OSError, ValueError):
            continue
        if when <= now and now - when <= dt.timedelta(hours=max_age_hours):
            out.append((f.parent.name, f.stem, when))
    return out


def live_url(lang, slug):
    return "%s/journal/%s/%s/" % (SITE, lang, slug)


def http_status(url, timeout=15):
    """HTTP status of a GET (cache-busted); None on a network error."""
    req = urllib.request.Request("%s?_=%d" % (url, int(time.time())), headers={"User-Agent": "still-dispatch/1", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as ex:
        return ex.code
    except (urllib.error.URLError, OSError):
        return None


def gh_runs(limit=10):
    """recent runs of the deploy workflow -> [{status, createdAt, ...}]. Raises RuntimeError when gh fails."""
    p = subprocess.run(["gh", "run", "list", "-R", REPO, "--workflow", WORKFLOW, "--limit", str(limit), "--json", "status,createdAt,event"],
                       capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("gh run list failed: %s" % p.stderr.strip()[:300])
    return json.loads(p.stdout or "[]")


def gh_dispatch():
    p = subprocess.run(["gh", "workflow", "run", WORKFLOW, "-R", REPO, "--ref", "main"], capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError("gh workflow run failed: %s" % p.stderr.strip()[:300])
    return p.stdout.strip()


def busy_reason(runs, now, cooldown_min, not_before=None):
    """why not to start another run: one is active, or one was created less than cooldown_min ago. None = free to go.
    not_before (aware datetime, the latest missing publish_at): a non-active run created before it could not have built the
    post, so it does not count for the cooldown (2026-10-28: an 11:15 push run held back an 11:23 post until 11:30).
    Active runs always block — we cannot tell when their build step reads the clock."""
    for r in runs:
        if r.get("status") in ACTIVE:
            return "a deploy run is already %s" % r["status"]
    for r in runs:
        try:
            created = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError):
            continue
        if not_before is not None and created < not_before:
            continue
        if dt.timedelta(0) <= now - created < dt.timedelta(minutes=cooldown_min):
            return "a deploy run was created %d min ago (cooldown %d min)" % ((now - created).total_seconds() // 60, cooldown_min)
    return None


def run(root, now, dry_run=False, max_age_hours=72, cooldown_min=10, status_fn=http_status, runs_fn=gh_runs, dispatch_fn=gh_dispatch, log=print):
    """-> exit code. status_fn / runs_fn / dispatch_fn are injectable (tests)."""
    due = due_posts(root, now, max_age_hours)
    log("now %s KST, %d due post file(s)" % (now.astimezone(KST).strftime("%Y-%m-%d %H:%M"), len(due)))
    missing = []
    for lang, slug, when in due:
        url = live_url(lang, slug)
        st = status_fn(url)
        log("  %s -> %s" % (url, st if st is not None else "network error"))
        if st == 404:
            missing.append((url, when))
    if not missing:
        log("nothing to deploy")
        return 0
    log("%d due post(s) not live yet" % len(missing))
    try:
        why = busy_reason(runs_fn(), now, cooldown_min, max(w for _, w in missing))
    except RuntimeError as ex:
        log("ERROR %s" % ex)
        return 1
    if why:
        log("skip: %s" % why)
        return 0
    if dry_run:
        log("dry-run: would run `gh workflow run %s -R %s --ref main`" % (WORKFLOW, REPO))
        return 0
    try:
        dispatch_fn()
    except RuntimeError as ex:
        log("ERROR %s" % ex)
        return 1
    log("dispatched %s" % WORKFLOW)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--now", default="now", help="`now` or `YYYY-MM-DD HH:MM` (KST) — which posts are due")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="site repo root (default: this repo)")
    ap.add_argument("--dry-run", action="store_true", help="check and print; never start a workflow run")
    ap.add_argument("--max-age-hours", type=int, default=72, help="ignore posts due longer ago than this (default 72)")
    ap.add_argument("--cooldown-min", type=int, default=10, help="no new run while the last one is younger than this (default 10)")
    a = ap.parse_args(argv)
    try:
        now = parse_when(a.now)
    except ValueError:
        print("--now must be `now` or `YYYY-MM-DD HH:MM` (KST): %r" % a.now, file=sys.stderr)
        return 2
    return run(a.root, now, a.dry_run, a.max_age_hours, a.cooldown_min)


if __name__ == "__main__":
    sys.exit(main())
