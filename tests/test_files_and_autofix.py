"""Tests for file bug sources, the bug ledger, auto-fix, and the chat engine."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["FIXFLEET_TELEMETRY"] = "0"

from bugfixer.files import FileSourceError, parse_bug_file
from bugfixer.files.mapper import map_headers, rows_to_bugs
from bugfixer.files.freetext import extract_bugs_from_text


# ── Helpers to build real xlsx/docx in memory ──────────────────

def make_xlsx(path: str, rows: list):
    """Build a minimal valid .xlsx with inline strings."""
    def col_letter(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s

    sheet_rows = []
    for r, row in enumerate(rows, 1):
        cells = "".join(
            f'<c r="{col_letter(c)}{r}" t="inlineStr"><is><t>{v}</t></is></c>'
            for c, v in enumerate(row)
        )
        sheet_rows.append(f'<row r="{r}">{cells}</row>')
    sheet = (
        '<?xml version="1.0"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def make_docx(path: str, paragraphs: list, table: list = None):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    if table:
        rows = "".join(
            "<w:tr>" + "".join(
                f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row
            ) + "</w:tr>"
            for row in table
        )
        body += f"<w:tbl>{rows}</w:tbl>"
    doc = f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)


# ── Excel ──────────────────────────────────────────────────────

class TestXlsxSource(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_standard_columns(self):
        p = os.path.join(self.dir, "bugs.xlsx")
        make_xlsx(p, [
            ["ID", "Title", "Description", "Steps to Reproduce", "Priority", "Status"],
            ["1", "Login crashes on empty password", "NPE in auth", "1. open 2. submit", "High", "Open"],
            ["2", "Search is slow", "Takes 10s", "", "critical", "open"],
            ["3", "Old fixed bug", "done long ago", "", "low", "Fixed"],
        ])
        bugs = parse_bug_file(p)
        self.assertEqual(len(bugs), 2)  # fixed row skipped
        self.assertEqual(bugs[0]["iid"], "1")
        self.assertEqual(bugs[0]["title"], "Login crashes on empty password")
        self.assertIn("High", bugs[0]["labels"])
        self.assertIn("Steps to Reproduce", bugs[0]["description"])
        self.assertIn("High", bugs[1]["labels"])  # critical → High

    def test_odd_headers_still_map(self):
        p = os.path.join(self.dir, "bugs.xlsx")
        make_xlsx(p, [
            ["Sr No", "Bug Summary", "Details", "Sev"],
            ["1", "Crash when rotating device", "See video", "P1"],
        ])
        bugs = parse_bug_file(p)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0]["title"], "Crash when rotating device")
        self.assertIn("High", bugs[0]["labels"])

    def test_no_title_column_fails_clearly(self):
        p = os.path.join(self.dir, "bugs.xlsx")
        make_xlsx(p, [["Foo", "Bar"], ["a", "b"], ["c", "d"]])
        with patch("bugfixer.files.mapper.map_headers_with_ai", return_value={}):
            with self.assertRaises(FileSourceError) as ctx:
                parse_bug_file(p)
        self.assertEqual(ctx.exception.code, "mapping_failed")

    def test_missing_file(self):
        with self.assertRaises(FileSourceError) as ctx:
            parse_bug_file(os.path.join(self.dir, "nope.xlsx"))
        self.assertEqual(ctx.exception.code, "file_not_found")

    def test_unsupported_extension(self):
        p = os.path.join(self.dir, "bugs.txt")
        Path(p).write_text("hi")
        with self.assertRaises(FileSourceError) as ctx:
            parse_bug_file(p)
        self.assertEqual(ctx.exception.code, "unsupported_format")


# ── Word ───────────────────────────────────────────────────────

class TestDocxSource(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_table_document(self):
        p = os.path.join(self.dir, "bugs.docx")
        make_docx(p, ["QA Report"], table=[
            ["ID", "Title", "Description"],
            ["7", "Checkout button unresponsive", "On iOS Safari only"],
        ])
        bugs = parse_bug_file(p)
        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0]["iid"], "7")
        self.assertEqual(bugs[0]["title"], "Checkout button unresponsive")

    def test_numbered_list_document(self):
        p = os.path.join(self.dir, "bugs.docx")
        make_docx(p, [
            "Bugs found in sprint 12:",
            "1. App crashes when uploading photos larger than 10MB",
            "Steps: pick a big photo",
            "2. Profile name shows null for new accounts",
        ])
        bugs = parse_bug_file(p)
        self.assertEqual(len(bugs), 2)
        self.assertIn("crashes when uploading", bugs[0]["title"])
        self.assertIn("Steps", bugs[0]["description"])


# ── Free-text extraction ───────────────────────────────────────

class TestFreeText(unittest.TestCase):
    def test_bug_prefix_style(self):
        text = "Bug: Payment fails with Visa cards\ndetails here\nBug: Logout loops forever"
        bugs = extract_bugs_from_text(text, "file://x.pdf")
        self.assertEqual(len(bugs), 2)

    def test_jira_key_style(self):
        text = "APP-101: Camera permission not requested\nAPP-102 - Dark mode text unreadable"
        bugs = extract_bugs_from_text(text, "file://x.pdf")
        self.assertEqual([b["iid"] for b in bugs], ["APP-101", "APP-102"])

    def test_empty_text(self):
        self.assertEqual(extract_bugs_from_text("", "file://x.pdf"), [])


# ── Ledger ─────────────────────────────────────────────────────

class TestBugList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch("bugfixer.buglist.LIST_PATH",
                              Path(self.tmp) / "ledger.json")
        self._patcher.start()
        from bugfixer import buglist
        self.bl = buglist

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bug(self, iid, title):
        return {"iid": iid, "title": title, "labels": [], "web_url": ""}

    def test_sync_dedup_and_status(self):
        stats = self.bl.sync("file:a.xlsx", [self._bug(1, "Crash on login")])
        self.assertEqual(stats["added"], 1)
        # Re-sync: known, not duplicated
        stats = self.bl.sync("file:a.xlsx", [self._bug(1, "Crash on login")])
        self.assertEqual(stats["known"], 1)
        # Same title from another source → duplicate
        stats = self.bl.sync("gitlab:grp/proj", [self._bug(42, "Crash on login")])
        self.assertEqual(stats["duplicates"], 1)
        dups = self.bl.list_bugs(status="duplicate")
        self.assertEqual(len(dups), 1)

    def test_mark_and_fixing_lock(self):
        self.bl.sync("file:a.xlsx", [self._bug(1, "Bug one")])
        key = self.bl.bug_key("file:a.xlsx", 1, "Bug one")
        self.assertTrue(self.bl.mark(key, "fixing"))
        self.assertFalse(self.bl.mark(key, "fixing"))  # already fixing → refused
        self.assertTrue(self.bl.mark(key, "fixed", confidence=0.9))
        self.assertEqual(self.bl.get(key)["last_confidence"], 0.9)
        with self.assertRaises(ValueError):
            self.bl.mark(key, "bogus")

    def test_summary(self):
        self.bl.sync("s", [self._bug(1, "A"), self._bug(2, "B")])
        self.assertEqual(self.bl.summary().get("new"), 2)


# ── Auto-fix engine ────────────────────────────────────────────

class FakeBackend:
    name = "fake"
    display_name = "Fake"

    def __init__(self, project_dir, make_change=True, report_confidence="9"):
        self.project_dir = project_dir
        self.make_change = make_change
        self.report_confidence = report_confidence

    def run(self, prompt, project_dir, timeout=600):
        from bugfixer.backends.base import RunResult
        if self.make_change:
            Path(project_dir, "app.py").write_text("fixed = True\n")
        stdout = (
            "=== FIX REPORT ===\n"
            "ROOT_CAUSE: off by one\n"
            f"CONFIDENCE: {self.report_confidence} / 10\n"
            "TESTS_RUN: yes\n"
            "=== END FIX REPORT ===\n"
        )
        return RunResult(returncode=0, stdout=stdout)


class TestAutoFix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.repo)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.repo)
        Path(self.repo, "app.py").write_text("fixed = False\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)
        self._patcher = patch("bugfixer.buglist.LIST_PATH",
                              Path(self.tmp) / "ledger.json")
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bugs(self):
        return [{"iid": 1, "title": "fixed flag never set", "description": "app.py wrong",
                 "labels": [], "web_url": ""}]

    def test_high_confidence_kept(self):
        from bugfixer import autofix
        backend = FakeBackend(self.repo, make_change=True, report_confidence="9")
        summary = autofix.run_autofix(self._bugs(), "file:t", self.repo, backend)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["kept"], 1)
        self.assertIn("fixed = True", Path(self.repo, "app.py").read_text())

    def test_low_confidence_reverted(self):
        from bugfixer import autofix
        backend = FakeBackend(self.repo, make_change=True, report_confidence="1")
        summary = autofix.run_autofix(self._bugs(), "file:t", self.repo, backend,
                                      min_confidence=0.95)
        self.assertEqual(summary["reverted"], 1)
        # Change was rolled back
        self.assertIn("fixed = False", Path(self.repo, "app.py").read_text())

    def test_no_change_fails(self):
        from bugfixer import autofix
        backend = FakeBackend(self.repo, make_change=False)
        summary = autofix.run_autofix(self._bugs(), "file:t", self.repo, backend)
        self.assertEqual(summary["failed"], 1)

    def test_dirty_tree_refused(self):
        from bugfixer import autofix
        Path(self.repo, "junk.txt").write_text("uncommitted")
        backend = FakeBackend(self.repo)
        summary = autofix.run_autofix(self._bugs(), "file:t", self.repo, backend)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["code"], "dirty_tree")

    def test_fixed_bug_skipped_on_rerun(self):
        from bugfixer import autofix
        backend = FakeBackend(self.repo, make_change=True, report_confidence="9")
        autofix.run_autofix(self._bugs(), "file:t", self.repo, backend)
        # Commit the kept fix so the tree is clean for round 2
        subprocess.run(["git", "add", "-A"], cwd=self.repo)
        subprocess.run(["git", "commit", "-qm", "fix"], cwd=self.repo)
        summary = autofix.run_autofix(self._bugs(), "file:t", self.repo, backend)
        self.assertEqual(summary["skipped"], 1)


# ── Chat engine ────────────────────────────────────────────────

class TestChat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p1 = patch("bugfixer.buglist.LIST_PATH", Path(self.tmp) / "ledger.json")
        self.p2 = patch("bugfixer.chat.SESSION_PATH", Path(self.tmp) / "chat.json")
        self.p1.start(); self.p2.start()
        from bugfixer import chat
        self.chat = chat

    def tearDown(self):
        self.p1.stop(); self.p2.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_help(self):
        out = self.chat.handle_message("help")
        self.assertIn("fix all confident", out["reply"])
        self.assertIsNone(out["action"])

    def test_load_file_then_fix_all(self):
        xlsx = os.path.join(self.tmp, "bugs.xlsx")
        make_xlsx(xlsx, [["ID", "Title"], ["1", "Broken navbar on mobile"]])
        out = self.chat.handle_message(f"load {xlsx}")
        self.assertIn("Loaded 1 open bug", out["reply"])
        out = self.chat.handle_message("fix all confident")
        self.assertEqual(out["action"]["type"], "auto_fix")
        self.assertTrue(out["action"]["file"].endswith("bugs.xlsx"))

    def test_fix_one(self):
        from bugfixer import buglist
        buglist.sync("file:x", [{"iid": "5", "title": "Header overlaps content",
                                 "labels": [], "web_url": ""}])
        out = self.chat.handle_message("fix #5")
        self.assertEqual(out["action"]["type"], "fix_one")
        self.assertEqual(out["action"]["iid"], "5")

    def test_unknown_bug(self):
        out = self.chat.handle_message("fix #999")
        self.assertIsNone(out["action"])
        self.assertIn("don't have", out["reply"])

    def test_set_threshold_and_status(self):
        out = self.chat.handle_message("set threshold 0.85")
        self.assertIn("0.85", out["reply"])
        out = self.chat.handle_message("fix everything")
        self.assertEqual(out["action"]["min_confidence"], 0.85)

    def test_skip(self):
        from bugfixer import buglist
        buglist.sync("file:x", [{"iid": "3", "title": "Minor typo in footer",
                                 "labels": [], "web_url": ""}])
        out = self.chat.handle_message("skip #3")
        self.assertIn("Skipped", out["reply"])
        self.assertEqual(buglist.list_bugs(status="skipped")[0]["iid"], "3")

    def test_unknown_message_offline(self):
        with patch("bugfixer.chat._ai_intent", return_value={}):
            out = self.chat.handle_message("what's the weather")
        self.assertIn("didn't catch", out["reply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
