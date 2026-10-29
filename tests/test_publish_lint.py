"""Publishing lint of `build_journal.py --check` (SEO guide v1, pipeline A + B): hard errors for broken posts, warnings (never failing) for
thin / long / repeated text. Run: python3 -m unittest discover -s tests"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402
from test_build_journal import Base, run  # noqa: E402

LONG_EN = " ".join(["word"] * 320)
LONG_KO = "가" * 850


def post(root, lang="en", slug="p1", date="2026-10-20", title="A title", desc="A short description.", body=None, extra=""):
    d = Path(root) / "content/journal" / lang
    d.mkdir(parents=True, exist_ok=True)
    tr = "" if lang in ("ko", "en") else "translation_of: en\n"
    body = body if body is not None else (LONG_KO if lang == "ko" else LONG_EN)
    (d / (slug + ".md")).write_text("---\ntitle: %s\ndate: %s\nslug: %s\nlang: %s\ndescription: %s\ncategory: test\n%s%s---\n\n%s\n"
                                    % (title, date, slug, lang, desc, tr, extra, body), encoding="utf-8")


def check(root, *args):
    """`build_journal.py --check` on a site that was just built (so the "committed pages are up to date" part passes and only the lint is judged)."""
    run(root)
    return run(root, "--check", *args)


class Errors(Base):
    def test_a_clean_post_passes_without_warnings(self):
        post(self.tmp)
        self.assertEqual(run(self.tmp).returncode, 0)
        r = check(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("warning", r.stdout)

    def test_required_fields_fail(self):
        for missing in ("title", "date", "slug", "lang", "description", "category"):
            d = Path(self.tmp) / "content/journal/en"
            d.mkdir(parents=True, exist_ok=True)
            lines = {"title": "title: T", "date": "date: 2026-10-20", "slug": "slug: p1", "lang": "lang: en", "description": "description: D", "category": "category: c"}
            del lines[missing]
            (d / "p1.md").write_text("---\n%s\n---\n\nBody\n" % "\n".join(lines.values()), encoding="utf-8")
            r = check(self.tmp)
            self.assertEqual(r.returncode, 1, missing)
            self.assertIn("missing front matter: " + missing, r.stderr, missing)

    def test_a_future_date_without_publish_at_fails(self):
        post(self.tmp, date="2999-01-01")
        r = check(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("date 2999-01-01 is in the future", r.stderr)
        self.assertIn("publish_at", r.stderr)  # the message says how to publish later

    def test_a_scheduled_future_post_is_fine(self):
        post(self.tmp, date="2999-01-01", extra="publish_at: 2999-01-01 10:00\n")
        r = check(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_date_is_judged_against_the_build_clock_when_given(self):
        post(self.tmp, date="2026-10-30")
        self.assertEqual(check(self.tmp, "--now", "2026-10-29 23:59").returncode, 1)
        self.assertEqual(check(self.tmp, "--now", "2026-10-30 00:00").returncode, 0)

    def test_published_at_and_updated_in_the_future_fail(self):
        post(self.tmp, date="2999-01-01", extra="published_at: 2999-01-01 10:00\n")
        self.assertIn("published_at 2999-01-01 10:00 is in the future", check(self.tmp).stderr)
        post(self.tmp, extra="updated: 2999-01-02\n")
        self.assertIn("updated 2999-01-02 is in the future", check(self.tmp).stderr)

    def test_updated_before_the_date_fails(self):
        post(self.tmp, date="2026-10-20", extra="updated: 2026-10-19\n")
        self.assertIn("updated 2026-10-19 is before the post's date 2026-10-20", check(self.tmp).stderr)

    def test_a_draft_is_not_linted(self):
        post(self.tmp, date="2999-01-01", title="TODO", extra="draft: true\n")
        self.assertEqual(check(self.tmp).returncode, 0)

    def test_placeholder_text_fails_but_the_word_todo_in_a_language_does_not(self):
        for field_title, field_desc in (("TODO title", "ok."), ("ok", "Describe it YYYY-MM-DD"), ("Lorem Ipsum dolor", "ok.")):
            post(self.tmp, title=field_title, desc=field_desc)
            r = check(self.tmp)
            self.assertEqual(r.returncode, 1, (field_title, field_desc))
            self.assertIn("placeholder text", r.stderr)
        post(self.tmp, lang="pt", title="Tudo bem", desc="Todo mundo precisa descansar.")
        post(self.tmp, lang="en", slug="p1")  # the en original so that pt has its source
        self.assertEqual(check(self.tmp).returncode, 0)

    def test_a_second_file_with_the_same_slug_fails_on_its_file_name(self):
        post(self.tmp, slug="p1")
        d = Path(self.tmp) / "content/journal/en"
        (d / "copy.md").write_text((d / "p1.md").read_text(encoding="utf-8"), encoding="utf-8")  # slug p1 again, in a different file
        r = check(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("file name must be <slug>.md", r.stderr)

    def test_the_slug_cannot_be_reserved(self):
        for slug in ("feed", "page", "ko"):
            post(self.tmp, slug=slug)
            self.assertIn("reserved", check(self.tmp).stderr, slug)
            (Path(self.tmp) / "content/journal/en" / (slug + ".md")).unlink()

    def test_the_lint_also_fails_the_normal_build(self):
        post(self.tmp, date="2999-01-01")
        self.assertEqual(run(self.tmp).returncode, 1)


class Warnings(Base):
    def lines(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        return re.findall(r"warning: (.*)", r.stdout)

    def test_a_short_original_warns_in_words_and_in_cjk_characters(self):
        post(self.tmp, lang="en", slug="a", body=" ".join(["w"] * 299))
        post(self.tmp, lang="ko", slug="b", body="가" * 799)
        w = self.lines(check(self.tmp))
        self.assertIn("en/a.md: original is short — 299 words (aim for 400+)", w)
        self.assertIn("ko/b.md: original is short — 799 chars (aim for 800+)", w)
        post(self.tmp, lang="en", slug="a", body=" ".join(["w"] * 300))
        post(self.tmp, lang="ko", slug="b", body="가" * 800)
        self.assertEqual([x for x in self.lines(check(self.tmp)) if "short" in x], [])

    def test_a_translation_is_not_judged_by_length(self):
        post(self.tmp, lang="en", slug="a")
        post(self.tmp, lang="ja", slug="a", body="短い")
        self.assertEqual([x for x in self.lines(check(self.tmp)) if "ja/" in x], [])

    def test_title_length_latin_60_cjk_40(self):
        post(self.tmp, lang="en", slug="a", title="t" * 61)
        post(self.tmp, lang="ko", slug="b", title="가" * 41)
        w = self.lines(check(self.tmp))
        self.assertIn("en/a.md: title is 61 characters (max 60 before a search result cuts it)", w)
        self.assertIn("ko/b.md: title is 41 characters (max 40 before a search result cuts it)", w)
        post(self.tmp, lang="en", slug="a", title="t" * 60)
        post(self.tmp, lang="ko", slug="b", title="가" * 40)
        self.assertEqual([x for x in self.lines(check(self.tmp)) if "title is" in x], [])

    def test_description_length_latin_160_cjk_110(self):
        post(self.tmp, lang="en", slug="a", desc="d" * 161)
        post(self.tmp, lang="ko", slug="b", desc="가" * 111)
        w = self.lines(check(self.tmp))
        self.assertIn("en/a.md: description is 161 characters (max 160 before a search result cuts it)", w)
        self.assertIn("ko/b.md: description is 111 characters (max 110 before a search result cuts it)", w)
        post(self.tmp, lang="en", slug="a", desc="d" * 160)
        post(self.tmp, lang="ko", slug="b", desc="가" * 110)
        self.assertEqual([x for x in self.lines(check(self.tmp)) if "description is" in x], [])

    def test_the_same_title_twice_in_one_language_warns_but_not_across_languages(self):
        post(self.tmp, lang="en", slug="a", title="Same")
        post(self.tmp, lang="en", slug="b", title="same ")
        post(self.tmp, lang="ko", slug="a", title="Same")
        w = self.lines(check(self.tmp))
        self.assertEqual([x for x in w if "same title" in x], ["en/a.md, en/b.md: the same title is used by 2 posts in en"])

    def test_scheduled_posts_are_linted_too_and_drafts_are_not(self):
        post(self.tmp, lang="en", slug="s", date="2999-01-01", title="t" * 70, extra="publish_at: 2999-01-01 10:00\n")
        post(self.tmp, lang="en", slug="d", title="t" * 70, extra="draft: true\n")
        w = self.lines(check(self.tmp))
        self.assertTrue(any(x.startswith("en/s.md: title is 70") for x in w), w)
        self.assertFalse(any(x.startswith("en/d.md") for x in w), w)

    def test_warnings_never_change_the_exit_code_or_the_output(self):
        post(self.tmp, lang="en", slug="a", title="t" * 99, desc="d" * 300, body="short")
        self.assertEqual(check(self.tmp).returncode, 0)
        r = run(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("warning(s) — not failing", r.stdout)
        self.assertEqual(check(self.tmp).returncode, 0)  # the generated pages are still "up to date": warnings add nothing to them

    def test_the_summary_counts_each_kind(self):
        post(self.tmp, lang="en", slug="a", title="t" * 99, desc="d" * 300, body="short")
        self.assertIn("(description too long 1, short original 1, title too long 1)", check(self.tmp).stdout)


class Committed(unittest.TestCase):
    def test_the_real_content_has_no_lint_error(self):
        r = run(REPO, "--check", "--strict-safety")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_the_real_content_passes_at_the_deploy_clock_and_its_warnings_are_only_the_known_kinds(self):
        r = run(REPO, "--check", "--now", "2026-10-29 23:59", "--strict-safety")
        self.assertEqual(r.returncode, 0, r.stderr)
        for w in re.findall(r"warning: (.*)", r.stdout):
            self.assertRegex(w, r"original is short|title is \d+ characters|description is \d+ characters|same title")


if __name__ == "__main__":
    unittest.main()
