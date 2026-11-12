import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_legal  # noqa: E402


class MdToHtml(unittest.TestCase):
    def test_table_is_wrapped_for_narrow_screens(self):
        out = build_legal.md_to_html("| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn('<div class="tblwrap"><table>', out)
        self.assertEqual(out.count("<tr>"), 2)

    def test_first_h1_is_left_to_the_page(self):
        out = build_legal.md_to_html("# Title\n\n## 1. Who\n\ntext")
        self.assertNotIn("<h1>", out)
        self.assertIn("<h2>1. Who</h2>", out)

    def test_paragraph_before_list_is_closed(self):
        out = build_legal.md_to_html("lead\n- one\n- two")
        self.assertLess(out.index("<p>lead</p>"), out.index("<ul>"))

    def test_html_is_escaped_and_links_restricted(self):
        out = build_legal.md_to_html("<b>x</b> [a](javascript:alert(1)) [m](mailto:privacy@ipe.rest)")
        self.assertIn("&lt;b&gt;", out)
        self.assertNotIn('href="javascript', out)
        self.assertIn('href="mailto:privacy@ipe.rest"', out)

    def test_placeholders_pass_through_unchanged(self):
        out = build_legal.md_to_html("시행일: {시행일} [확인 필요: 주소]")
        self.assertIn("{시행일}", out)
        self.assertIn("[확인 필요: 주소]", out)


class Pages(unittest.TestCase):
    def test_committed_pages_match_a_fresh_build(self):
        self.assertEqual(build_legal.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
