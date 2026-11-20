#!/bin/bash
# still.ipe.rest journal dispatcher wrapper — template copy; the live one is ~/.ipe/bin/still_dispatch.sh (see README.md here).
# launchd calls this every 5 minutes. Outside the publish window (KST 12:00-18:40) it exits at once.
# Inside: refresh a dedicated read-only clone, then run scripts/dispatch_due.py (404 on a due post -> one `gh workflow run deploy.yml`).
# Pass --dry-run through to only look: ~/.ipe/bin/still_dispatch.sh --dry-run   (the window check is skipped with STILL_DISPATCH_ANYTIME=1)
set -u
HM="$(TZ=Asia/Seoul date +%H%M)"
HM=$((10#$HM))
in_window() { [ "$HM" -ge 1200 ] && [ "$HM" -le 1840 ]; }
if [ "${STILL_DISPATCH_ANYTIME:-0}" != "1" ] && ! in_window; then exit 0; fi

CLONE="${STILL_DISPATCH_CLONE:-$HOME/.ipe/still-rest-dispatch}"
REMOTE="https://github.com/blessu76/still-rest.git"
echo "=== $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S') KST dispatch tick"
if [ ! -d "$CLONE/.git" ]; then
  git clone --quiet "$REMOTE" "$CLONE" || { echo "ERROR clone failed"; exit 1; }
fi
git -C "$CLONE" pull --ff-only --quiet || { echo "ERROR git pull --ff-only failed"; exit 1; }
[ -f "$CLONE/scripts/dispatch_due.py" ] || { echo "dispatch_due.py is not in the clone yet (not pushed to main?) - nothing to do"; exit 0; }
# The clone has only vendor/ipe_web_kit.lock (the kit is private, never committed): install the locked kit from the local kit clone
# before the script imports ipe_web_kit. Without it every tick dies with ModuleNotFoundError (2026-11-20). Failure = loud, exit 1.
KIT="${IPE_WEB_KIT_DIR:-$HOME/Developer/ipe_web_kit}"
[ -f "$CLONE/scripts/kit_lock.py" ] || { echo "ERROR kit_lock.py is missing in the clone - cannot install ipe_web_kit, not dispatching"; exit 1; }
if ! python3 "$CLONE/scripts/kit_lock.py" --root "$CLONE" sync --kit "$KIT"; then
  echo "ERROR ipe_web_kit sync failed (kit clone: $KIT; set IPE_WEB_KIT_DIR if it lives elsewhere) - not dispatching"
  exit 1
fi
exec python3 "$CLONE/scripts/dispatch_due.py" "$@"
