"""Persistent state — track tokens used per backend per day, attempted issues."""

import json
from datetime import datetime
from pathlib import Path

STATE_PATH = Path.home() / ".bugfixer-state.json"


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict):
    try:
        STATE_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_daily_usage(backend_name: str) -> int:
    data = _load()
    return int(data.get("usage", {}).get(_today(), {}).get(backend_name, {}).get("tokens", 0))


def record_usage(backend_name: str, tokens: int, project_id: str, issue_iid, success: bool):
    data = _load()
    today = _today()

    usage = data.setdefault("usage", {}).setdefault(today, {}).setdefault(backend_name, {
        "tokens": 0, "issues": 0, "success": 0, "fail": 0,
    })
    usage["tokens"] = int(usage.get("tokens", 0)) + tokens
    usage["issues"] = int(usage.get("issues", 0)) + 1
    if success:
        usage["success"] = int(usage.get("success", 0)) + 1
    else:
        usage["fail"] = int(usage.get("fail", 0)) + 1

    attempts = data.setdefault("attempts", {})
    key = f"{project_id}#{issue_iid}"
    attempts.setdefault(key, []).append({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "backend": backend_name,
        "tokens": tokens,
        "success": success,
    })

    _save(data)


def was_attempted(project_id: str, issue_iid) -> list:
    data = _load()
    return data.get("attempts", {}).get(f"{project_id}#{issue_iid}", [])


def was_fixed(project_id: str, issue_iid) -> bool:
    return any(a.get("success") for a in was_attempted(project_id, issue_iid))


def daily_summary() -> dict:
    return _load().get("usage", {}).get(_today(), {})
