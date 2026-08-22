"""Auto-fix engine — fix bugs in bulk, keep only high-confidence results.

Flow per bug: run the AI backend → score confidence → if score >= threshold
and files actually changed, keep the edits; otherwise revert them so the
working tree is exactly as before. Requires a clean git tree at start so a
revert can never touch the user's own work.
"""

import subprocess
from dataclasses import dataclass, field

from . import budget, buglist, state, telemetry
from .confidence import evaluate as evaluate_confidence
from .locator import locate
from .parser import parse_issue
from .prompt import build_prompt

DEFAULT_MIN_CONFIDENCE = 0.70


# ── Git helpers ────────────────────────────────────────────────

def _git(project_dir: str, *args, timeout: int = 30):
    return subprocess.run(
        ["git", *args], cwd=project_dir,
        capture_output=True, text=True, timeout=timeout,
    )


def is_git_repo(project_dir: str) -> bool:
    try:
        return _git(project_dir, "rev-parse", "--is-inside-work-tree").returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def working_tree_clean(project_dir: str) -> bool:
    r = _git(project_dir, "status", "--porcelain")
    return r.returncode == 0 and not r.stdout.strip()


def changed_paths(project_dir: str) -> list:
    """Modified + untracked paths (porcelain format)."""
    r = _git(project_dir, "status", "--porcelain")
    paths = []
    for line in r.stdout.splitlines():
        if len(line) > 3:
            # Rename entries look like "R  old -> new"
            p = line[3:].split(" -> ")[-1].strip().strip('"')
            paths.append(p)
    return paths


def revert_changes(project_dir: str):
    """Restore tracked files and delete files the fix created.

    Only safe because auto-fix requires a clean tree before each fix —
    everything dirty at this point came from the fix being rejected.
    """
    _git(project_dir, "checkout", "--", ".")
    _git(project_dir, "clean", "-fd")


# ── Per-bug fix ────────────────────────────────────────────────

@dataclass
class AutoFixResult:
    key: str = ""
    iid: str = ""
    title: str = ""
    outcome: str = ""          # kept | reverted | failed | skipped
    confidence: float = 0.0
    confidence_label: str = ""
    files_changed: list = field(default_factory=list)
    reason: str = ""


def fix_one(bug: dict, source: str, project_dir: str, backend,
            min_confidence: float = DEFAULT_MIN_CONFIDENCE,
            locator_cfg: dict = None, kind: str = "bug") -> AutoFixResult:
    """Fix one bug (or implement one request); keep or revert based on
    confidence. Updates the ledger. If the model inspects the code and finds
    no defect, outcome is "not_a_bug" and nothing is changed."""
    key = buglist.bug_key(source, bug.get("iid"), bug.get("title", ""))
    res = AutoFixResult(key=key, iid=str(bug.get("iid")), title=bug.get("title", ""))

    entry = buglist.get(key)
    if entry and entry.get("status") in ("fixed", "duplicate"):
        res.outcome = "skipped"
        res.reason = f"already {entry['status']}"
        return res
    if not buglist.mark(key, "fixing") and entry:
        res.outcome = "skipped"
        res.reason = "another run is fixing this bug"
        return res

    if not working_tree_clean(project_dir):
        buglist.mark(key, "new")
        res.outcome = "failed"
        res.reason = "working tree not clean — commit or stash first"
        return res

    parsed = parse_issue(bug)
    lc = locator_cfg or {}
    loc = locate(parsed, project_dir,
                 max_candidates=int(lc.get("max_candidates", 5)),
                 inline_top=bool(lc.get("inline_top_file", True)))
    prompt = build_prompt(parsed, locator=loc, kind=kind)

    telemetry.track("fix_started", {"provider": "autofix", "backend": backend.name})
    result = backend.run(prompt, project_dir)

    conf = evaluate_confidence(
        result.stdout, project_dir,
        candidate_files=loc.candidates,
        issue_keywords=loc.symbols + loc.files_mentioned,
    )
    res.confidence = conf.final_score
    res.confidence_label = conf.label()
    res.files_changed = conf.files_changed

    check = budget.check_budget(prompt, backend.name, session_used=0,
                                daily_used=state.get_daily_usage(backend.name))

    # Model inspected the code and found no defect → report, change nothing.
    if conf.verdict == "not_a_bug" and not conf.files_changed and result.ok:
        res.outcome = "not_a_bug"
        res.reason = conf.reasoning or "checked the code — the reported behavior is correct"
        buglist.mark(key, "not_a_bug")
        state.record_usage(backend_name=backend.name, tokens=check.estimated,
                           project_id=source, issue_iid=bug.get("iid"), success=True)
        telemetry.track("fix_completed", {
            "provider": "autofix", "backend": backend.name, "success": True,
            "timed_out": False, "confidence": "not_a_bug", "files_changed": 0,
        })
        return res

    kept = (result.ok and conf.files_changed
            and conf.final_score >= min_confidence and not result.timed_out)

    if kept:
        res.outcome = "kept"
        buglist.mark(key, "fixed", confidence=conf.final_score)
    else:
        if changed_paths(project_dir):
            revert_changes(project_dir)
        res.outcome = "reverted" if conf.files_changed else "failed"
        res.reason = (
            "timed out" if result.timed_out
            else f"confidence {conf.final_score:.2f} below threshold {min_confidence:.2f}"
            if conf.files_changed
            else "backend made no changes"
        )
        buglist.mark(key, "failed", confidence=conf.final_score)

    state.record_usage(
        backend_name=backend.name, tokens=check.estimated,
        project_id=source, issue_iid=bug.get("iid"), success=kept,
    )
    telemetry.track("fix_completed", {
        "provider": "autofix", "backend": backend.name, "success": kept,
        "timed_out": result.timed_out, "confidence": conf.label(),
        "files_changed": len(conf.files_changed),
    })
    return res


def run_autofix(bugs: list, source: str, project_dir: str, backend,
                min_confidence: float = DEFAULT_MIN_CONFIDENCE,
                max_bugs: int = 0, locator_cfg: dict = None,
                progress=None) -> dict:
    """Fix a batch. Returns a summary dict. `progress(result)` is called after
    each bug when provided."""
    if not is_git_repo(project_dir):
        return {"ok": False, "code": "not_git_repo",
                "error": "Auto-fix needs a git repository — confidence reverts rely on git."}
    if not working_tree_clean(project_dir):
        return {"ok": False, "code": "dirty_tree",
                "error": "Working tree has uncommitted changes. Commit or stash first — "
                         "auto-fix must be able to revert low-confidence fixes safely."}

    buglist.sync(source, bugs)
    telemetry.track("auto_fix_run", {"count": len(bugs), "backend": backend.name})

    # QA triage gate — only genuine, project-relevant bugs get fixed. Items
    # judged not-a-bug or not-relevant are reported back as alerts instead.
    from .triage import triage as run_triage
    verdicts = run_triage(bugs, project_dir)
    alerts = []
    workable = []
    for bug, v in zip(bugs, verdicts):
        if v["verdict"] == "not_relevant":
            key = buglist.bug_key(source, bug.get("iid"), bug.get("title", ""))
            buglist.mark(key, "not_relevant")
            alerts.append({
                "iid": str(bug.get("iid")),
                "title": bug.get("title", "")[:80],
                "verdict": "not_relevant",
                "reason": v["reason"],
            })
        else:
            workable.append((bug, v))

    results = []
    for bug, v in workable:
        if max_bugs and len([r for r in results if r.outcome != "skipped"]) >= max_bugs:
            break
        r = fix_one(bug, source, project_dir, backend,
                    min_confidence=min_confidence, locator_cfg=locator_cfg,
                    kind=v.get("kind", "bug"))
        results.append(r)
        # Code-checked "no defect found" → surface to the user as an alert.
        if r.outcome == "not_a_bug":
            alerts.append({
                "iid": r.iid, "title": r.title[:80],
                "verdict": "not_a_bug", "reason": r.reason,
            })
        if progress:
            progress(r)

    kept = [r for r in results if r.outcome == "kept"]
    return {
        "ok": True,
        "total": len(results),
        "kept": len(kept),
        "reverted": len([r for r in results if r.outcome == "reverted"]),
        "failed": len([r for r in results if r.outcome == "failed"]),
        "skipped": len([r for r in results if r.outcome == "skipped"]),
        "not_a_bug": len([r for r in results if r.outcome == "not_a_bug"]),
        "alerts": alerts,
        "min_confidence": min_confidence,
        "results": [r.__dict__ for r in results],
    }
