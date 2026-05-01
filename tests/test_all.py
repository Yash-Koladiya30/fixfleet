"""Comprehensive tests — parser, locator, budget, confidence, prompt, registry."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make sure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bugfixer import budget, confidence
from bugfixer.backends import registry
from bugfixer.cli import _sanitize_path
from bugfixer.gitlab import parse_project_input
from bugfixer.backends.api.openai_compat import _apply_diff, _extract_diff
from bugfixer.locator import (
    extract_signals,
    inline_top_file,
    locate,
    rank_candidate_files,
)
from bugfixer.parser import parse_description, parse_issue
from bugfixer.prompt import build_prompt


# ── Sample issues ──────────────────────────────────────────────

ISSUE_FULL = {
    "iid": 42,
    "title": "Login button does nothing on Safari",
    "web_url": "https://gitlab.com/x/y/-/issues/42",
    "labels": ["Bug", "High", "frontend"],
    "description": """
## Description
Clicking Login on Safari 17 has no effect. Works in Chrome/Firefox.

## Steps to Reproduce
1. Open the site in Safari 17
2. Enter valid credentials
3. Click Login

## Expected Behavior
Redirect to /dashboard.

## Actual Behavior
Page does nothing. No console errors.

## Environment
- Safari 17.2 on macOS 14.4
- App version 2.3.1

## Logs
```
TypeError: undefined is not a function (evaluating event.preventDefault)
  at handleSubmit (src/auth/login.js:42:18)
  at HTMLFormElement.<anonymous> (src/auth/login.js:30:5)
```
""",
    "created_at": "2026-04-15T10:00:00Z",
}


ISSUE_PYTHON_TRACE = {
    "iid": 88,
    "title": "User registration crashes",
    "labels": ["Bug"],
    "web_url": "https://gitlab.com/x/y/-/issues/88",
    "description": """
**Description:** Crash when posting /api/users.

**Steps:**
1. POST /api/users with valid body

**Stack trace:**
```
Traceback (most recent call last):
  File "app/views/users.py", line 28, in create_user
    user = UserService.create(payload)
  File "app/services/user_service.py", line 102, in create
    raise ValidationError("email")
ValidationError: email
```
""",
}


ISSUE_BARE = {
    "iid": 1,
    "title": "Something broken",
    "labels": [],
    "web_url": "",
    "description": "Just plain text, no headings, no structure.",
}


ISSUE_SWIFT_DIAGNOSTIC = {
    "iid": 144,
    "title": "Build fails with extra trailing closure",
    "labels": ["Bug", "iOS"],
    "web_url": "https://gitlab.com/x/y/-/issues/144",
    "description": """
## Compiler Error
```
Sources/App/LoginView.swift:42:18: error: Extra trailing closure passed in call
```
""",
}


# ── Tests ──────────────────────────────────────────────────────

class TestParser(unittest.TestCase):

    def test_full_issue_extracts_all_sections(self):
        p = parse_issue(ISSUE_FULL)
        self.assertIn("Safari 17", p.description)
        self.assertIn("1. Open the site", p.steps)
        self.assertIn("/dashboard", p.expected)
        self.assertIn("No console errors", p.actual)
        self.assertIn("macOS 14.4", p.environment)
        self.assertIn("preventDefault", p.logs)

    def test_bold_headings(self):
        p = parse_issue(ISSUE_PYTHON_TRACE)
        self.assertIn("POST /api/users", p.steps)
        self.assertIn("ValidationError", p.logs)

    def test_bare_text_falls_back_to_description(self):
        p = parse_issue(ISSUE_BARE)
        self.assertEqual(p.description, "Just plain text, no headings, no structure.")
        self.assertEqual(p.steps, "")

    def test_empty_description_yields_empty_sections(self):
        p = parse_issue({"iid": 5, "title": "x", "description": ""})
        self.assertEqual(p.description, "")

    def test_section_aliases(self):
        body = "## Repro\n1. step\n\n## Current Behavior\nbroken"
        s = parse_description(body)
        self.assertIn("steps", s)
        self.assertIn("actual", s)


class TestLocator(unittest.TestCase):

    def test_extract_files(self):
        p = parse_issue(ISSUE_FULL)
        sig = extract_signals(p)
        self.assertTrue(any("login.js" in f for f in sig["files"]))

    def test_extract_python_stack_frames(self):
        p = parse_issue(ISSUE_PYTHON_TRACE)
        sig = extract_signals(p)
        files_in_frames = {fr["file"] for fr in sig["frames"]}
        self.assertIn("app/views/users.py", files_in_frames)
        self.assertIn("app/services/user_service.py", files_in_frames)

    def test_extract_js_stack_frames(self):
        p = parse_issue(ISSUE_FULL)
        sig = extract_signals(p)
        # JS regex should pick up src/auth/login.js
        files_in_frames = {fr["file"] for fr in sig["frames"]}
        self.assertTrue(any("login.js" in f for f in files_in_frames))

    def test_extract_swift_diagnostics(self):
        p = parse_issue(ISSUE_SWIFT_DIAGNOSTIC)
        sig = extract_signals(p)
        frame = sig["frames"][0]
        self.assertEqual(frame["file"], "Sources/App/LoginView.swift")
        self.assertEqual(frame["line"], 42)
        self.assertEqual(frame["column"], 18)
        self.assertEqual(frame["lang"], "swift")
        self.assertIn("Extra trailing closure", frame["func"])

    def test_rank_candidates_from_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "auth").mkdir(parents=True)
            (root / "src" / "auth" / "login.js").write_text(
                "function handleSubmit(event) { event.preventDefault(); }\n"
            )
            (root / "src" / "auth" / "logout.js").write_text("export const logout = () => {};\n")
            (root / "README.md").write_text("project")

            sig = {
                "files": ["src/auth/login.js"],
                "frames": [{"file": "src/auth/login.js", "line": 42, "func": "handleSubmit"}],
                "symbols": ["handleSubmit"],
            }
            ranked = rank_candidate_files(str(root), sig, max_files=3)
            self.assertTrue(any("login.js" in r for r in ranked))
            # login.js should outrank logout.js (no signal for logout)
            self.assertEqual(Path(ranked[0]).name, "login.js")

    def test_inline_top_file_truncates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "big.py"
            target.write_text("\n".join(f"line {i}" for i in range(1000)))
            inlined = inline_top_file(str(root), ["big.py"], max_lines=200)
            self.assertEqual(inlined["path"], "big.py")
            self.assertEqual(inlined["line_count"], 1000)
            self.assertIn("lines elided", inlined["content"])

    def test_locate_no_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = parse_issue(ISSUE_BARE)
            loc = locate(p, tmp)
            self.assertFalse(loc.has_hints)


class TestBudget(unittest.TestCase):

    def test_slim_truncates(self):
        text = "a" * 5000
        out = budget.slim(text, 1000)
        self.assertLessEqual(len(out), 1100)  # plus truncation marker
        self.assertIn("truncated", out)

    def test_slim_passthrough(self):
        text = "small"
        self.assertEqual(budget.slim(text, 100), "small")

    def test_estimate_tokens(self):
        self.assertEqual(budget.estimate_tokens(""), 0)
        self.assertGreater(budget.estimate_tokens("hello world" * 100), 100)

    def test_check_budget_allows_small(self):
        c = budget.check_budget("short prompt", "claude", 0, 0)
        self.assertTrue(c.allowed)

    def test_check_budget_blocks_oversize(self):
        big_prompt = "x" * 200_000
        c = budget.check_budget(big_prompt, "claude", 0, 0)
        self.assertFalse(c.allowed)
        self.assertIn("per-issue cap", c.reason)

    def test_check_budget_blocks_session(self):
        # "short" prompt yields a few estimated tokens; session_used must be at-cap
        c = budget.check_budget(
            "short", "claude", session_used=200_000, daily_used=0,
        )
        self.assertFalse(c.allowed)
        self.assertIn("session cap", c.reason)


class TestConfidence(unittest.TestCase):

    def test_parse_fix_report(self):
        out = """
some output ...
=== FIX REPORT ===
ROOT_CAUSE: Missing null check in handler
FILES_CHANGED: src/auth/login.js
CONFIDENCE: 8/10
REASONING: clear repro, surgical fix
TESTS_RUN: no
=== END FIX REPORT ===
"""
        f = confidence.parse_fix_report(out)
        self.assertEqual(f["CONFIDENCE"], "8/10")
        self.assertEqual(f["TESTS_RUN"], "no")
        self.assertEqual(confidence.parse_self_rating(f), 8)

    def test_hedge_density(self):
        text = "I think maybe this might possibly fix it. Not sure though."
        self.assertGreater(confidence.hedge_density(text), 0)
        self.assertEqual(confidence.hedge_density("clear and definitive"), 0)

    def test_diff_focus_score_no_diff(self):
        stats = {"is_git": True, "files": [], "lines_added": 0, "lines_removed": 0}
        self.assertEqual(confidence.diff_focus_score(stats), 0.0)

    def test_diff_focus_score_small_diff(self):
        stats = {"is_git": True, "files": ["a.py", "b.py"], "lines_added": 5, "lines_removed": 3}
        s = confidence.diff_focus_score(stats)
        self.assertGreater(s, 0.7)

    def test_diff_focus_score_huge_diff(self):
        stats = {"is_git": True, "files": ["a.py"] * 10, "lines_added": 800, "lines_removed": 0}
        s = confidence.diff_focus_score(stats)
        self.assertLess(s, 0.3)

    def test_evaluate_no_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = confidence.evaluate("(empty output)", tmp)
            self.assertGreaterEqual(r.final_score, 0.0)
            self.assertLessEqual(r.final_score, 1.0)
            self.assertIn("not a git repo", " ".join(r.notes))

    def test_evaluate_with_git_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
            f = Path(tmp) / "x.py"
            f.write_text("a = 1\n")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

            f.write_text("a = 1\nb = 2\n")  # one-line diff

            stdout = """
explanation here
=== FIX REPORT ===
ROOT_CAUSE: missing var
FILES_CHANGED: x.py
CONFIDENCE: 9/10
REASONING: trivial
TESTS_RUN: n/a
=== END FIX REPORT ===
"""
            r = confidence.evaluate(stdout, tmp, candidate_files=["x.py"], issue_keywords=["b"])
            self.assertGreater(r.final_score, 0.6)
            self.assertIn("x.py", r.files_changed)
            self.assertEqual(r.self_rating, 9)


class TestPrompt(unittest.TestCase):

    def test_build_prompt_full(self):
        from bugfixer.locator import LocatorResult

        p = parse_issue(ISSUE_FULL)
        loc = LocatorResult(
            files_mentioned=["src/auth/login.js"],
            stack_frames=[{"file": "src/auth/login.js", "line": 42, "func": "handleSubmit", "lang": "js"}],
            symbols=["handleSubmit"],
            candidates=["src/auth/login.js"],
            top_inline={"path": "src/auth/login.js", "content": "function handleSubmit(){}", "line_count": 50},
        )
        prompt = build_prompt(p, locator=loc)

        # Expect locator hints, FIX REPORT instruction, all sections
        self.assertIn("Steps to Reproduce", prompt)
        self.assertIn("Locator Hints", prompt)
        self.assertIn("FIX REPORT", prompt)
        self.assertIn("untrusted user-reported content", prompt)
        self.assertIn("login.js", prompt)

    def test_prompt_handles_backtick_content(self):
        # Description with triple-backticks should not break fence
        issue = {
            "iid": 7, "title": "t",
            "description": "## Description\nThis has ``` backticks ``` inside.",
            "labels": [], "web_url": "",
        }
        p = parse_issue(issue)
        prompt = build_prompt(p)
        # Prompt must still parse — no unbalanced fences
        self.assertIn("backticks", prompt)


class TestPathSanitizer(unittest.TestCase):

    def test_strips_cd_prefix(self):
        self.assertEqual(_sanitize_path("cd /Users/foo/bar"), "/Users/foo/bar")
        self.assertEqual(_sanitize_path("CD /Users/foo/bar"), "/Users/foo/bar")

    def test_strips_quotes(self):
        self.assertEqual(_sanitize_path('"/Users/foo bar"'), "/Users/foo bar")
        self.assertEqual(_sanitize_path("'/path'"), "/path")

    def test_unescapes_spaces(self):
        self.assertEqual(
            _sanitize_path("/Users/yashkoladiya/Documents/Projects/App\\ Aspect/dual-accounts"),
            "/Users/yashkoladiya/Documents/Projects/App Aspect/dual-accounts",
        )

    def test_unescapes_parens(self):
        self.assertEqual(
            _sanitize_path("/Users/me/Foo\\ \\(bar\\)/baz"),
            "/Users/me/Foo (bar)/baz",
        )

    def test_strips_whitespace(self):
        self.assertEqual(_sanitize_path("  /path/to/dir  "), "/path/to/dir")

    def test_passes_clean_path_through(self):
        self.assertEqual(_sanitize_path("/Users/foo/bar"), "/Users/foo/bar")
        self.assertEqual(_sanitize_path("~/work"), "~/work")


class TestProjectInputParser(unittest.TestCase):

    def test_https_url(self):
        h, p = parse_project_input("https://gitlab.com/group/project")
        self.assertEqual((h, p), ("gitlab.com", "group/project"))

    def test_https_url_with_git_suffix(self):
        h, p = parse_project_input("https://gitlab.com/group/project.git")
        self.assertEqual((h, p), ("gitlab.com", "group/project"))

    def test_https_url_with_issues_path(self):
        h, p = parse_project_input("https://gitlab.com/group/sub/proj/-/issues/42")
        self.assertEqual((h, p), ("gitlab.com", "group/sub/proj"))

    def test_https_url_with_blob_path(self):
        h, p = parse_project_input("https://gitlab.com/g/p/-/blob/main/README.md")
        self.assertEqual((h, p), ("gitlab.com", "g/p"))

    def test_self_hosted_https(self):
        h, p = parse_project_input("https://gitlab.example.com/team/repo")
        self.assertEqual((h, p), ("gitlab.example.com", "team/repo"))

    def test_ssh_url(self):
        h, p = parse_project_input("git@gitlab.com:group/project.git")
        self.assertEqual((h, p), ("gitlab.com", "group/project"))

    def test_ssh_protocol_url(self):
        h, p = parse_project_input("ssh://git@gitlab.com/group/project.git")
        self.assertEqual((h, p), ("gitlab.com", "group/project"))

    def test_plain_path(self):
        h, p = parse_project_input("group/project")
        self.assertEqual((h, p), ("gitlab.com", "group/project"))

    def test_subgroup_path(self):
        h, p = parse_project_input("group/subgroup/project")
        self.assertEqual((h, p), ("gitlab.com", "group/subgroup/project"))

    def test_numeric_id(self):
        h, p = parse_project_input("12345")
        self.assertEqual((h, p), ("gitlab.com", "12345"))

    def test_appaspect_real_url(self):
        h, p = parse_project_input(
            "https://gitlab.com/appaspect-technologies-projects/appaspect-ios/dual-accounts.git"
        )
        self.assertEqual(h, "gitlab.com")
        self.assertEqual(p, "appaspect-technologies-projects/appaspect-ios/dual-accounts")

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            parse_project_input("")
        with self.assertRaises(ValueError):
            parse_project_input("   ")

    def test_trailing_slash_stripped(self):
        h, p = parse_project_input("https://gitlab.com/group/project/")
        self.assertEqual(p, "group/project")


class TestRegistry(unittest.TestCase):

    def test_list_all_clis_returns_six(self):
        clis = registry.list_cli_backends()
        self.assertEqual(len(clis), 6)
        names = {b.name for b in clis}
        self.assertSetEqual(names, {"claude", "codex", "gemini", "aider", "qwen", "cursor"})

    def test_api_presets_have_required_fields(self):
        for k, p in registry.API_PRESETS.items():
            self.assertIn("label", p)
            self.assertIn("base_url", p)
            self.assertIn("default_model", p)
            self.assertIn("key_url", p)

    def test_build_api_backend(self):
        b = registry.build_api_backend(
            base_url="https://api.example/v1",
            api_key="key",
            model="m",
        )
        self.assertEqual(b.model, "m")


class TestDiffApply(unittest.TestCase):

    def test_extract_fenced_diff(self):
        text = """
explanation

```diff
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,3 @@
 a = 1
+b = 2
 c = 3
```
"""
        d = _extract_diff(text)
        self.assertIn("--- a/foo.py", d)
        self.assertIn("@@ -1,2 +1,3 @@", d)

    def test_apply_diff_to_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
            f = Path(tmp) / "foo.py"
            f.write_text("a = 1\nc = 3\n")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)

            diff = (
                "--- a/foo.py\n"
                "+++ b/foo.py\n"
                "@@ -1,2 +1,3 @@\n"
                " a = 1\n"
                "+b = 2\n"
                " c = 3\n"
            )
            rc, msg = _apply_diff(diff, tmp)
            self.assertEqual(rc, 0, f"diff apply failed: {msg}")
            self.assertEqual(f.read_text(), "a = 1\nb = 2\nc = 3\n")


class TestStateAndConfig(unittest.TestCase):

    def setUp(self):
        # Redirect HOME so state/config don't pollute the real user dir
        self._tmp = tempfile.mkdtemp()
        self._orig_home = os.environ.get("HOME")
        os.environ["HOME"] = self._tmp
        # Reload modules to pick up new HOME
        from importlib import reload
        from bugfixer import config as _cfg, state as _st
        reload(_cfg)
        reload(_st)
        self.config_mod = _cfg
        self.state_mod = _st

    def tearDown(self):
        if self._orig_home is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = self._orig_home
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_config_defaults(self):
        cfg = self.config_mod.load()
        self.assertIn("budgets", cfg)
        self.assertEqual(cfg["default_backend"], "")

    def test_config_save_load_roundtrip(self):
        cfg = self.config_mod.load()
        cfg["default_backend"] = "claude"
        cfg["budgets"]["per_issue_max_tokens"] = 12345
        self.config_mod.save(cfg)
        cfg2 = self.config_mod.load()
        self.assertEqual(cfg2["default_backend"], "claude")
        self.assertEqual(cfg2["budgets"]["per_issue_max_tokens"], 12345)

    def test_state_record_and_query(self):
        self.state_mod.record_usage(
            backend_name="claude", tokens=5000,
            project_id="g/p", issue_iid=42, success=True,
        )
        self.assertEqual(self.state_mod.get_daily_usage("claude"), 5000)
        self.assertTrue(self.state_mod.was_fixed("g/p", 42))
        self.assertFalse(self.state_mod.was_fixed("g/p", 999))


if __name__ == "__main__":
    unittest.main(verbosity=2)
