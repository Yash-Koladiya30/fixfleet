"""User config — ~/.bugfixer.json."""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".bugfixer.json"

DEFAULT_CONFIG = {
    "default_backend": "",
    "default_project_id": "",
    "default_project_dir": "",
    "api": {
        "preset": "",
        "base_url": "",
        "api_key": "",
        "model": "",
    },
    "budgets": {
        "session_max_tokens": 200_000,
        "per_issue_max_tokens": 30_000,
        "daily_max_tokens": 500_000,
    },
    "locator": {
        "max_candidates": 5,
        "inline_top_file": True,
        "inline_max_lines": 250,
    },
    "skip_already_fixed": True,
}


def load() -> dict:
    if not CONFIG_PATH.exists():
        return _deep_copy(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return _deep_copy(DEFAULT_CONFIG)
    return _merge(_deep_copy(DEFAULT_CONFIG), data)


def save(cfg: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except OSError:
        pass


def _deep_copy(d):
    return json.loads(json.dumps(d))


def _merge(base: dict, override: dict) -> dict:
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _merge(base[k], v)
        else:
            base[k] = v
    return base
