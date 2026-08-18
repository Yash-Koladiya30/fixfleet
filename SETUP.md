# FixFleet — Development Setup Guide

> Hand this file to an AI assistant (or follow it yourself) to get the project
> fully runnable on a fresh machine. Covers: clone → dev environment → tests →
> builds → releases → secrets. Nothing secret is in this file.

## What this project is

FixFleet auto-fixes bugs from 6 issue trackers (GitHub, GitLab, Jira, Linear,
Bitbucket, Azure DevOps) using AI agents (Claude Code, Codex, Gemini CLI,
Cursor, Aider, Qwen, or any OpenAI-compatible API). Two deliverables from one
repo:

| Deliverable | Location | Published to |
|---|---|---|
| Python CLI (`fixfleet` / `fix-bugs`) | `bugfixer/` | PyPI: https://pypi.org/project/fixfleet/ |
| VS Code extension | `vscode/` | VS Code Marketplace + Open VSX (`YashKoladiya30.fixfleet`) |

Repo: https://github.com/Yash-Koladiya30/fixfleet

## Repo map

```
bugfixer/               Python package (stdlib-only at runtime, no deps)
  cli.py                Interactive terminal flow (GitLab-only currently)
  json_api.py           Non-interactive JSON API — what the VS Code extension calls
  providers/            One module per issue tracker + registry + base ABC
  backends/cli/         One module per AI CLI tool
  backends/api/         OpenAI-compatible HTTP backend
  parser.py locator.py confidence.py budget.py prompt.py state.py config.py ui.py
  telemetry.py          GA4 Measurement Protocol analytics (see Secrets below)
  _ga.py                GIT-IGNORED — holds the GA4 API secret locally
tests/                  unittest/pytest suite (~100 tests, all providers mocked)
vscode/                 Extension source (TypeScript)
  src/                  extension.ts, fixfleetCli.ts, bugPanel.ts, settingsPanel.ts,
                        welcomeView.ts, telemetry.ts
  ga-keys.json          GIT-IGNORED — holds the GA4 API secret locally
.github/workflows/publish-pypi.yml   Tag-triggered PyPI publish (Trusted Publishing)
pyproject.toml          Python packaging; version lives here + bugfixer/__init__.py
```

## 1. Prerequisites

- Python 3.9+ for using the CLI; **3.12 recommended for development**
  (macOS: `brew install python@3.12`)
- Node.js 18+ and npm (for the extension)
- git with SSH key registered on GitHub (remote is `git@github.com:...`)
- Optional for real usage: at least one AI CLI on PATH (`claude`, `codex`,
  `gemini`, `cursor-agent`, `aider`, `qwen`) or an OpenAI-compatible API key

## 2. Clone + Python setup

```bash
git clone git@github.com:Yash-Koladiya30/fixfleet.git
cd fixfleet

# Dev virtualenv (runtime has zero dependencies; these are dev-only tools)
python3.12 -m venv .venv
source .venv/bin/activate
pip install pytest build

# Editable install — makes `fixfleet` command available
pip install -e .

fixfleet --version          # sanity check
fixfleet --backends-json    # detects installed AI CLIs, lists providers
```

## 3. Run tests (do this first on any new machine)

```bash
python -m pytest tests/ -q
# Expect: ~101 passed. Suite is fully offline — all provider APIs are mocked.
# Telemetry is auto-disabled inside tests.
```

Also verify the package imports on the minimum supported Python if available:
`python3.9 -m pytest tests/ -q` (same expected result).

## 4. VS Code extension setup

```bash
cd vscode
npm install
npm run compile            # tsc — must exit clean
npx vsce package           # produces fixfleet-<version>.vsix
```

Test locally: VS Code → Extensions panel → `···` → Install from VSIX.

## 5. Secrets and local-only files (IMPORTANT when migrating machines)

These files are **git-ignored** and must be recreated (or copied from the old
machine) — the project runs fine without them, but analytics will be silently
disabled:

| File | Content |
|---|---|
| `bugfixer/_ga.py` | `API_SECRET = "<GA4 Measurement Protocol secret>"` |
| `vscode/ga-keys.json` | `{ "api_secret": "<same secret>" }` |

Where to get the secret: https://analytics.google.com → Admin → Data streams →
the FixFleet stream (measurement ID `G-RB1CHG2YLD`, which is public and lives
in the source) → Measurement Protocol API secrets. The Firebase project is
`fixfleet-420a8` on console.firebase.google.com.

Verify analytics wiring:
```bash
FIXFLEET_TELEMETRY_DEBUG=1 fixfleet --backends-json
# stderr should print "[telemetry] ... validationMessages: []"
# Events visible in Firebase console → Analytics → DebugView
```

User-level files (on the OLD machine, copy if you want to keep history —
otherwise they regenerate):
- `~/.bugfixer.json` — saved config (default backend/project, budgets, API keys
  for the OpenAI-compatible backend)
- `~/.bugfixer-state.json` — token usage + fixed-issue history
- `~/.bugfixer-analytics.json` — anonymous analytics client id

Accounts/credentials needed for publishing (none stored in repo):
- **PyPI** — nothing local needed: publishing is GitHub-Actions Trusted
  Publishing, triggered by pushing a `v*` tag
- **VS Code Marketplace** — publisher `YashKoladiya30`; needs an Azure DevOps
  PAT for `vsce publish` (or upload the .vsix at
  https://marketplace.visualstudio.com/manage)
- **Open VSX** — token from open-vsx.org → Settings → Access Tokens;
  publish with `OVSX_PAT=<token> npx ovsx publish <vsix>`
- **GitHub Actions secret** (optional): repo secret `FIXFLEET_GA_SECRET` — the
  publish workflow bakes it into CI-built wheels; without it CI builds ship
  with telemetry disabled

## 6. Release process

Versions live in THREE places — bump all together:
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `bugfixer/__init__.py` → `__version__ = "X.Y.Z"`
3. `vscode/package.json` → `"version"` (extension has its own versioning)

Then:
```bash
# Python → PyPI (automatic via CI)
git commit -am "Release X.Y.Z: <summary>"
git tag vX.Y.Z
git push && git push origin vX.Y.Z
# CI verifies tag==pyproject version, runs tests, builds, publishes to PyPI.
# Watch: https://github.com/Yash-Koladiya30/fixfleet/actions

# Extension → both registries (manual)
cd vscode && npm run compile && npx vsce package
npx vsce publish                      # VS Code Marketplace (needs PAT)
OVSX_PAT=<token> npx ovsx publish fixfleet-<ver>.vsix   # Open VSX (Antigravity/Cursor)
```

Local wheel build (bakes the telemetry secret from `bugfixer/_ga.py`):
```bash
rm -rf dist build/lib && python -m build && ls dist/
```

## 7. Try it end-to-end

```bash
# List bugs from a tracker (provider auto-detected from URL)
fixfleet --list-bugs-json --token <tracker-token> \
  --project-url https://github.com/owner/repo

# Fix one issue (runs the AI agent locally in your repo checkout)
fixfleet --fix-issue 42 --backend claude --token <tracker-token> \
  --project-url https://github.com/owner/repo --project-dir ~/code/repo

# Interactive guided mode (GitLab only)
fixfleet
```

Notes: bugs must carry a `Bug`/`bug` label (Jira: issuetype Bug; Bitbucket:
kind bug; Azure: work item type Bug). Budgets are enforced — `--force`
overrides. Nothing is ever committed/pushed by the tool.

## 8. Gotchas / project conventions

- Runtime code is **Python stdlib only** — adding a pip dependency to
  `bugfixer/` is a breaking decision, don't do it casually
- All provider API calls are raw `urllib` with mocked-response tests in
  `tests/test_providers_qa.py`; when changing a provider, update its mock
  shapes to match the real API
- `--date` means "created that single day" on EVERY provider — keep semantics
  unified when touching date filters
- Jira uses `/rest/api/3/search/jql` (cursor pagination via `nextPageToken`);
  the old `/search` endpoint is removed and returns HTTP 410
- Extension passes the tracker token via `BUGFIXER_TOKEN` env var, never argv
- Tokens are never logged; webview HTML must escape all CLI-derived strings
- Known deferred gaps: tokens stored in plaintext VS Code settings (SecretStorage
  migration pending); interactive terminal mode is GitLab-only
