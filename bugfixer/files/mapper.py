"""Map arbitrary spreadsheet/table columns to canonical bug fields.

Strategy: heuristic header matching first (free, offline). If no title-like
column can be found, optionally fall back to the configured OpenAI-compatible
API backend to map headers (one small AI call per file).
"""

import json as _json
import re

# canonical field -> header synonyms (normalized: lowercase, alnum+space only)
_SYNONYMS = {
    "iid": ["id", "no", "number", "sr", "sr no", "srno", "bug id", "bugid",
            "issue id", "ticket", "ticket id", "key", "#"],
    "title": ["title", "summary", "subject", "bug", "bug title", "name",
              "issue", "issue title", "defect", "defect title", "problem"],
    "description": ["description", "desc", "details", "detail", "issue description",
                    "bug description", "notes", "note", "comment", "comments",
                    "observation", "remarks"],
    "steps": ["steps", "steps to reproduce", "repro", "repro steps",
              "reproduction", "how to reproduce", "scenario"],
    "expected": ["expected", "expected result", "expected behavior",
                 "expected behaviour", "expected output"],
    "actual": ["actual", "actual result", "actual behavior", "actual behaviour",
               "actual output", "current behavior", "current result"],
    "priority": ["priority", "severity", "sev", "impact", "level"],
    "status": ["status", "state", "bug status", "resolution", "fixed"],
    "environment": ["environment", "env", "platform", "device", "os", "browser",
                    "version", "build"],
    "author": ["author", "reporter", "reported by", "raised by", "created by",
               "tester", "found by", "owner"],
    "created_at": ["created", "created at", "date", "created date", "reported on",
                   "date reported", "logged on"],
}

# statuses meaning "already done — skip this row"
CLOSED_STATUSES = {
    "fixed", "closed", "done", "resolved", "complete", "completed",
    "verified", "rejected", "duplicate", "wont fix", "wontfix", "invalid",
    "not a bug", "na", "n/a",
}

PRIORITY_MAP = {
    "critical": "High", "blocker": "High", "highest": "High", "high": "High",
    "p0": "High", "p1": "High", "1": "High", "urgent": "High", "major": "High",
    "medium": "Medium", "p2": "Medium", "2": "Medium", "normal": "Medium",
    "moderate": "Medium",
    "low": "Low", "lowest": "Low", "minor": "Low", "trivial": "Low",
    "p3": "Low", "p4": "Low", "3": "Low", "4": "Low",
}


def _norm(header: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (header or "").strip().lower())
    return re.sub(r"\s+", " ", s).strip()


def map_headers(headers: list) -> dict:
    """Heuristic header mapping. Returns {canonical_field: column_index}."""
    mapping: dict = {}
    normed = [_norm(h) for h in headers]

    # Exact synonym match first, then substring match — first hit wins per field.
    for field, synonyms in _SYNONYMS.items():
        for i, h in enumerate(normed):
            if i in mapping.values():
                continue
            if h in synonyms:
                mapping[field] = i
                break
        if field in mapping:
            continue
        for i, h in enumerate(normed):
            if i in mapping.values() or not h:
                continue
            if any(syn in h for syn in synonyms if len(syn) > 3):
                mapping[field] = i
                break
    return mapping


def map_headers_with_ai(headers: list, sample_rows: list) -> dict:
    """AI fallback — asks the configured OpenAI-compatible backend to map
    columns. Returns {} if no API backend is configured or the call fails."""
    from .. import config
    cfg = (config.load().get("api") or {})
    if not (cfg.get("base_url") and cfg.get("model")):
        return {}

    from ..backends.registry import build_api_backend
    backend = build_api_backend(
        base_url=cfg["base_url"], api_key=cfg.get("api_key", ""),
        model=cfg["model"], apply_diff=False,
    )
    fields = list(_SYNONYMS.keys())
    prompt = (
        "Map spreadsheet columns to bug-report fields. Columns (0-indexed):\n"
        f"{_json.dumps(list(headers))}\n"
        f"Sample rows:\n{_json.dumps(sample_rows[:3], default=str)[:1500]}\n\n"
        f"Reply with ONLY a JSON object mapping any of {fields} "
        "to a column index. Omit fields with no matching column."
    )
    try:
        result = backend.run(prompt, project_dir=".", timeout=60)
        m = re.search(r"\{[^{}]*\}", result.stdout or "")
        if not m:
            return {}
        raw = _json.loads(m.group(0))
        return {k: int(v) for k, v in raw.items()
                if k in _SYNONYMS and isinstance(v, (int, str)) and str(v).isdigit()
                and int(v) < len(headers)}
    except Exception:
        return {}


def rows_to_bugs(headers: list, rows: list, source_label: str,
                 allow_ai: bool = True) -> list:
    """Convert a header row + data rows into unified bug dicts.

    Skips rows whose status column marks them already closed/fixed.
    Raises ValueError when no title-like column can be identified.
    """
    mapping = map_headers(headers)
    if "title" not in mapping and allow_ai:
        ai_map = map_headers_with_ai(headers, rows)
        for k, v in ai_map.items():
            mapping.setdefault(k, v)
    if "title" not in mapping:
        # Last resort: single-column sheet → treat it as titles.
        non_empty_cols = {i for row in rows for i, c in enumerate(row) if str(c).strip()}
        if len(non_empty_cols) == 1:
            mapping["title"] = non_empty_cols.pop()
        else:
            raise ValueError(
                "Could not identify a title/summary column. "
                f"Headers found: {headers}. Rename one column to 'Title' or "
                "configure an API backend so AI column-mapping can run."
            )

    def cell(row, field):
        idx = mapping.get(field)
        if idx is None or idx >= len(row):
            return ""
        return str(row[idx]).strip()

    bugs = []
    seq = 0
    for row in rows:
        title = cell(row, "title")
        if not title:
            continue
        status = _norm(cell(row, "status"))
        if status in CLOSED_STATUSES:
            continue
        seq += 1
        iid = cell(row, "iid") or str(seq)
        labels = ["Bug"]
        pr = _norm(cell(row, "priority"))
        if pr in PRIORITY_MAP:
            labels.append(PRIORITY_MAP[pr])

        # Compose a markdown description so the existing parser extracts sections.
        parts = []
        if cell(row, "description"):
            parts.append(cell(row, "description"))
        for fld, heading in (("steps", "Steps to Reproduce"),
                             ("expected", "Expected Behavior"),
                             ("actual", "Actual Behavior"),
                             ("environment", "Environment")):
            v = cell(row, fld)
            if v:
                parts.append(f"## {heading}\n{v}")
        bugs.append({
            "iid": iid,
            "title": title,
            "description": "\n\n".join(parts),
            "labels": labels,
            "created_at": cell(row, "created_at"),
            "updated_at": "",
            "web_url": f"{source_label}#row{seq}",
            "author": {"username": cell(row, "author")},
        })
    return bugs
