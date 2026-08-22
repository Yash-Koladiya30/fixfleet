"""Bug triage — act as a senior QA engineer before any fix runs.

Answers two questions per reported item:
  1. Is this actually a BUG (vs feature request / question / task)?
  2. Does it belong to THIS project (do its files/symbols/terms exist here)?

Verdicts: "bug" (fix it), "not_a_bug", "not_relevant", "unclear" (fix, but
flag). Classification is heuristic-first; when an OpenAI-compatible API
backend is configured, one batched AI call refines the verdicts.
"""

import json as _json
import re

from .locator import extract_signals, rank_candidate_files
from .parser import parse_issue

# Phrases that signal a non-bug work item.
_FEATURE_RE = re.compile(
    r"\b(feature request|enhancement|add support|please add|would be (nice|great)|"
    r"can you add|new feature|improvement|suggestion|proposal|request:)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"\b(how (do|to|can) (i|we)|question:|is it possible|what is the)\b",
    re.IGNORECASE,
)
_BUG_SIGNAL_RE = re.compile(
    r"\b(crash|error|exception|fail|broken|freeze|hang|wrong|incorrect|"
    r"doesn'?t work|not working|traceback|stack ?trace|regression|leak|"
    r"unexpected|corrupt|500|404|npe|nullpointer|segfault)\b",
    re.IGNORECASE,
)

QA_SYSTEM_PROMPT = (
    "You are a senior QA engineer triaging a bug list before automated fixing. "
    "For each item decide: is it a genuine software BUG (defect in existing "
    "behavior), and does it plausibly belong to the given project? "
    "Feature requests, questions, tasks, and vague complaints are NOT bugs. "
    "Items referencing screens, files, or components that clearly don't exist "
    "in this project are NOT relevant."
)


def _heuristic_verdict(bug: dict, candidates: list, has_signals: bool) -> tuple:
    """Return (verdict, kind, reason) from cheap local signals.

    verdict: "proceed" | "not_relevant" — feature requests and suggestions
    PROCEED too (they get implemented); only wrong-project items are stopped
    here. Whether something is truly "not a bug" is decided later, by the AI
    actually inspecting the code.
    """
    text = f"{bug.get('title', '')}\n{bug.get('description', '')}"

    # Relevance: the issue mentioned concrete files/symbols but NONE exist here.
    if has_signals and not candidates:
        return "not_relevant", "bug", "mentions files/components not found in this project"

    if _FEATURE_RE.search(text) and not _BUG_SIGNAL_RE.search(text):
        return "proceed", "enhancement", "suggestion/feature request — will implement it"
    if _QUESTION_RE.search(text) and not _BUG_SIGNAL_RE.search(text):
        return "proceed", "enhancement", "reads like a request — will attempt it"
    return "proceed", "bug", ""


def _ai_refine(items: list, project_hint: str) -> dict:
    """One batched AI call. Returns {index: {"verdict":..., "reason":...}} or {}."""
    from . import config
    cfg = (config.load().get("api") or {})
    if not (cfg.get("base_url") and cfg.get("model")):
        return {}
    from .backends.registry import build_api_backend
    backend = build_api_backend(base_url=cfg["base_url"],
                                api_key=cfg.get("api_key", ""),
                                model=cfg["model"], apply_diff=False)
    listing = _json.dumps(items, default=str)[:9000]
    prompt = (
        f"{QA_SYSTEM_PROMPT}\n\nProject context: {project_hint}\n\n"
        f"Items (JSON):\n{listing}\n\n"
        'Reply with ONLY a JSON array, one object per item, in order: '
        '{"verdict": "bug|not_a_bug|not_relevant|unclear", "reason": "<short, user-friendly>"}'
    )
    try:
        result = backend.run(prompt, project_dir=".", timeout=90)
        m = re.search(r"\[.*\]", result.stdout or "", re.DOTALL)
        arr = _json.loads(m.group(0)) if m else []
        out = {}
        for i, v in enumerate(arr):
            verdict = str((v or {}).get("verdict", "")).strip()
            if verdict in ("bug", "not_a_bug", "not_relevant", "unclear"):
                out[i] = {"verdict": verdict,
                          "reason": str(v.get("reason", ""))[:140]}
        return out
    except Exception:
        return {}


def triage(bugs: list, project_dir: str, use_ai: bool = True) -> list:
    """Classify each item. Returns [{verdict, kind, reason, candidates}].

    verdict "proceed" → work on it (kind "bug" fixes, "enhancement" implements);
    verdict "not_relevant" → skip + alert the user.
    """
    results = []
    ai_items = []
    for b in bugs:
        parsed = parse_issue(b)
        signals = extract_signals(parsed)
        has_signals = bool(signals["files"] or signals["frames"] or signals["symbols"])
        candidates = rank_candidate_files(project_dir, signals, max_files=3)
        verdict, kind, reason = _heuristic_verdict(b, candidates, has_signals)
        results.append({"verdict": verdict, "kind": kind, "reason": reason,
                        "candidates": candidates})
        ai_items.append({
            "title": b.get("title", "")[:150],
            "description": (b.get("description") or "")[:400],
            "matching_project_files": candidates,
        })

    # Optional AI pass refines RELEVANCE only (never blocks work items).
    if use_ai and any(r["verdict"] == "not_relevant" for r in results):
        refined = _ai_refine(ai_items, project_hint=project_dir)
        for i, r in enumerate(results):
            ai = refined.get(i)
            if not ai:
                continue
            # AI can rescue a heuristic not_relevant back to proceed, or confirm it.
            if r["verdict"] == "not_relevant" and ai["verdict"] == "bug":
                r["verdict"] = "proceed"
                r["reason"] = ""
            elif ai["verdict"] == "not_relevant":
                r["verdict"] = "not_relevant"
                if ai["reason"]:
                    r["reason"] = ai["reason"]
    return results
