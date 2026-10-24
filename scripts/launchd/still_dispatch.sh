#!/bin/bash
# still.ipe.rest journal dispatcher wrapper — template copy; the live one is ~/.ipe/bin/still_dispatch.sh (see README.md here).
# launchd calls this every 5 minutes. Outside the publish windows (KST 09:00-12:40, 16:00-18:40) it exits at once.
# Inside: refresh a dedicated read-only clone, then run scripts/dispatch_due.py (404 on a due post -> one `gh workflow run deploy.yml`).
# Pass --dry-run through to only look: ~/.ipe/bin/still_dispatch.sh --dry-run   (the window check is skipped with STILL_DISPATCH_ANYTIME=1)
set -u
HM="$(TZ=Asia/Seoul date +%H%M)"
HM=$((10#$HM))
in_window() { { [ "$HM" -ge 900 ] && [ "$HM" -le 1240 ]; } || { [ "$HM" -ge 1600 ] && [ "$HM" -le 1840 ]; }; }
if [ "${STILL_DISPATCH_ANYTIME:-0}" != "1" ] && ! in_window; then exit 0; fi

CLONE="${STILL_DISPATCH_CLONE:-$HOME/.ipe/still-rest-dispatch}"
REMOTE="https://github.com/blessu76/still-rest.git"
echo "=== $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S') KST dispatch tick"
if [ ! -d "$CLONE/.git" ]; then
  git clone --quiet "$REMOTE" "$CLONE" || { echo "ERROR clone failed"; exit 1; }
fi
git -C "$CLONE" pull --ff-only --quiet || { echo "ERROR git pull --ff-only failed"; exit 1; }
[ -f "$CLONE/scripts/dispatch_due.py" ] || { echo "dispatch_due.py is not in the clone yet (not pushed to main?) - nothing to do"; exit 0; }
exec python3 "$CLONE/scripts/dispatch_due.py" "$@"
