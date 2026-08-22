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

QA_SYSTEM_PROMPT = (
    "You are a senior QA engineer triaging a work-item list before automated "
    "fixing. For each item decide only RELEVANCE: does it plausibly belong to "
    "the given project? Items referencing screens, files, or components that "
    "clearly don't exist in this project are NOT relevant. Whether an item is "
    "a defect or a suggestion does not matter here — both are worked on."
)


def _heuristic_verdict(bug: dict, candidates: list, has_signals: bool) -> tuple:
    """Return (verdict, reason) — relevance gate only.

    Everything relevant PROCEEDS: the fixing AI itself understands whether an
    item is a defect, a suggestion (however phrased), or not actually a bug —
    no keyword guessing here. Only wrong-project items are stopped.
    """
    if has_signals and not candidates:
        return "not_relevant", "mentions files/components not found in this project"
    return "proceed", ""


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
        verdict, reason = _heuristic_verdict(b, candidates, has_signals)
        results.append({"verdict": verdict, "reason": reason,
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
