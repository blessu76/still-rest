"""ipe_web_kit vendor copy (vendor/ipe_web_kit): untouched since install, and the still-only duplicates agree with it"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KIT = REPO / "vendor/ipe_web_kit"
sys.path.insert(0, str(REPO / "scripts"))


class KitVendor(unittest.TestCase):
    def test_kit_untouched(self):
        # vendor.py verify compares every file with MANIFEST.sha256 (offline) — a hand-edited vendor copy fails here
        r = subprocess.run([sys.executable, str(KIT / "vendor.py"), "verify", str(REPO)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_version_stamp(self):
        self.assertTrue((KIT / "KIT_VERSION").read_text(encoding="utf-8").startswith("v"))

    def test_site_common_uses_the_kit(self):
        import ipe_web_kit.localtime as kit_lt
        import ipe_web_kit.seo as kit_seo
        import site_common
        self.assertIs(site_common.meta_desc, kit_seo.meta_desc)
        self.assertIs(site_common.esc, kit_seo.esc)
        self.assertIs(site_common.ORG, kit_seo.ORG)
        self.assertIs(site_common.with_localtime, kit_lt.with_localtime)

    def test_local_js_copy_is_the_kit_asset(self):
        # scripts/ipe-localtime.js is only read by tests/test_localtime.py now; the build inlines the kit's copy
        self.assertEqual((REPO / "scripts/ipe-localtime.js").read_bytes(), (KIT / "assets/ipe-localtime.js").read_bytes())


if __name__ == "__main__":
    unittest.main()
