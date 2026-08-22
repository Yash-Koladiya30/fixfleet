"""Unified bug list — one local ledger across all sources (trackers + files).

Solves three problems:
  - Stable identity: every bug gets a key derived from (source, iid, title),
    so re-importing the same file or re-fetching the tracker doesn't duplicate.
  - Duplicate detection: the same bug arriving from two sources (e.g. the
    Excel sheet AND GitLab) is linked via normalized-title matching; the
    duplicate is marked so it's never fixed twice.
  - Status tracking: new → fixing → fixed / failed / skipped, with attempt
    counts and last confidence, persisted in ~/.fixfleet-buglist.json.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

LIST_PATH = Path.home() / ".fixfleet-buglist.json"

STATUSES = ("new", "fixing", "fixed", "failed", "skipped", "duplicate",
            "not_a_bug", "not_relevant")


def _load() -> dict:
    try:
        return json.loads(LIST_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {"bugs": {}}


def _save(data: dict):
    try:
        LIST_PATH.write_text(json.dumps(data, indent=2, default=str))
    except OSError:
        pass


def _norm_title(title: str) -> str:
    s = re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def bug_key(source: str, iid, title: str) -> str:
    raw = f"{source}|{iid}|{_norm_title(title)}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def sync(source: str, bugs: list) -> dict:
    """Merge freshly fetched/parsed bugs into the ledger.

    Returns {"added": n, "known": n, "duplicates": n}. Never downgrades an
    existing status — a bug already marked fixed stays fixed.
    """
    data = _load()
    ledger = data["bugs"]
    by_norm_title = {
        e["norm_title"]: k for k, e in ledger.items()
        if e.get("status") != "duplicate"
    }

    added = known = dups = 0
    for b in bugs:
        key = bug_key(source, b.get("iid"), b.get("title", ""))
        if key in ledger:
            known += 1
            ledger[key]["title"] = b.get("title", ledger[key]["title"])
            continue
        norm = _norm_title(b.get("title", ""))
        entry = {
            "key": key,
            "source": source,
            "iid": b.get("iid"),
            "title": b.get("title", ""),
            "norm_title": norm,
            "labels": b.get("labels", []),
            "web_url": b.get("web_url", ""),
            "status": "new",
            "attempts": 0,
            "last_confidence": None,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        # Same title already tracked from a different source → mark duplicate.
        twin = by_norm_title.get(norm)
        if twin and norm and ledger[twin]["source"] != source:
            entry["status"] = "duplicate"
            entry["duplicate_of"] = twin
            dups += 1
        else:
            by_norm_title[norm] = key
            added += 1
        ledger[key] = entry

    _save(data)
    return {"added": added, "known": known, "duplicates": dups}


def get(key: str) -> dict:
    return _load()["bugs"].get(key) or {}


def list_bugs(status: str = None, source: str = None) -> list:
    out = []
    for e in _load()["bugs"].values():
        if status and e.get("status") != status:
            continue
        if source and e.get("source") != source:
            continue
        out.append(e)
    return sorted(out, key=lambda e: e.get("updated_at", ""), reverse=True)


def mark(key: str, status: str, confidence: float = None) -> bool:
    """Update a bug's status. Returns False if the bug is unknown or the
    transition is refused (already being fixed by another run)."""
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    data = _load()
    entry = data["bugs"].get(key)
    if not entry:
        return False
    # Concurrency guard: refuse to start fixing a bug already mid-fix.
    if status == "fixing" and entry.get("status") == "fixing":
        return False
    entry["status"] = status
    if status == "fixing":
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
    if confidence is not None:
        entry["last_confidence"] = confidence
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save(data)
    return True


def summary() -> dict:
    counts: dict = {}
    for e in _load()["bugs"].values():
        counts[e.get("status", "new")] = counts.get(e.get("status", "new"), 0) + 1
    return counts
