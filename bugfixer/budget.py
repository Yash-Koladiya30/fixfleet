"""Token budget — slim long sections, estimate cost, enforce caps.

Estimation is heuristic (1 token ≈ 4 chars for English text). Good enough for
warning users before they blow through a paid plan; not for billing accuracy.
"""

from dataclasses import dataclass


# ── Section caps (chars) ───────────────────────────────────────

DEFAULT_CAPS = {
    "title": 300,
    "description": 2500,
    "steps": 1500,
    "expected": 500,
    "actual": 800,
    "environment": 600,
    "logs": 2000,
    "notes": 800,
    "raw_description": 4000,
    "inline_file": 8000,  # inlined candidate file content
}


# ── Token cost rates (per backend, output:input ratio) ─────────

# Multiplier estimates how many tokens get consumed per input token across the
# whole agentic loop (reads, edits, retries). Pure-API backend = ~1.5; agentic
# CLI = 3-4 because of tool-use round-trips.
BACKEND_LOOP_MULTIPLIER = {
    "claude": 4.0,
    "codex": 4.0,
    "gemini": 3.5,
    "qwen": 3.5,
    "cursor": 3.5,
    "aider": 2.5,
    "openai_compat": 1.5,  # diff-only, no loop
}


# ── Default budgets ────────────────────────────────────────────

DEFAULT_BUDGETS = {
    "session_max_tokens": 200_000,
    "per_issue_max_tokens": 30_000,
    "daily_max_tokens": 500_000,
}


# ── Public helpers ─────────────────────────────────────────────

def slim(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    cut = max_chars
    return text[:cut].rstrip() + f"\n\n[...truncated {len(text) - cut} chars to save tokens...]"


def estimate_tokens(text: str) -> int:
    """Rough token count: 4 chars per token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_total_cost(prompt: str, backend_name: str) -> int:
    """Estimate total tokens consumed for one issue on the given backend."""
    base = estimate_tokens(prompt)
    mult = BACKEND_LOOP_MULTIPLIER.get(backend_name, 3.0)
    return int(base * mult)


@dataclass
class BudgetCheck:
    allowed: bool
    estimated: int
    session_used: int
    session_max: int
    per_issue_max: int
    daily_used: int
    daily_max: int
    reason: str = ""


def check_budget(prompt: str, backend_name: str,
                 session_used: int, daily_used: int,
                 budgets: dict = None) -> BudgetCheck:
    b = {**DEFAULT_BUDGETS, **(budgets or {})}
    estimated = estimate_total_cost(prompt, backend_name)

    reasons: list = []
    if estimated > b["per_issue_max_tokens"]:
        reasons.append(
            f"per-issue cap exceeded ({estimated:,} > {b['per_issue_max_tokens']:,})"
        )
    if session_used + estimated > b["session_max_tokens"]:
        reasons.append(
            f"session cap would be exceeded "
            f"({session_used + estimated:,} > {b['session_max_tokens']:,})"
        )
    if daily_used + estimated > b["daily_max_tokens"]:
        reasons.append(
            f"daily cap would be exceeded "
            f"({daily_used + estimated:,} > {b['daily_max_tokens']:,})"
        )

    return BudgetCheck(
        allowed=not reasons,
        estimated=estimated,
        session_used=session_used,
        session_max=b["session_max_tokens"],
        per_issue_max=b["per_issue_max_tokens"],
        daily_used=daily_used,
        daily_max=b["daily_max_tokens"],
        reason="; ".join(reasons),
    )
