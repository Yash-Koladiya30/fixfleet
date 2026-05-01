"""CLI entry point — orchestrates the bug-fixing flow."""

import os
import sys
from datetime import datetime
from pathlib import Path

from . import budget, config, state, ui
from .backends.base import Backend, RunResult
from .backends.registry import (
    API_PRESETS,
    build_api_backend,
    detect_available_clis,
    detect_unavailable_clis,
    list_cli_backends,
)
from .confidence import evaluate as evaluate_confidence
from .gitlab import fetch_bug_issues
from .locator import locate
from .parser import parse_issue
from .prompt import build_prompt


# ── Path sanitization ──────────────────────────────────────────

def _sanitize_path(raw: str) -> str:
    """Clean common shell-pasted path mistakes:
       - Strip leading 'cd ' (user copied a cd command)
       - Strip surrounding quotes (single, double, smart)
       - Unescape backslash-space (e.g. 'App\\ Aspect' → 'App Aspect')
       - Trim whitespace
    """
    s = raw.strip()
    # Strip leading 'cd ' command
    if s.lower().startswith("cd "):
        s = s[3:].strip()
    # Strip wrapping quotes
    for q in ('"', "'", "`", "“", "”", "‘", "’"):
        if len(s) >= 2 and s.startswith(q) and s.endswith(q):
            s = s[1:-1].strip()
            break
    # Unescape backslash-escaped spaces and parens (zsh/bash drag-and-drop)
    s = s.replace("\\ ", " ").replace("\\(", "(").replace("\\)", ")")
    s = s.replace("\\&", "&").replace("\\'", "'")
    return s.strip()


# ── Backend selection ──────────────────────────────────────────

def _step_choose_backend(cfg: dict) -> Backend:
    ui.print_section("Step 0 — Choose Backend")

    available = detect_available_clis()
    missing = detect_unavailable_clis()

    options: list = []  # list of (label, callable returning Backend)

    if available:
        ui.print_info(f"{ui.GREEN}Detected installed CLIs:{ui.RESET}")
        for b in available:
            idx = len(options) + 1
            options.append(("cli", b))
            ui.print_info(f"  [{idx}] {ui.BOLD}{b.display_name}{ui.RESET}  {ui.DIM}(`{b.requires_binary}`){ui.RESET}")
        print(f"  {ui.BLUE}│{ui.RESET}")

    if missing:
        ui.print_info(f"{ui.DIM}Not installed:{ui.RESET}")
        for b in missing:
            ui.print_info(f"     {ui.DIM}- {b.display_name} ({b.requires_binary}){ui.RESET}")
        print(f"  {ui.BLUE}│{ui.RESET}")

    api_idx = len(options) + 1
    options.append(("api", None))
    ui.print_info(f"{ui.GREEN}API option:{ui.RESET}")
    ui.print_info(f"  [{api_idx}] {ui.BOLD}OpenAI-Compatible API{ui.RESET}  "
                  f"{ui.DIM}(Groq / Gemini / OpenRouter / Ollama / ...){ui.RESET}")
    print(f"  {ui.BLUE}│{ui.RESET}")

    # Honor env var override
    forced = os.environ.get("BUGFIXER_BACKEND", "").strip().lower()
    if forced:
        for b in list_cli_backends():
            if b.name == forced and b.available():
                ui.print_success(f"Using {b.display_name} (BUGFIXER_BACKEND={forced})")
                ui.print_end()
                return b
        if forced == "openai_compat" or forced == "api":
            backend = _build_api_from_config(cfg)
            if backend:
                ui.print_success(f"Using API backend (BUGFIXER_BACKEND={forced})")
                ui.print_end()
                return backend

    # Honor saved default
    saved = cfg.get("default_backend") or ""
    default_hint = ""
    default_index = None
    if saved:
        for i, (kind, b) in enumerate(options, 1):
            if kind == "cli" and b and b.name == saved:
                default_index = i
                default_hint = f"  {ui.DIM}(saved default: {saved}, press Enter){ui.RESET}"
                break
        if saved == "openai_compat" and default_index is None:
            default_index = api_idx
            default_hint = f"  {ui.DIM}(saved default: API, press Enter){ui.RESET}"

    ui.print_info(f"Pick a backend{default_hint}")
    print(f"  {ui.BLUE}│{ui.RESET}")
    raw = ui.ask_input("Choice")

    if not raw and default_index is not None:
        choice_idx = default_index
    else:
        try:
            choice_idx = int(raw)
        except ValueError:
            ui.print_error("Invalid choice.")
            sys.exit(1)

    if not (1 <= choice_idx <= len(options)):
        ui.print_error("Choice out of range.")
        sys.exit(1)

    kind, backend = options[choice_idx - 1]
    if kind == "cli":
        cfg["default_backend"] = backend.name
        config.save(cfg)
        ui.print_success(f"Selected: {backend.display_name}")
        ver = backend.version()
        if ver:
            ui.print_info(f"Version: {ui.DIM}{ver}{ui.RESET}")
        ui.print_end()
        return backend

    # API path
    backend = _step_configure_api(cfg)
    cfg["default_backend"] = "openai_compat"
    config.save(cfg)
    ui.print_end()
    return backend


def _build_api_from_config(cfg: dict) -> Backend:
    api_cfg = cfg.get("api") or {}
    if api_cfg.get("base_url") and api_cfg.get("model"):
        return build_api_backend(
            base_url=api_cfg["base_url"],
            api_key=api_cfg.get("api_key", ""),
            model=api_cfg["model"],
        )
    return None


def _step_configure_api(cfg: dict) -> Backend:
    ui.print_info(f"\n  {ui.BOLD}API Configuration{ui.RESET}")

    saved = cfg.get("api") or {}
    if saved.get("base_url") and saved.get("model"):
        ui.print_info(f"Saved: {ui.DIM}{saved.get('preset', 'custom')} | "
                      f"{saved['base_url']} | {saved['model']}{ui.RESET}")
        ui.print_info(f"Press {ui.BOLD}Enter{ui.RESET} to reuse, or type {ui.BOLD}'new'{ui.RESET} to reconfigure")
        ans = ui.ask_input("Action").lower()
        if ans != "new":
            return build_api_backend(
                base_url=saved["base_url"],
                api_key=saved.get("api_key", ""),
                model=saved["model"],
            )

    ui.print_info("Pick a preset:")
    preset_keys = list(API_PRESETS.keys())
    for i, k in enumerate(preset_keys, 1):
        p = API_PRESETS[k]
        ui.print_info(f"  [{i}] {ui.BOLD}{p['label']}{ui.RESET}")
    print(f"  {ui.BLUE}│{ui.RESET}")

    raw = ui.ask_input("Preset")
    try:
        idx = int(raw) - 1
    except ValueError:
        ui.print_error("Invalid preset choice.")
        sys.exit(1)
    if not (0 <= idx < len(preset_keys)):
        ui.print_error("Out of range.")
        sys.exit(1)

    pkey = preset_keys[idx]
    preset = API_PRESETS[pkey]

    base_url = preset["base_url"]
    if pkey == "custom" or not base_url:
        base_url = ui.ask_input("Base URL (e.g. https://host/v1)")

    if preset["key_url"]:
        ui.print_info(f"Get a free API key: {ui.DIM}{preset['key_url']}{ui.RESET}")

    needs_key = pkey not in ("ollama", "lmstudio")
    api_key = ui.ask_secret("API key (leave blank for none)") if needs_key else ""

    default_model = preset["default_model"]
    model_in = ui.ask_input(f"Model [{default_model}]" if default_model else "Model")
    model = model_in or default_model
    if not model:
        ui.print_error("Model is required.")
        sys.exit(1)

    cfg["api"] = {
        "preset": pkey,
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
    }
    config.save(cfg)
    ui.print_success(f"Configured: {model} @ {base_url}")
    return build_api_backend(base_url=base_url, api_key=api_key, model=model)


# ── Steps 1-5 (token, project, dir, date, fetch) ───────────────

def _step_token() -> str:
    ui.print_section("Step 1 — GitLab Token")
    ui.print_info("Paste your GitLab Personal Access Token")
    ui.print_info(f"{ui.DIM}(starts with glpat-... | typing is hidden){ui.RESET}")
    ui.print_info(f"{ui.DIM}Required scope: 'api' or 'read_api'{ui.RESET}")
    print(f"  {ui.BLUE}│{ui.RESET}")
    token = ui.ask_secret("Token")
    if not token:
        ui.print_error("Token cannot be empty!")
        sys.exit(1)
    ui.print_success("Token received")
    ui.print_end()
    return token


def _step_project_id(cfg: dict) -> tuple:
    """Return (host, project_path)."""
    from .gitlab import parse_project_input

    ui.print_section("Step 2 — GitLab Project")
    ui.print_info(f"{ui.BOLD}Just paste the GitLab project URL — we'll handle the rest.{ui.RESET}")
    ui.print_info("")
    ui.print_info(f"{ui.WHITE}Any of these work:{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}https://gitlab.com/group/project{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}https://gitlab.com/group/project.git{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}https://gitlab.com/group/subgroup/project/-/issues{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}git@gitlab.com:group/project.git{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}group/project{ui.RESET}  {ui.DIM}(short form){ui.RESET}")
    ui.print_info(f"  {ui.GREEN}12345{ui.RESET}  {ui.DIM}(numeric ID){ui.RESET}")
    ui.print_info("")
    ui.print_info(f"{ui.DIM}Self-hosted GitLab works too — host is auto-detected from URL.{ui.RESET}")

    saved_id = cfg.get("default_project_id") or ""
    saved_host = cfg.get("default_project_host") or ""
    if saved_id:
        ui.print_info("")
        host_disp = saved_host or "gitlab.com"
        ui.print_info(f"Saved default: {ui.GREEN}{saved_id}{ui.RESET} on {ui.DIM}{host_disp}{ui.RESET}  {ui.DIM}(press Enter to reuse){ui.RESET}")
    print(f"  {ui.BLUE}│{ui.RESET}")

    while True:
        raw = ui.ask_input("Project URL or ID")
        if not raw and saved_id:
            host = saved_host or "gitlab.com"
            project_id = saved_id
            break
        if not raw:
            ui.print_error("Cannot be empty!")
            continue

        try:
            host, project_id = parse_project_input(raw)
        except ValueError as e:
            ui.print_error(f"Could not parse that input: {e}")
            ui.print_info("Try the full URL from your browser address bar.")
            continue

        # Sanity check — looks like a folder path?
        if raw.startswith(("/", "~")):
            ui.print_error("That looks like a folder path, not a GitLab project.")
            ui.print_info("Step 2 wants the GitLab URL. Step 3 is for the local folder.")
            continue
        break

    cfg["default_project_id"] = project_id
    cfg["default_project_host"] = host
    config.save(cfg)
    ui.print_success(f"Project: {ui.GREEN}{project_id}{ui.RESET}")
    if host != "gitlab.com":
        ui.print_info(f"Host: {ui.DIM}{host}{ui.RESET}  {ui.DIM}(self-hosted){ui.RESET}")
    ui.print_end()
    return host, project_id


def _step_project_dir(cfg: dict) -> str:
    ui.print_section("Step 3 — Local Project Directory")
    ui.print_info(f"{ui.BOLD}This is the LOCAL folder on your Mac where the code lives.{ui.RESET}")
    ui.print_info(f"{ui.BOLD}NOT a GitLab URL. NOT a Project ID.{ui.RESET}")
    ui.print_info("")
    ui.print_info(f"{ui.WHITE}If you haven't cloned the repo yet, do this first:{ui.RESET}")
    ui.print_info(f"  {ui.DIM}cd ~/Documents{ui.RESET}")
    ui.print_info(f"  {ui.DIM}git clone https://gitlab.com/your/project.git{ui.RESET}")
    ui.print_info("")
    ui.print_info(f"{ui.WHITE}Then paste the absolute path to that cloned folder, e.g.:{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}/Users/yashkoladiya/Documents/dual-accounts{ui.RESET}")
    ui.print_info(f"  {ui.GREEN}~/work/myproject{ui.RESET}  {ui.DIM}(tilde expands to home){ui.RESET}")
    ui.print_info("")
    ui.print_info(f"{ui.DIM}Tip: cd into the project folder before running, then press Enter to use it.{ui.RESET}")

    saved = cfg.get("default_project_dir") or ""
    if saved and Path(saved).is_dir():
        ui.print_info("")
        ui.print_info(f"Saved default: {ui.GREEN}{saved}{ui.RESET}  {ui.DIM}(press Enter to reuse){ui.RESET}")
    else:
        ui.print_info("")
        ui.print_info(f"Press {ui.BOLD}Enter{ui.RESET} to use current directory: {ui.GREEN}{Path.cwd()}{ui.RESET}")
    print(f"  {ui.BLUE}│{ui.RESET}")

    while True:
        raw = ui.ask_input("Local project dir")
        if not raw:
            project_dir = saved or str(Path.cwd())
        else:
            cleaned = _sanitize_path(raw)
            # Reject URLs early with helpful message
            if cleaned.startswith(("http://", "https://", "git@", "ssh://", "gitlab.com")):
                ui.print_error("That's a URL, not a local folder.")
                ui.print_info("Step 3 needs a path on your Mac (e.g. /Users/you/Documents/myproject).")
                ui.print_info("Clone the repo first if you haven't:")
                ui.print_info(f"  {ui.DIM}git clone <url> ~/Documents/myproject{ui.RESET}")
                continue
            # Reject GitLab-ID-looking strings (relative path that doesn't exist on disk)
            if (not cleaned.startswith(("/", "~", "."))
                    and "/" in cleaned
                    and not Path(cleaned).expanduser().exists()
                    and not Path.cwd().joinpath(cleaned).exists()):
                ui.print_error("That looks like a GitLab Project ID, not a local folder.")
                ui.print_info("Step 3 needs an absolute path like /Users/yashkoladiya/Documents/myproject")
                continue
            project_dir = cleaned

        project_dir = str(Path(project_dir).expanduser().resolve())
        if not Path(project_dir).is_dir():
            ui.print_error(f"Directory does not exist: {project_dir}")
            ui.print_info("Clone the repo first or check the path. Try again.")
            continue
        break

    cfg["default_project_dir"] = project_dir
    config.save(cfg)
    ui.print_success(f"Local dir: {ui.GREEN}{project_dir}{ui.RESET}")
    ui.print_end()
    return project_dir


def _step_date_filter() -> str:
    ui.print_section("Step 4 — Date Filter")
    ui.print_info(f"Enter date to fetch bugs {ui.DIM}(format: YYYY-MM-DD){ui.RESET}")
    ui.print_info(f"Press {ui.BOLD}Enter{ui.RESET} to fetch ALL open bugs")
    print(f"  {ui.BLUE}│{ui.RESET}")
    date_input = ui.ask_input("Date")
    if not date_input:
        ui.print_success("Fetching ALL open bugs")
        ui.print_end()
        return None
    try:
        datetime.strptime(date_input, "%Y-%m-%d")
    except ValueError:
        ui.print_error("Invalid date format! Use YYYY-MM-DD")
        sys.exit(1)
    ui.print_success(f"Filtering bugs created on {ui.BOLD}{date_input}{ui.RESET}")
    ui.print_end()
    return date_input


# ── Issue display + selection ──────────────────────────────────

def _display_issues(issues: list, project_id: str, skip_fixed: bool):
    ui.print_section(f"Found {ui.CYAN}{len(issues)}{ui.WHITE} open bug issue(s)")
    ui.print_divider()
    for i, issue in enumerate(issues, 1):
        labels = issue.get("labels", [])
        created = issue.get("created_at", "")[:10]
        priority, color = ui.get_priority(labels)
        labels_str = ", ".join(labels) if labels else "—"
        already = state.was_fixed(project_id, issue["iid"]) if skip_fixed else False
        status_tag = f"  {ui.GREEN}[FIXED]{ui.RESET}" if already else ""

        print(f"  {ui.BLUE}│{ui.RESET}")
        print(f"  {ui.BLUE}│  {ui.BOLD}{ui.WHITE}[{i}]{ui.RESET}  {ui.BOLD}#{issue['iid']}{ui.RESET}"
              f" {ui.WHITE}{issue['title']}{ui.RESET}{status_tag}")
        print(f"  {ui.BLUE}│       {ui.DIM}Created: {created}  {ui.RESET}"
              f"{color}Priority: {priority}{ui.RESET}  {ui.DIM}Labels: {labels_str}{ui.RESET}")
    ui.print_end()


def _select_issues(issues: list, project_id: str, skip_fixed: bool) -> list:
    ui.print_section("Step 6 — Select Issues to Fix")
    ui.print_info(f"Enter numbers separated by commas  {ui.DIM}(e.g., 1,3,5){ui.RESET}")
    ui.print_info(f"Enter {ui.BOLD}'all'{ui.RESET} to fix all  | {ui.BOLD}'unfixed'{ui.RESET} to skip already-fixed  | {ui.BOLD}'q'{ui.RESET} to quit")
    print(f"  {ui.BLUE}│{ui.RESET}")
    choice = ui.ask_input("Choice").lower()

    if choice == "q":
        ui.print_info("Bye!")
        ui.print_end()
        return []

    if choice in ("all", "unfixed"):
        if choice == "unfixed":
            selected = [i for i in issues if not state.was_fixed(project_id, i["iid"])]
        else:
            selected = list(issues)
        ui.print_success(f"Selected {len(selected)} issue(s)")
        ui.print_warning("Changes will be LOCAL only (no commit/push)")
        ui.print_end()
        return selected

    selected: list = []
    invalid: list = []
    for raw in choice.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            idx = int(raw) - 1
        except ValueError:
            invalid.append(raw)
            continue
        if 0 <= idx < len(issues):
            issue = issues[idx]
            if skip_fixed and state.was_fixed(project_id, issue["iid"]):
                ui.print_warning(f"Skipping #{issue['iid']} — already fixed previously")
                continue
            selected.append(issue)
        else:
            invalid.append(raw)

    if invalid:
        ui.print_warning(f"Ignored invalid entries: {', '.join(invalid)}")

    if not selected:
        ui.print_error("No valid issues selected.")
        ui.print_end()
        return []

    ui.print_success(f"Selected {len(selected)} issue(s) to fix")
    ui.print_warning("Changes will be LOCAL only (no commit/push)")
    ui.print_end()
    return selected


# ── Fix loop ───────────────────────────────────────────────────

def _print_parsed_preview(parsed):
    sections: list = []
    for name in ("description", "steps", "expected", "actual", "environment", "logs", "notes"):
        if getattr(parsed, name, ""):
            sections.append(name)
    if sections:
        ui.print_info(f"Parsed sections: {ui.CYAN}{', '.join(sections)}{ui.RESET}")
    else:
        ui.print_warning("No structured sections detected — using raw description")


def _print_locator_preview(loc):
    bits: list = []
    if loc.files_mentioned:
        bits.append(f"files={len(loc.files_mentioned)}")
    if loc.stack_frames:
        bits.append(f"frames={len(loc.stack_frames)}")
    if loc.symbols:
        bits.append(f"symbols={len(loc.symbols)}")
    if loc.candidates:
        bits.append(f"candidates={len(loc.candidates)}")
    if loc.top_inline:
        bits.append("inlined-top")
    if bits:
        ui.print_info(f"Locator: {ui.CYAN}{' '.join(bits)}{ui.RESET}")
    else:
        ui.print_warning("Locator: no hints — model will explore from scratch")


def _print_budget(check, backend_name: str):
    pct = check.estimated * 100 / max(check.per_issue_max, 1)
    bar_len = 20
    filled = min(bar_len, int(bar_len * pct / 100))
    bar = "█" * filled + "░" * (bar_len - filled)
    color = ui.GREEN if pct < 50 else (ui.YELLOW if pct < 90 else ui.RED)
    ui.print_info(f"Budget [{backend_name}]: {color}{check.estimated:,}{ui.RESET} est tokens "
                  f"{ui.DIM}(cap {check.per_issue_max:,}){ui.RESET}  {color}{bar}{ui.RESET}")
    if check.session_used:
        ui.print_info(f"Session used: {check.session_used:,} / {check.session_max:,}")
    if check.daily_used:
        ui.print_info(f"Today used:   {check.daily_used:,} / {check.daily_max:,}")


def _print_confidence(conf):
    s = conf.final_score
    bar_len = 20
    filled = min(bar_len, int(bar_len * s))
    bar = "█" * filled + "░" * (bar_len - filled)
    color = ui.GREEN if s >= 0.8 else (ui.YELLOW if s >= 0.55 else ui.RED)

    print(f"  {ui.BLUE}│{ui.RESET}")
    print(f"  {ui.BLUE}│  {ui.BOLD}Confidence Report{ui.RESET}")
    print(f"  {ui.BLUE}│    Final score:    {color}{s:.2f}{ui.RESET}  {color}{bar}{ui.RESET}  ({conf.label()})")
    if conf.self_rating:
        print(f"  {ui.BLUE}│    Self-rating:    {conf.self_rating}/10")
    if conf.root_cause:
        print(f"  {ui.BLUE}│    Root cause:     {ui.DIM}{conf.root_cause[:120]}{ui.RESET}")
    print(f"  {ui.BLUE}│    Diff focus:     {conf.diff_focus:.2f}")
    print(f"  {ui.BLUE}│    File relevance: {conf.file_relevance:.2f}")
    print(f"  {ui.BLUE}│    Hedge density:  {conf.hedge_density:.1%}")
    print(f"  {ui.BLUE}│    Tests run:      {conf.tests_run}")
    print(f"  {ui.BLUE}│    Files changed:  {len(conf.files_changed)}  ({conf.lines_changed} lines)")
    for note in conf.notes:
        print(f"  {ui.BLUE}│    {ui.YELLOW}!{ui.RESET} {note}")


def _fix_issues(selected: list, project_dir: str, project_id: str,
                backend: Backend, cfg: dict) -> tuple:
    fixed = failed = 0
    session_tokens = 0
    budgets = cfg.get("budgets") or {}
    locator_cfg = cfg.get("locator") or {}

    for i, issue in enumerate(selected, 1):
        labels = issue.get("labels", [])
        priority, color = ui.get_priority(labels)

        ui.print_section(f"Fixing Issue [{i}/{len(selected)}]")
        ui.print_info(f"#{issue['iid']} - {ui.BOLD}{issue['title']}{ui.RESET}")
        ui.print_info(f"Priority: {color}{priority}{ui.RESET}")

        parsed = parse_issue(issue)
        _print_parsed_preview(parsed)

        loc = locate(
            parsed,
            project_dir,
            max_candidates=int(locator_cfg.get("max_candidates", 5)),
            inline_top=bool(locator_cfg.get("inline_top_file", True)),
        )
        _print_locator_preview(loc)

        prompt = build_prompt(parsed, locator=loc)

        daily_used = state.get_daily_usage(backend.name)
        check = budget.check_budget(
            prompt, backend.name,
            session_used=session_tokens, daily_used=daily_used,
            budgets=budgets,
        )
        _print_budget(check, backend.name)

        if not check.allowed:
            ui.print_warning(f"Budget would be exceeded: {check.reason}")
            ans = ui.ask_input("Run anyway? (y/N)").lower()
            if ans != "y":
                ui.print_warning(f"Skipped #{issue['iid']} due to budget.")
                ui.print_end()
                failed += 1
                continue

        result: RunResult = backend.run(prompt, project_dir)
        consumed = check.estimated  # use estimate as proxy

        print(f"  {ui.BLUE}│  {ui.DIM}{'─' * 50}{ui.RESET}")

        if result.timed_out:
            ui.print_error("Backend timed out.")

        success = result.ok
        conf = evaluate_confidence(
            result.stdout,
            project_dir,
            candidate_files=loc.candidates,
            issue_keywords=loc.symbols + loc.files_mentioned,
        )
        _print_confidence(conf)

        # Apply confidence floor: low confidence + no diff = treat as failure
        if conf.final_score < 0.20 and not conf.files_changed:
            success = False

        session_tokens += consumed
        state.record_usage(
            backend_name=backend.name,
            tokens=consumed,
            project_id=project_id,
            issue_iid=issue["iid"],
            success=success,
        )

        if success:
            fixed += 1
            ui.print_success(f"Done with #{issue['iid']}  (confidence: {conf.label()})")
        else:
            failed += 1
            ui.print_error(f"Failed on #{issue['iid']}  (rc={result.returncode}, confidence: {conf.label()})")

        ui.print_end()

        if i < len(selected):
            print(f"\n  {ui.MAGENTA}  Continue to next issue? (y/n): {ui.RESET}", end="")
            cont = input().strip().lower()
            if cont != "y":
                ui.print_warning("Stopping early. Review your changes!")
                break

    return fixed, failed


# ── Entry ──────────────────────────────────────────────────────

def main():
    ui.print_banner()
    cfg = config.load()

    backend = _step_choose_backend(cfg)

    token = _step_token()
    host, project_id = _step_project_id(cfg)
    project_dir = _step_project_dir(cfg)
    date_filter = _step_date_filter()

    ui.print_section("Step 5 — Fetching Issues from GitLab")
    ui.print_info(f"Connecting to {ui.DIM}{host}{ui.RESET}...")
    issues = fetch_bug_issues(token, project_id, date_filter, host=host)
    if not issues:
        ui.print_warning("No open bug issues found! Nothing to fix.")
        ui.print_end()
        return
    ui.print_success(f"Fetched {len(issues)} bug issue(s)")
    ui.print_end()

    skip_fixed = bool(cfg.get("skip_already_fixed", True))
    _display_issues(issues, project_id, skip_fixed)
    selected = _select_issues(issues, project_id, skip_fixed)
    if not selected:
        return

    fixed, failed = _fix_issues(selected, project_dir, project_id, backend, cfg)
    ui.print_summary(fixed=fixed, failed=failed, total=len(selected))


if __name__ == "__main__":
    main()
