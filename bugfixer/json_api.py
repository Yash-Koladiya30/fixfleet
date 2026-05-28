"""Non-interactive JSON API for programmatic callers (VSCode extension, CI, etc).

Usage from shell:
    fixfleet --list-bugs-json --token glpat-... --project-url https://...
    fixfleet --backends-json
    fixfleet --fix-issue 42 --backend claude --token ... --project-url ... --project-dir ...
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, budget, config, state
from .backends.base import RunResult
from .backends.registry import (
    API_PRESETS,
    build_api_backend,
    detect_available_clis,
    detect_unavailable_clis,
    list_cli_backends,
)
from .confidence import evaluate as evaluate_confidence
from .gitlab import (
    GitLabAuthError,
    GitLabError,
    GitLabNetworkError,
    GitLabNotFoundError,
    fetch_bug_issues,
    parse_project_input,
)
from .locator import locate
from .parser import parse_issue
from .prompt import build_prompt


def _emit(payload):
    """Print a single-line JSON payload to stdout."""
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _err(message: str, code: int = 1, error_code: str = "generic"):
    _emit({"ok": False, "error": message, "code": error_code})
    sys.exit(code)


def _err_from_gitlab(e: GitLabError):
    """Emit structured JSON for a GitLab exception, then exit cleanly."""
    _emit({
        "ok": False,
        "code": e.code,
        "status": e.status,
        "error": e.message,
    })
    sys.exit(1)


# ── List backends ──────────────────────────────────────────────

def cmd_backends_json():
    """Output detected CLI backends + API preset metadata."""
    installed = [
        {
            "name": b.name,
            "display_name": b.display_name,
            "binary": b.requires_binary,
            "version": b.version(),
            "installed": True,
        }
        for b in detect_available_clis()
    ]
    missing = [
        {
            "name": b.name,
            "display_name": b.display_name,
            "binary": b.requires_binary,
            "installed": False,
        }
        for b in detect_unavailable_clis()
    ]
    presets = [
        {"key": k, **v} for k, v in API_PRESETS.items()
    ]
    _emit({
        "ok": True,
        "version": __version__,
        "cli_backends": installed + missing,
        "api_presets": presets,
    })


# ── List bugs ──────────────────────────────────────────────────

def cmd_list_bugs_json(args):
    token = args.token
    project_url = args.project_url
    if not token:
        _err("--token required")
    if not project_url:
        _err("--project-url required")

    try:
        host, project_id = parse_project_input(project_url)
    except ValueError as e:
        _err(f"invalid --project-url: {e}")

    try:
        issues = fetch_bug_issues(token, project_id, date_str=args.date, host=host)
    except GitLabError as e:
        _err_from_gitlab(e)
    except Exception as e:
        _err(f"unexpected error: {e}", error_code="unexpected")

    payload_issues = []
    for i in issues:
        parsed = parse_issue(i)
        fixed = state.was_fixed(project_id, i["iid"])
        payload_issues.append({
            "iid": i.get("iid"),
            "title": i.get("title", ""),
            "web_url": i.get("web_url", ""),
            "labels": i.get("labels", []),
            "created_at": i.get("created_at", ""),
            "updated_at": i.get("updated_at", ""),
            "author": (i.get("author") or {}).get("username", ""),
            "already_fixed": fixed,
            "sections": {
                "description": parsed.description,
                "steps": parsed.steps,
                "expected": parsed.expected,
                "actual": parsed.actual,
                "environment": parsed.environment,
                "logs": parsed.logs,
                "notes": parsed.notes,
            },
        })

    _emit({
        "ok": True,
        "host": host,
        "project_id": project_id,
        "count": len(payload_issues),
        "issues": payload_issues,
    })


# ── Fix one issue ──────────────────────────────────────────────

def cmd_fix_issue(args):
    token = args.token
    project_url = args.project_url
    project_dir = args.project_dir
    backend_name = args.backend
    issue_iid = args.fix_issue

    if not token: _err("--token required")
    if not project_url: _err("--project-url required")
    if not project_dir: _err("--project-dir required")
    if not backend_name: _err("--backend required")
    if not issue_iid: _err("--fix-issue required")

    if not Path(project_dir).is_dir():
        _err(f"project-dir not found: {project_dir}")

    try:
        host, project_id = parse_project_input(project_url)
    except ValueError as e:
        _err(f"invalid project-url: {e}")

    # Resolve backend
    backend = None
    for b in list_cli_backends():
        if b.name == backend_name:
            if not b.available():
                _err(f"backend {backend_name} not installed")
            backend = b
            break

    if backend is None and backend_name == "openai_compat":
        cfg = config.load()
        api_cfg = cfg.get("api") or {}
        if not (api_cfg.get("base_url") and api_cfg.get("model")):
            _err("API backend not configured. Run `fixfleet` interactively first to save API config.")
        backend = build_api_backend(
            base_url=api_cfg["base_url"],
            api_key=api_cfg.get("api_key", ""),
            model=api_cfg["model"],
        )

    if backend is None:
        _err(f"unknown backend: {backend_name}")

    # Fetch + find target issue
    try:
        issues = fetch_bug_issues(token, project_id, host=host)
    except GitLabError as e:
        _err_from_gitlab(e)
    target = next((i for i in issues if i.get("iid") == issue_iid), None)
    if target is None:
        _err(f"issue #{issue_iid} not found among open Bug-labeled issues")

    parsed = parse_issue(target)
    loc = locate(parsed, project_dir)
    prompt = build_prompt(parsed, locator=loc)

    # Budget check
    daily_used = state.get_daily_usage(backend.name)
    check = budget.check_budget(
        prompt, backend.name,
        session_used=0, daily_used=daily_used,
    )

    # Run backend
    result: RunResult = backend.run(prompt, project_dir)
    conf = evaluate_confidence(
        result.stdout, project_dir,
        candidate_files=loc.candidates,
        issue_keywords=loc.symbols + loc.files_mentioned,
    )

    success = result.ok and (conf.final_score >= 0.20 or conf.files_changed)
    state.record_usage(
        backend_name=backend.name,
        tokens=check.estimated,
        project_id=project_id,
        issue_iid=issue_iid,
        success=success,
    )

    _emit({
        "ok": True,
        "issue": {
            "iid": issue_iid,
            "title": target.get("title", ""),
        },
        "backend": backend.name,
        "result": {
            "returncode": result.returncode,
            "timed_out": result.timed_out,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        "confidence": {
            "final_score": conf.final_score,
            "label": conf.label(),
            "self_rating": conf.self_rating,
            "root_cause": conf.root_cause,
            "diff_focus": conf.diff_focus,
            "file_relevance": conf.file_relevance,
            "hedge_density": conf.hedge_density,
            "tests_run": conf.tests_run,
            "files_changed": conf.files_changed,
            "lines_changed": conf.lines_changed,
            "notes": conf.notes,
        },
        "tokens": {
            "estimated": check.estimated,
            "daily_used_after": daily_used + check.estimated,
        },
        "locator": {
            "files_mentioned": loc.files_mentioned,
            "candidates": loc.candidates,
            "frames_count": len(loc.stack_frames),
            "symbols_count": len(loc.symbols),
        },
        "success": success,
    })


# ── Get config ─────────────────────────────────────────────────

def cmd_config_get():
    cfg = config.load()
    # Redact sensitive fields
    safe = {**cfg}
    if "api" in safe and isinstance(safe["api"], dict):
        api = {**safe["api"]}
        if api.get("api_key"):
            api["api_key"] = "***redacted***"
        safe["api"] = api
    _emit({"ok": True, "config": safe})


# ── Set config ─────────────────────────────────────────────────

def cmd_config_set(args):
    if not args.config_set:
        _err("--config-set requires KEY=VALUE")
    cfg = config.load()

    for pair in args.config_set:
        if "=" not in pair:
            _err(f"invalid --config-set entry: {pair}")
        key, value = pair.split("=", 1)
        # Support nested keys via dot notation: api.base_url=...
        parts = key.split(".")
        target = cfg
        for p in parts[:-1]:
            target = target.setdefault(p, {})
        target[parts[-1]] = value

    config.save(cfg)
    _emit({"ok": True, "saved": list(args.config_set)})


# ── Argument parser ────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fixfleet",
        description="FixFleet — auto-fix GitLab bugs with AI agents.",
        add_help=True,
    )
    p.add_argument("--version", action="version", version=f"fixfleet {__version__}")

    # JSON / non-interactive modes
    p.add_argument("--backends-json", action="store_true", help="List installed backends as JSON")
    p.add_argument("--list-bugs-json", action="store_true", help="Fetch open bugs as JSON")
    p.add_argument("--fix-issue", type=int, metavar="IID", help="Fix one issue by IID, output JSON")
    p.add_argument("--config-get", action="store_true", help="Print current config as JSON (redacted)")
    p.add_argument("--config-set", action="append", metavar="KEY=VALUE",
                   help="Set a config key (use dot notation, e.g. api.base_url=...)")

    # Shared params for non-interactive calls
    p.add_argument("--token", help="GitLab token (or set BUGFIXER_TOKEN env var)")
    p.add_argument("--project-url", help="GitLab project URL or ID")
    p.add_argument("--project-dir", help="Local project directory")
    p.add_argument("--backend", help="Backend name: claude, codex, gemini, cursor, aider, qwen, openai_compat")
    p.add_argument("--date", help="Filter bugs created on YYYY-MM-DD")

    return p


def main():
    import os
    parser = build_parser()
    args, _unknown = parser.parse_known_args()

    # Env-var fallbacks
    args.token = args.token or os.environ.get("BUGFIXER_TOKEN", "")
    args.project_url = args.project_url or os.environ.get("BUGFIXER_PROJECT_URL", "")
    args.project_dir = args.project_dir or os.environ.get("BUGFIXER_PROJECT_DIR", "")
    args.backend = args.backend or os.environ.get("BUGFIXER_BACKEND", "")

    if args.backends_json:
        cmd_backends_json()
        return
    if args.list_bugs_json:
        cmd_list_bugs_json(args)
        return
    if args.fix_issue is not None:
        cmd_fix_issue(args)
        return
    if args.config_get:
        cmd_config_get()
        return
    if args.config_set:
        cmd_config_set(args)
        return

    # No JSON flag → fall through to interactive CLI
    from .cli import main as interactive_main
    interactive_main()


if __name__ == "__main__":
    main()
