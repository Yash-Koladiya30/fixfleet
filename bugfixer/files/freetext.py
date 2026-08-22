"""Extract bugs from free-form text (Word paragraphs, PDF text).

Heuristics first: numbered items ("1. crash on login"), "Bug:"/"Issue:"
headings, or "BUG-123"-style ids at line start. If nothing matches and an
OpenAI-compatible API backend is configured, one AI call splits the text
into bugs.
"""

import json as _json
import re

# Line starts a new bug: "1. Title", "1) Title", "Bug: Title", "Bug 3 - Title",
# "Issue: Title", "#12 Title", "BUG-123: Title"
_BUG_START = re.compile(
    r"^\s*(?:"
    r"(?P<num>\d{1,3})[.)]\s+"
    r"|(?:bug|issue|defect)\s*(?P<num2>\d{0,4})\s*[:\-–]\s*"
    r"|#(?P<num3>\d{1,5})\s+"
    r"|(?P<key>[A-Z][A-Z0-9]+-\d+)\s*[:\-–]?\s*"
    r")(?P<title>.+)$",
    re.IGNORECASE,
)

_SECTION_HINT = re.compile(
    r"^\s*(steps|expected|actual|environment|priority|severity)\b", re.IGNORECASE)


def _heuristic_split(text: str, source_label: str) -> list:
    bugs: list = []
    current: dict = None
    body_lines: list = []

    def flush():
        nonlocal current, body_lines
        if current:
            current["description"] = "\n".join(body_lines).strip()
            bugs.append(current)
        current, body_lines = None, []

    for line in text.splitlines():
        m = _BUG_START.match(line)
        # A numbered line restarting at 1 right under a "Steps:"-style header is
        # a reproduction sub-step, not a new bug. Bug numbering continues the
        # sequence (next bug = count+1), so those still match.
        if (m and m.group("num") and body_lines
                and _SECTION_HINT.match(body_lines[-1] or "")
                and m.group("num") != str(len(bugs) + (2 if current else 1))):
            m = None
        if m and len(m.group("title").strip()) >= 8:
            flush()
            iid = (m.group("num") or m.group("num2") or m.group("num3")
                   or m.group("key") or str(len(bugs) + 1))
            current = {
                "iid": iid,
                "title": m.group("title").strip()[:200],
                "labels": ["Bug"],
                "created_at": "", "updated_at": "",
                "web_url": f"{source_label}#bug{len(bugs) + 1}",
                "author": {"username": ""},
            }
        elif current is not None:
            body_lines.append(line.rstrip())
    flush()
    return bugs


def _ai_extract(text: str, source_label: str) -> list:
    from .. import config
    cfg = (config.load().get("api") or {})
    if not (cfg.get("base_url") and cfg.get("model")):
        return []

    from ..backends.registry import build_api_backend
    backend = build_api_backend(
        base_url=cfg["base_url"], api_key=cfg.get("api_key", ""),
        model=cfg["model"], apply_diff=False,
    )
    prompt = (
        "Extract every distinct bug report from this document. Reply with ONLY "
        "a JSON array; each item: {\"title\": str, \"description\": str}. "
        "Skip anything already marked fixed/closed.\n\n---\n"
        + text[:12000]
    )
    try:
        result = backend.run(prompt, project_dir=".", timeout=120)
        m = re.search(r"\[.*\]", result.stdout or "", re.DOTALL)
        if not m:
            return []
        items = _json.loads(m.group(0))
    except Exception:
        return []

    bugs = []
    for i, item in enumerate(items, 1):
        title = str((item or {}).get("title", "")).strip()
        if not title:
            continue
        bugs.append({
            "iid": str(i),
            "title": title[:200],
            "description": str(item.get("description", "")).strip(),
            "labels": ["Bug"],
            "created_at": "", "updated_at": "",
            "web_url": f"{source_label}#bug{i}",
            "author": {"username": ""},
        })
    return bugs


def extract_bugs_from_text(text: str, source_label: str) -> list:
    if not (text or "").strip():
        return []
    bugs = _heuristic_split(text, source_label)
    if bugs:
        return bugs
    return _ai_extract(text, source_label)
