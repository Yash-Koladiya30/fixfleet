"""Bug locator — pre-narrow the search space before invoking the LLM.

Extracts file paths, function names, error classes, and stack frames from a
parsed issue, then ranks candidate files in the project. The goal is to give
the model a strong starting point so it doesn't waste tokens grepping the
whole repo.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .parser import ParsedIssue


# ── Regex patterns ─────────────────────────────────────────────

FILE_RE = re.compile(
    r"\b([\w./-]+\.(?:py|js|ts|tsx|jsx|mjs|cjs|java|go|rb|php|rs|cpp|cc|c|h|hpp|kt|swift|scala|cs|vue|svelte|sql|sh|bash|zsh|yml|yaml|json|toml|md))\b"
)

# Python:  File "path/to/file.py", line 42, in func_name
PY_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')

# JS/Node: at func (path:line:col)  OR  at path:line:col
JS_FRAME_RE = re.compile(r"at\s+(?:(\S+)\s+\()?([^():\s]+\.(?:js|ts|tsx|jsx|mjs|cjs)):(\d+):\d+\)?")

# Java:    at pkg.Class.method(File.java:42)
JAVA_FRAME_RE = re.compile(r"at\s+[\w.$<>]+\(([^:)]+\.java):(\d+)\)")

# Go:      file.go:42 +0x1234
GO_FRAME_RE = re.compile(r"([\w./-]+\.go):(\d+)")

# Swift/Xcode: path/File.swift:42:18: error: Extra trailing closure passed in call
SWIFT_DIAGNOSTIC_RE = re.compile(
    r"(?m)^([\w./ -]+\.swift):(\d+):(?:(\d+):)?\s*"
    r"(error|warning|note):\s*(.+)$"
)

# Identifiers in backticks or CamelCase classes / SCREAMING_SNAKE_CASE
SYMBOL_RE = re.compile(
    r"`([A-Za-z_][\w.]*)`"
    r"|\b([A-Z][a-zA-Z0-9_]*(?:Error|Exception|Service|Controller|Model|View|Handler|Manager|Provider))\b"
    r"|\b([A-Z_][A-Z0-9_]{3,})\b"
)


# ── Skip directories / extensions ──────────────────────────────

IGNORE_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist",
    "build", ".next", ".nuxt", "target", "vendor", ".gradle", ".idea",
    ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
}


@dataclass
class LocatorResult:
    files_mentioned: list = field(default_factory=list)
    stack_frames: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    candidates: list = field(default_factory=list)        # ranked file paths
    top_inline: dict = field(default_factory=dict)        # {"path": ..., "content": ...}

    @property
    def has_hints(self) -> bool:
        return bool(self.files_mentioned or self.stack_frames or self.symbols or self.candidates)


# ── Signal extraction ──────────────────────────────────────────

def _gather_text(issue: ParsedIssue) -> str:
    """Concatenate searchable fields. Use parsed sections if any exist; otherwise
    fall back to raw_description (which would contain everything anyway)."""
    parts = [issue.title or ""]
    parsed_sections = [
        issue.description, issue.steps, issue.expected, issue.actual,
        issue.environment, issue.logs, issue.notes,
    ]
    if any(s for s in parsed_sections):
        parts.extend(s or "" for s in parsed_sections)
    else:
        parts.append(issue.raw_description or "")
    return "\n".join(parts)


def extract_signals(issue: ParsedIssue) -> dict:
    blob = _gather_text(issue)

    files = sorted(set(FILE_RE.findall(blob)))

    frames: list = []
    for m in PY_FRAME_RE.finditer(blob):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "func": m.group(3), "lang": "python"})
    for m in JS_FRAME_RE.finditer(blob):
        frames.append({"file": m.group(2), "line": int(m.group(3)), "func": m.group(1) or "", "lang": "js"})
    for m in JAVA_FRAME_RE.finditer(blob):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "func": "", "lang": "java"})
    for m in GO_FRAME_RE.finditer(blob):
        frames.append({"file": m.group(1), "line": int(m.group(2)), "func": "", "lang": "go"})
    for m in SWIFT_DIAGNOSTIC_RE.finditer(blob):
        frames.append({
            "file": m.group(1).strip(),
            "line": int(m.group(2)),
            "column": int(m.group(3)) if m.group(3) else None,
            "func": m.group(5).strip(),
            "lang": "swift",
            "severity": m.group(4),
        })

    sym_set: set = set()
    for tup in SYMBOL_RE.findall(blob):
        for s in tup:
            if s and len(s) >= 3 and not _is_common_word(s):
                sym_set.add(s)
    symbols = sorted(sym_set)

    # Dedupe frames (same blob may contain both raw_description and parsed sections)
    seen: set = set()
    unique_frames: list = []
    for fr in frames:
        key = (fr.get("file"), fr.get("line"), fr.get("func"))
        if key in seen:
            continue
        seen.add(key)
        unique_frames.append(fr)

    return {"files": files, "frames": unique_frames, "symbols": symbols}


_COMMON_SYMBOLS = {
    "ERROR", "WARNING", "INFO", "DEBUG", "TODO", "FIXME", "NOTE",
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "HTTP", "HTTPS",
    "JSON", "XML", "HTML", "CSS", "URL", "URI", "API", "REST", "SQL",
    "TRUE", "FALSE", "NULL", "NONE", "USER", "TYPE", "DATA",
}


def _is_common_word(s: str) -> bool:
    return s.upper() in _COMMON_SYMBOLS


# ── File ranking ───────────────────────────────────────────────

def _has_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _ripgrep_files(project_dir: str, pattern: str, max_count: int = 20) -> list:
    try:
        result = subprocess.run(
            ["rg", "--files-with-matches", "-w", "--max-count", "3", pattern],
            cwd=project_dir, capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        return result.stdout.splitlines()[:max_count]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _python_grep_files(project_dir: str, pattern: str, max_count: int = 20) -> list:
    """Pure-Python fallback when ripgrep is missing. Slow on big repos but always works."""
    pat = re.compile(rf"\b{re.escape(pattern)}\b")
    matched: list = []
    root = Path(project_dir)
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if any(p in IGNORE_DIRS for p in f.parts):
            continue
        if f.stat().st_size > 1_000_000:  # skip > 1MB files
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        if pat.search(text):
            matched.append(str(f.relative_to(root)))
            if len(matched) >= max_count:
                break
    return matched


def rank_candidate_files(project_dir: str, signals: dict, max_files: int = 5) -> list:
    """Score files by overlap with signals. Return top N relative paths."""
    project = Path(project_dir)
    if not project.is_dir():
        return []

    scores: dict = {}

    # Direct file mentions: highest weight
    for fname in signals.get("files", []):
        normalized = fname.lstrip("./")
        for hit in project.rglob(normalized):
            if any(p in IGNORE_DIRS for p in hit.parts):
                continue
            try:
                rel = str(hit.relative_to(project))
            except ValueError:
                continue
            scores[rel] = scores.get(rel, 0) + 12

    # Stack frame files: highest weight
    for frame in signals.get("frames", []):
        ffile = frame.get("file", "")
        if not ffile:
            continue
        # Stack frames may have absolute paths; try the basename too
        basename = Path(ffile).name
        for hit in project.rglob(basename):
            if any(p in IGNORE_DIRS for p in hit.parts):
                continue
            try:
                rel = str(hit.relative_to(project))
            except ValueError:
                continue
            scores[rel] = scores.get(rel, 0) + 15

    # Symbol search via ripgrep (or python fallback)
    use_rg = _has_ripgrep()
    for sym in signals.get("symbols", [])[:10]:
        files = _ripgrep_files(project_dir, sym) if use_rg else _python_grep_files(project_dir, sym)
        for f in files:
            scores[f] = scores.get(f, 0) + 3

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [f for f, _ in ranked[:max_files]]


# ── Inline top candidate ───────────────────────────────────────

def inline_top_file(project_dir: str, candidates: list, max_lines: int = 250) -> dict:
    """Read the top-ranked file so the model doesn't burn tokens reading it."""
    if not candidates:
        return {}
    rel = candidates[0]
    path = Path(project_dir) / rel
    if not path.is_file():
        return {}
    try:
        text = path.read_text(errors="ignore")
    except Exception:
        return {}

    lines = text.splitlines()
    if len(lines) > max_lines:
        head = lines[: max_lines // 2]
        tail = lines[-(max_lines // 2):]
        elided = len(lines) - len(head) - len(tail)
        text = "\n".join(head + [f"... [{elided} lines elided] ..."] + tail)
    return {"path": rel, "content": text, "line_count": len(lines)}


# ── Public entrypoint ──────────────────────────────────────────

def locate(issue: ParsedIssue, project_dir: str,
           max_candidates: int = 5,
           inline_top: bool = True) -> LocatorResult:
    signals = extract_signals(issue)
    candidates = rank_candidate_files(project_dir, signals, max_files=max_candidates)
    top_inline = inline_top_file(project_dir, candidates) if inline_top else {}

    return LocatorResult(
        files_mentioned=signals["files"],
        stack_frames=signals["frames"],
        symbols=signals["symbols"],
        candidates=candidates,
        top_inline=top_inline,
    )
