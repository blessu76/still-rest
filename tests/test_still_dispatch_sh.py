"""Static checks for scripts/launchd/still_dispatch.sh (the shell wrapper is not run here: it needs git remote + launchd).
The kit must be installed into the clone BEFORE dispatch_due.py runs, and a failed install must stop the run loudly.
Run: python3 -m unittest discover -s tests"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WRAPPER = (REPO / "scripts" / "launchd" / "still_dispatch.sh").read_text(encoding="utf-8").splitlines()


def line_no(pred):
    hits = [i for i, l in enumerate(WRAPPER) if pred(l)]
    return hits


class WrapperKitSyncTests(unittest.TestCase):
    def test_sync_runs_before_exec(self):
        sync = line_no(lambda l: "kit_lock.py" in l and "sync" in l and not l.lstrip().startswith("#"))
        execs = line_no(lambda l: l.startswith("exec "))
        self.assertEqual(len(sync), 1)
        self.assertEqual(len(execs), 1)
        self.assertLess(sync[0], execs[0])

    def test_kit_dir_comes_from_env_with_default(self):
        self.assertTrue(any('IPE_WEB_KIT_DIR:-$HOME/Developer/ipe_web_kit' in l for l in WRAPPER))

    def test_sync_failure_exits_nonzero_with_message(self):
        i = line_no(lambda l: "kit_lock.py" in l and "sync" in l)[0]
        block = "\n".join(WRAPPER[i - 1:i + 4])
        self.assertIn("if ! python3", block)
        self.assertIn("ERROR ipe_web_kit sync failed", block)
        self.assertIn("exit 1", block)

    def test_exec_is_the_only_dispatch_entry(self):
        # dispatch_due.py may only be started by the exec line, which sits after the sync guard
        mentions = line_no(lambda l: "dispatch_due.py" in l and not l.lstrip().startswith("#"))
        self.assertEqual(len(mentions), 2)  # the existence check + the exec
        self.assertTrue(WRAPPER[mentions[-1]].startswith("exec "))


if __name__ == "__main__":
    unittest.main()
