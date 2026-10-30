"""Publishing lint of `build_journal.py --check` (SEO guide v1, pipeline A + B): hard errors for broken posts (and for a NEW post under the
length floor), warnings (never failing) for thin / long / repeated text. Run: python3 -m unittest discover -s tests"""
import datetime as dt
import json
import os
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402
import check_sitemap  # noqa: E402
import indexnow  # noqa: E402
from test_build_journal import Base, run  # noqa: E402

LONG_EN = " ".join(["word"] * 420)
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
        post(self.tmp, lang="en", slug="a", body=" ".join(["w"] * 399))
        post(self.tmp, lang="ko", slug="b", body="가" * 799)
        w = self.lines(check(self.tmp))
        self.assertIn("en/a.md: original is short — 399 words (aim for 400+)", w)
        self.assertIn("ko/b.md: original is short — 799 chars (aim for 800+)", w)
        post(self.tmp, lang="en", slug="a", body=" ".join(["w"] * 400))
        post(self.tmp, lang="ko", slug="b", body="가" * 800)
        self.assertEqual([x for x in self.lines(check(self.tmp)) if "short" in x], [])

    def test_an_old_post_under_the_floor_only_warns(self):
        post(self.tmp, lang="en", slug="a", date="2026-10-30", extra="publish_at: 2026-10-30 10:00\n", body=" ".join(["w"] * 10))
        post(self.tmp, lang="ko", slug="b", date="2026-10-30", extra="publish_at: 2026-10-30 10:00\n", body="가" * 10)
        w = self.lines(check(self.tmp))  # returncode 0 asserted in lines()
        self.assertIn("en/a.md: original is short — 10 words (aim for 400+)", w)
        self.assertIn("ko/b.md: original is short — 10 chars (aim for 800+)", w)

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


class LengthFloor(Base):
    """Davy 2026-10-29: a NEW original (date >= LENGTH_ERROR_FROM) under 300 words / 600 CJK chars is an error at the author/merge gate;
    the deploy runner (flag or env) only warns, so a scheduled post is never held back by it."""
    NEW = "2026-10-31"

    def setUp(self):
        super().setUp()
        self._env = os.environ.pop(bj.LENGTH_SOFT_ENV, None)  # these tests judge the gate itself, whatever the outer shell exports

    def tearDown(self):
        if self._env is not None:
            os.environ[bj.LENGTH_SOFT_ENV] = self._env
        super().tearDown()

    def test_the_cut_over_date_is_named(self):
        self.assertEqual((bj.LENGTH_ERROR_FROM, bj.MIN_WORDS, bj.MIN_CJK_CHARS, bj.AIM_WORDS, bj.AIM_CJK_CHARS), ("2026-10-31", 300, 600, 400, 800))

    def test_a_new_original_under_the_floor_fails_at_the_boundary(self):
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body=" ".join(["w"] * 299))
        r = check(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("en/a.md: new post is below the length floor — 299 words (minimum 300, aim for 400+)", r.stderr)
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body=" ".join(["w"] * 300))
        r = check(self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)  # 300..399 is only the aim warning
        self.assertIn("en/a.md: original is short — 300 words (aim for 400+)", r.stdout)

    def test_a_new_korean_original_under_the_floor_fails_at_the_boundary(self):
        for lang in ("ko",):  # ja/zh are translations only (originals are ko/en), so they are never judged
            post(self.tmp, lang=lang, slug="b", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="가" * 599)
            r = check(self.tmp)
            self.assertEqual(r.returncode, 1, lang)
            self.assertIn("%s/b.md: new post is below the length floor — 599 chars (minimum 600, aim for 800+)" % lang, r.stderr)
            post(self.tmp, lang=lang, slug="b", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="가" * 600)
            r = check(self.tmp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("%s/b.md: original is short — 600 chars (aim for 800+)" % lang, r.stdout)
            (Path(self.tmp) / "content/journal" / lang / "b.md").unlink()

    def test_a_post_dated_2026_10_30_is_never_an_error_however_short(self):
        post(self.tmp, lang="en", slug="a", date="2026-10-30", extra="publish_at: 2026-10-30 10:00\n", body="short")
        post(self.tmp, lang="ko", slug="b", date="2026-10-30", extra="publish_at: 2026-10-30 10:00\n", body="짧다")
        self.assertEqual(check(self.tmp).returncode, 0)

    def test_a_translation_is_not_judged_by_the_floor(self):
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW)
        post(self.tmp, lang="ja", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="短い")
        self.assertEqual(check(self.tmp).returncode, 0)

    def test_the_normal_build_fails_too(self):
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="short")
        self.assertEqual(run(self.tmp).returncode, 1)

    def test_the_deploy_mode_flag_turns_the_floor_into_a_loud_warning(self):
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body=" ".join(["w"] * 299))
        post(self.tmp, lang="ko", slug="b", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="가" * 599)
        self.assertEqual(run(self.tmp, "--length-errors-as-warnings").returncode, 0)
        r = run(self.tmp, "--check", "--length-errors-as-warnings", "--now", "2026-10-31 12:00")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("new post below floor 2", r.stdout)
        self.assertIn("en/a.md: new post is below the length floor — 299 words (minimum 300, aim for 400+) — would FAIL", r.stdout)
        self.assertIn("ko/b.md: new post is below the length floor — 599 chars (minimum 600, aim for 800+) — would FAIL", r.stdout)
        self.assertEqual(check(self.tmp, "--length-errors-as-warnings").returncode, 0)  # incl. the "committed pages are up to date" part

    def test_the_deploy_mode_env_does_the_same_and_0_does_not(self):
        post(self.tmp, lang="en", slug="a", date=self.NEW, extra="publish_at: %s 10:00\n" % self.NEW, body="short")
        for val, code in (("1", 0), ("0", 1), ("", 1)):
            os.environ[bj.LENGTH_SOFT_ENV] = val
            try:
                self.assertEqual(check(self.tmp).returncode, code, repr(val))
            finally:
                del os.environ[bj.LENGTH_SOFT_ENV]

    def test_the_deploy_workflow_runs_in_deploy_mode(self):
        """the workflow's top-level env keeps the verify + publish steps (and the unit tests inside them) from failing on the length floor"""
        wf = (REPO / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        self.assertRegex(wf, r'(?m)^env:\n(?:  .*\n|\n)*?  %s: "1"\n' % bj.LENGTH_SOFT_ENV)

    def test_the_actions_annotation_is_printed_for_a_downgraded_floor(self):
        w = "en/a.md: new post is below the length floor — 299 words (minimum 300, aim for 400+) — would FAIL"
        old = os.environ.get("GITHUB_ACTIONS")
        os.environ["GITHUB_ACTIONS"] = "true"
        try:
            self.assertIn("::warning title=still length floor::" + w, bj.warning_text([w]))
        finally:
            os.environ.pop("GITHUB_ACTIONS") if old is None else os.environ.__setitem__("GITHUB_ACTIONS", old)

    def test_the_deploy_mode_leaves_the_other_errors_alone(self):
        post(self.tmp, date="2999-01-01", body="short")  # a future date without publish_at
        post(self.tmp, slug="ph", title="TODO later")
        r = run(self.tmp, "--check", "--length-errors-as-warnings")
        self.assertEqual(r.returncode, 1)
        self.assertIn("is in the future", r.stderr)
        self.assertIn("placeholder text", r.stderr)


class UpdatedClock(Base):
    """`updated` is judged against the REAL clock: a build that replays an earlier `--now` (the tests, a rebuild of the past) must not break on
    an `updated` that is already history today, and must never print it as its own dateModified; a real build still rejects a future one."""

    def modified(self, lang="en", slug="p1"):
        h = (Path(self.tmp) / "journal" / lang / slug / "index.html").read_text(encoding="utf-8")
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S).group(1))
        return ld["dateModified"], re.search(r'<meta property="article:modified_time" content="([^"]*)">', h).group(1)

    def test_a_past_clock_build_clamps_a_later_updated_instead_of_failing(self):
        post(self.tmp, date="2026-10-20", extra="updated: 2026-10-28\n")  # written after this clock, but long before the real today
        for args in (("--now", "2026-10-24 12:00"), ("--now", "2026-10-20 09:00")):
            r = run(self.tmp, *args)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(run(self.tmp, "--check", *args).returncode, 0)
            clock = args[1][:10]
            self.assertEqual(self.modified(), (clock, clock), args)  # never a date from the build's own future
            self.assertIn("<lastmod>%s</lastmod>" % clock, (Path(self.tmp) / "sitemap.xml").read_text(encoding="utf-8").split("/journal/en/p1/")[1])
            errs = check_sitemap.check(self.tmp, dt.datetime.fromisoformat(args[1]).replace(tzinfo=bj.KST))[0]
            self.assertEqual([e for e in errs if "/journal/" in e], [], args)  # (the copied home/info rows carry later stamps of their own)

    def test_a_past_clock_build_still_fails_for_an_updated_after_the_real_today(self):
        post(self.tmp, extra="updated: 2999-01-02\n")
        r = run(self.tmp, "--now", "2026-10-24 12:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("updated 2999-01-02 is in the future", r.stderr)

    def test_a_real_clock_build_rejects_a_future_updated_and_keeps_todays(self):
        today = dt.datetime.now(bj.KST).date()
        post(self.tmp, extra="updated: %s\n" % (today + dt.timedelta(days=1)))
        for args in ((), ("--now", "now")):
            r = run(self.tmp, *args)
            self.assertEqual(r.returncode, 1, args)
            self.assertIn("is in the future", r.stderr)
        post(self.tmp, extra="updated: %s\n" % today)
        for args in ((), ("--now", "now")):
            self.assertEqual(run(self.tmp, *args).returncode, 0, args)
            self.assertEqual(self.modified(), (today.isoformat(),) * 2)

    def test_a_future_clock_replay_is_unchanged(self):
        post(self.tmp, extra="updated: 2027-01-02\n")
        self.assertEqual(run(self.tmp, "--now", "2099-01-01 00:00").returncode, 0)
        self.assertEqual(self.modified(), ("2027-01-02",) * 2)
        post(self.tmp, extra="updated: 2100-01-02\n")
        self.assertEqual(run(self.tmp, "--now", "2099-01-01 00:00").returncode, 1)

    def test_indexnow_changed_picks_up_a_post_that_got_updated_today(self):
        today = dt.datetime.now(bj.KST).date().isoformat()
        post(self.tmp, date="2026-10-20")
        self.assertEqual(run(self.tmp, "--now", "now").returncode, 0)
        before = indexnow.sitemap_entries(Path(self.tmp) / "sitemap.xml")  # what is live: the post, lastmod = its date
        post(self.tmp, date="2026-10-20", extra="updated: %s\n" % today)  # the enriched post is deployed with updated = today
        self.assertEqual(run(self.tmp, "--now", "now").returncode, 0)
        after = indexnow.sitemap_entries(Path(self.tmp) / "sitemap.xml")
        urls = indexnow.changed_urls(after, today, before)
        post_url = [loc for loc, _ in after if loc.endswith("/journal/en/p1/")]
        self.assertEqual(len(post_url), 1)
        self.assertIn(post_url[0], urls)
        self.assertEqual(urls[-1].rsplit("/", 1)[-1], "sitemap.xml")
        self.assertEqual(indexnow.changed_urls(after, today, after), [])  # the next hourly run: nothing new


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
