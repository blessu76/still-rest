"""Legacy language redirects (ipe_web_kit.redirects): zh -> zh-Hant, ru/ar/hi -> en, pt -> pt-BR. Run: python3 -m unittest discover -s tests"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "vendor"))
from ipe_web_kit import redirects as kit  # noqa: E402

RULES = {"pt": "pt-BR", "zh": "zh-Hant", "ar": "en", "hi": "en", "ru": "en"}


class LegacyRedirects(unittest.TestCase):
    def test_kit_rules_are_the_agreed_ones(self):
        self.assertEqual(kit.LEGACY_REDIRECTS, RULES)

    def test_committed_pages_are_fresh(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/build_redirects.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_old_page_points_at_the_same_page_in_the_new_language(self):
        for old, new in RULES.items():
            for rest in ("", "faq/", "about/"):
                h = (REPO / old / rest / "index.html").read_text(encoding="utf-8")
                self.assertIn('<link rel="canonical" href="https://still.ipe.rest/%s/%s">' % (new, rest), h, (old, rest))
                self.assertIn('<meta name="robots" content="noindex,follow">', h, (old, rest))
                self.assertTrue((REPO / new / rest / "index.html").is_file(), (new, rest))  # the target exists

    def test_old_journal_pages_redirect_to_an_existing_journal_page(self):
        for old in RULES:
            for f in (REPO / "journal" / old).rglob("index.html"):
                h = f.read_text(encoding="utf-8")
                url = h.split('<link rel="canonical" href="', 1)[1].split('"', 1)[0]
                self.assertTrue((REPO / url[len("https://still.ipe.rest/"):] / "index.html").is_file(), (str(f), url))

    def test_old_languages_are_not_in_the_sitemap(self):
        self.assertEqual(kit.sitemap_leaks((REPO / "sitemap.xml").read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
