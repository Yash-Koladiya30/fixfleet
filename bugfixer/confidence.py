"""Confidence scoring — combine model self-rating with diff metrics.

Sources of signal:
  1. FIX REPORT block in stdout (model self-rating + root cause)
  2. git diff inside project_dir (objective: lines changed, files changed)
  3. Hedge-word density in stdout (overrides self-rating when high)
  4. Relevance of changed files vs issue keywords / candidate list
"""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ── Patterns ───────────────────────────────────────────────────

REPORT_RE = re.compile(
    r"===\s*FIX REPORT\s*===\s*\n"
    r"(.*?)"
    r"(?:===\s*END FIX REPORT\s*===|\Z)",
    re.DOTALL | re.IGNORECASE,
)

FIELD_RE = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.+?)\s*$", re.MULTILINE)

HEDGE_WORDS = [
    "maybe", "might", "perhaps", "possibly", "i think",
    "not sure", "unsure", "i guess", "probably", "likely",
    "i'm not sure", "could be", "may be", "tentative",
]

HEDGE_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in HEDGE_WORDS) + r")\b", re.IGNORECASE)


# ── Result ─────────────────────────────────────────────────────

@dataclass
class ConfidenceResult:
    final_score: float = 0.0  # 0..1
    self_rating: int = 0      # 0..10 (0 = not provided)
    root_cause: str = ""
    files_changed: list = field(default_factory=list)
    lines_changed: int = 0
    hedge_density: float = 0.0
    diff_focus: float = 0.0   # 0..1
    file_relevance: float = 0.0  # 0..1
    tests_run: str = "unknown"
    notes: list = field(default_factory=list)

    def label(self) -> str:
        s = self.final_score
        if s >= 0.80:
            return "High"
        if s >= 0.55:
            return "Medium"
        if s >= 0.30:
            return "Low"
        return "Very Low"


# ── Parsing ────────────────────────────────────────────────────

def parse_fix_report(stdout: str) -> dict:
    if not stdout:
        return {}

    block_match = REPORT_RE.search(stdout)
    if block_match:
        block = block_match.group(1)
    else:
        # Fallback: scan whole stdout for known fields.
        block = stdout

    fields: dict = {}
    for m in FIELD_RE.finditer(block):
        key = m.group(1).strip().upper()
        val = m.group(2).strip()
        fields[key] = val
    return fields


def hedge_density(stdout: str) -> float:
    if not stdout:
        return 0.0
    matches = HEDGE_RE.findall(stdout)
    words = max(1, len(stdout.split()))
    return min(1.0, len(matches) / max(words / 100, 1))


def git_diff_stats(project_dir: str) -> dict:
    """Return {files: [paths], lines_added: int, lines_removed: int}."""
    project = Path(project_dir)
    if not (project / ".git").exists():
        return {"files": [], "lines_added": 0, "lines_removed": 0, "is_git": False}

    try:
        # Both staged and unstaged
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--numstat"],
            cwd=project_dir, capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"files": [], "lines_added": 0, "lines_removed": 0, "is_git": True}

    files: list = []
    added = removed = 0
    for line in diff.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, r, path = parts
        try:
            added += int(a) if a != "-" else 0
            removed += int(r) if r != "-" else 0
        except ValueError:
            pass
        files.append(path)

    return {
        "files": files,
        "lines_added": added,
        "lines_removed": removed,
        "is_git": True,
    }


# ── Sub-scores ─────────────────────────────────────────────────

def diff_focus_score(diff_stats: dict) -> float:
    """Smaller, focused diff = higher score. Empty diff = 0."""
    if not diff_stats.get("is_git"):
        return 0.5  # unknown, neutral
    files = diff_stats.get("files", [])
    if not files:
        return 0.0
    total = diff_stats.get("lines_added", 0) + diff_stats.get("lines_removed", 0)
    if total == 0:
        return 0.0
    # 1.0 for ≤20 lines / 1-2 files; falls off
    size_score = max(0.0, min(1.0, 1.0 - (total - 20) / 480))
    file_score = max(0.0, min(1.0, 1.0 - (len(files) - 2) / 8))
    return 0.6 * size_score + 0.4 * file_score


def file_relevance_score(diff_stats: dict, candidate_files: list, issue_keywords: list) -> float:
    """Did the fix touch files we already identified as candidates / matching keywords?"""
    files = diff_stats.get("files", [])
    if not files:
        return 0.0

    candidates_norm = {Path(c).as_posix().lower() for c in (candidate_files or [])}
    keywords_norm = [k.lower() for k in (issue_keywords or []) if k]

    hits = 0
    for f in files:
        fp = Path(f).as_posix().lower()
        if any(c in fp or fp in c for c in candidates_norm):
            hits += 1
            continue
        if any(k in fp for k in keywords_norm):
            hits += 1
    return min(1.0, hits / len(files))


def parse_self_rating(fields: dict) -> int:
    raw = fields.get("CONFIDENCE", "")
    m = re.search(r"(\d+)\s*(?:/\s*10)?", raw or "")
    if not m:
        return 0
    n = int(m.group(1))
    return max(0, min(10, n))


# ── Public entrypoint ──────────────────────────────────────────

def evaluate(stdout: str, project_dir: str,
             candidate_files: list = None,
             issue_keywords: list = None) -> ConfidenceResult:
    fields = parse_fix_report(stdout)
    self_rating = parse_self_rating(fields)
    root_cause = fields.get("ROOT_CAUSE", "")
    tests_run = (fields.get("TESTS_RUN", "unknown") or "unknown").lower()

    diff = git_diff_stats(project_dir)
    files_changed = diff.get("files", [])
    lines_changed = diff.get("lines_added", 0) + diff.get("lines_removed", 0)

    hedge = hedge_density(stdout)
    focus = diff_focus_score(diff)
    relevance = file_relevance_score(diff, candidate_files or [], issue_keywords or [])

    # Tests sub-score
    if tests_run == "yes" or tests_run.startswith("pass"):
        tests_score = 1.0
    elif tests_run == "no":
        tests_score = 0.4
    elif tests_run == "n/a":
        tests_score = 0.6
    else:
        tests_score = 0.5

    # Weighted combo
    final = (
        0.30 * focus +
        0.20 * relevance +
        0.20 * (self_rating / 10.0 if self_rating else 0.5) +
        0.15 * (1.0 - hedge) +
        0.15 * tests_score
    )

    notes: list = []
    if not files_changed and diff.get("is_git"):
        notes.append("No files changed — fix may not have been applied.")
        final = min(final, 0.10)
    if not diff.get("is_git"):
        notes.append("Project is not a git repo — diff metrics unavailable.")
    if hedge > 0.05:
        notes.append(f"High hedge-word density ({hedge:.1%}) — model expressed uncertainty.")

    return ConfidenceResult(
        final_score=round(final, 3),
        self_rating=self_rating,
        root_cause=root_cause,
        files_changed=files_changed,
        lines_changed=lines_changed,
        hedge_density=round(hedge, 3),
        diff_focus=round(focus, 3),
        file_relevance=round(relevance, 3),
        tests_run=tests_run,
        notes=notes,
    )
