# FixFleet — AI Agent Context

> Read this file first. It contains everything needed to work on this codebase
> without exploring. Machine setup / release steps live in [SETUP.md](SETUP.md).

## What this is

FixFleet auto-fixes bugs with AI agents. Bug sources: 6 issue trackers
(GitHub, GitLab, Jira, Linear, Bitbucket, Azure DevOps) **or** local bug files
(Excel/Word/PDF — no tracker/token needed). It parses bugs, checks project
relevance, locates likely files, dispatches to an AI backend (Claude Code,
Codex, Gemini CLI, Cursor, Aider, Qwen, or any OpenAI-compatible API), and
keeps a fix only when it's solid — otherwise reverts via git. Never commits.

Two deliverables, one repo:
- **Python CLI** `bugfixer/` → PyPI package `fixfleet` (entry points `fixfleet`, `fix-bugs` → `bugfixer.json_api:main`)
- **VS Code extension** `vscode/` → Marketplace + Open VSX `YashKoladiya30.fixfleet` (calls the CLI; never talks to trackers/AI directly)

## Hard rules (violating these is a bug)

1. **Python runtime is stdlib-only, >=3.9.** No pip dependencies in `bugfixer/`
   except the optional `files` extra (`pypdf`, imported lazily in `files/pdf.py`
   only). No `X | Y` type syntax (3.10+).
2. **Never commit/push in the user's repo.** Fix engines leave the tree dirty.
3. **Confidence scores/thresholds are internal.** User-facing text (chat
   replies, extension UI) says "solid fixes", "needs review", "not a bug",
   "not this project" — never numbers, "confidence", or "threshold".
4. **Webviews:** every dynamic string passes `esc()` before `innerHTML`; every
   panel has a CSP meta tag; animations wrapped in
   `@media (prefers-reduced-motion: no-preference)`.
5. **Tokens:** extension passes tracker tokens via `BUGFIXER_TOKEN` env var,
   NEVER argv (ps/log exposure). CLI log redaction is position-based.
6. **Telemetry privacy:** event names + coarse metadata only — never tokens,
   URLs, titles, code, file paths. Opt-outs must keep working
   (`telemetry.enabled` config, `DO_NOT_TRACK`, `FIXFLEET_TELEMETRY=0`,
   VS Code global telemetry setting).
7. **Fork safety:** `_subprocess.py` spawns with `start_new_session=True`
   (fork+exec, not posix_spawn). Any thread doing network I/O must hold
   `telemetry.spawn_lock` during the request, and Popen takes the same lock —
   otherwise child deadlocks pre-exec and backends hang silently (real bug,
   fixed in 0.5.2).
8. **`--date` means "created that single day"** — identical semantics on all
   six providers (exclusive next-day upper bound).
9. **Versions live in 3 places**, bump together: `pyproject.toml`,
   `bugfixer/__init__.py`, `vscode/package.json` (extension versions its own).
10. **License:** source-available (see LICENSE) — free to use, no
    copy/modify/redistribute. Don't add "open source" claims to docs.

## Python package map (`bugfixer/`)

| Module | Responsibility |
|---|---|
| `json_api.py` | CLI entry. All flags, JSON-line output, dispatch. The extension's only interface |
| `cli.py` | Interactive terminal flow (GitLab-only, styled) |
| `providers/` | One module per tracker + `base.py` (Provider ABC, error types) + `registry.py` (`get_provider`, `detect_provider_from_url` — hostname-only matching) |
| `files/` | Bug files: `xlsx.py`/`docx.py` pure-stdlib zip+XML readers, `pdf.py` (pypdf, optional), `mapper.py` (header→field heuristics + AI fallback), `freetext.py` (numbered/Bug:-style splitting + AI fallback), `media.py` (embedded screenshot extraction → `~/.fixfleet-media/`, xlsx row-anchored) |
| `parser.py` | Markdown issue body → `ParsedIssue` sections (steps/expected/actual/logs…) |
| `locator.py` | Extract file paths/stack frames/symbols → rank candidate files (rg or pure-py grep) → inline top file |
| `triage.py` | Pre-fix QA gate: RELEVANCE only (files/symbols not in project → `not_relevant`). Bug-vs-suggestion is decided by the fixing AI, not here |
| `prompt.py` | Builds the work-item prompt: fenced untrusted sections, locator hints, FIX REPORT contract (see below) |
| `backends/` | `base.py` (Backend ABC, `RunResult`), `registry.py` (CLI list + API presets), `cli/*.py` (one per AI CLI, argv construction), `api/openai_compat.py` (diff-mode HTTP backend), `_subprocess.py` (tee runner: process-group kill on timeout, utf-8, spawn_lock) |
| `confidence.py` | Scores a fix: FIX REPORT parse + git diff stats + hedge words. Exposes `verdict` ("fixed"/"not_a_bug") and `reasoning` |
| `autofix.py` | Batch engine: clean-tree required → triage gate → per-bug fix → keep if `result.ok && files_changed && score>=min_confidence` else `git checkout -- . && git clean -fd` revert → ledger update → summary with `alerts` |
| `buglist.py` | Persistent ledger `~/.fixfleet-buglist.json`: stable keys sha1(source|iid|title), statuses new/fixing/fixed/failed/skipped/duplicate/not_a_bug/not_relevant, cross-source duplicate detection, fixing-lock |
| `chat.py` | Chat engine for `--chat-json`: regex intents (load/list/status/fix/skip/threshold) + AI intent fallback; read-only actions answered directly, mutating ones returned as `action` for the caller to execute |
| `budget.py` | Token estimation + caps (per-issue/session/daily). Coerces legacy string configs |
| `config.py` | `~/.bugfixer.json` (defaults deep-merged) |
| `state.py` | `~/.bugfixer-state.json` usage/attempt history |
| `telemetry.py` | GA4 Measurement Protocol, fire-and-forget daemon thread, `spawn_lock`, measurement id public, API secret from git-ignored `_ga.py` or `FIXFLEET_GA_SECRET` env (absent → silently disabled) |
| `ui.py` | ANSI terminal helpers; ask_input/ask_secret exit cleanly on EOF/Ctrl+C |
| `gitlab.py` | Backwards-compat shim re-exporting provider names |

## Extension map (`vscode/src/`)

| File | Responsibility |
|---|---|
| `extension.ts` | Activation, command registration, status bar, CLI-missing prompt |
| `fixfleetCli.ts` | Spawns the CLI: PATH augmentation, `python -m` fallback, `runJson` (last JSON line wins), token via env, arg redaction. Helpers: `listBugs`, `fixBug`, `autoFix`, `chatMessage`, `buglistJson`, `listBackends` |
| `welcomeView.ts` | Sidebar: not-configured onboarding, tracker bug list w/ batch fix, file-mode ledger view (`sourceMode === 'file'` → `--buglist-json`, no token) |
| `bugPanel.ts` | Per-bug detail panel + single fix |
| `chatPanel.ts` | Brand-themed animated chat: quick-command chips, typing dots, persistent transcript (`globalState['fixfleet.chatHistory']` cap 200), ↑/↓ prompt recall (`fixfleet.promptHistory` cap 50), executes chat `action`s, renders auto-fix summaries + QA alerts in plain words |
| `settingsPanel.ts` | Settings webview: Bug Source chooser (tracker/file — file hides token sections), provider grid, backend grid |
| `telemetry.ts` | GA4 MP via `vscode.env.machineId`; respects `vscode.env.isTelemetryEnabled` + `fixfleet.telemetry`; secret from git-ignored `ga-keys.json` bundled into local vsix |

Brand palette: forest green `#1F3329→#16241D`, cream `#F0E6D2`, sage,
champagne/amber gold `#D4C19C`/`#D4A574`. Config keys under `fixfleet.*`
(`sourceMode`, `provider`, `gitlabToken` (generic token, legacy name),
`projectUrl`, `projectDir`, `backend`, `dateFrom/To`, `cliPath`, `pythonPath`,
`telemetry`).

## Contracts

**Unified bug dict** (every source produces this):
`{iid, title, description, labels[], created_at, updated_at, web_url, author:{username}, screenshots?[]}`
— `iid` is int-like for trackers, string for Jira ("PROJ-42") and files; compare with `str()`.
Bugs must carry a Bug label/type at the tracker; file rows with closed/fixed
status are skipped at parse.

**FIX REPORT** (the AI backend must end its output with this; parsed by
`confidence.parse_fix_report`):
```
=== FIX REPORT ===
VERDICT: <fixed | implemented | not_a_bug>
ROOT_CAUSE: <one sentence>
FILES_CHANGED: <paths or none>
CONFIDENCE: <1-10> / 10
REASONING: <one sentence>
TESTS_RUN: <yes | no | n/a>
=== END FIX REPORT ===
```
`not_a_bug` + no file changes → item reported to user as checked-and-fine,
nothing changed, ledger status `not_a_bug`.

**CLI JSON flags** (all emit single-line JSON; errors: `{ok:false, code, error}` exit 1):
`--backends-json` · `--providers-json` · `--list-bugs-json [--file PATH]` ·
`--fix-issue IID [--file PATH]` · `--auto-fix [--file PATH] [--min-confidence F] [--max-bugs N]`
(streams `{"event":"bug_done",...}` per bug, then final summary with
`kept/reverted/failed/skipped/not_a_bug/alerts[]`) · `--buglist-json [--bug-status S]` ·
`--mark-bug KEY=STATUS` · `--chat-json --message TEXT` → `{reply, action|null, session}` ·
`--config-get/--config-set K=V` (JSON-coerced) · `--force` (budget override).
Provider omitted → auto-detect from URL, fallback gitlab. Env fallbacks:
`BUGFIXER_TOKEN/PROJECT_URL/PROJECT_DIR/BACKEND`.

**Chat actions** the caller must execute:
`{type:"auto_fix", source, file, min_confidence}` and
`{type:"fix_one", key, iid, source, file, min_confidence}`.

## State files (user home)

`~/.bugfixer.json` config · `~/.bugfixer-state.json` usage ·
`~/.fixfleet-buglist.json` ledger · `~/.fixfleet-chat.json` chat session ·
`~/.fixfleet-media/<hash>/` extracted screenshots ·
`~/.bugfixer-analytics.json` anonymous client id.

## Testing

```bash
python3 -m pytest tests/ -q     # ~134 tests, fully offline, telemetry disabled
```
`tests/test_all.py` core engine; `tests/test_providers_qa.py` all providers via
mocked `urllib.request.urlopen` with real API response shapes (update mocks
when changing a provider); `tests/test_files_and_autofix.py` builds real
xlsx/docx zips in-memory, fake backend for autofix keep/revert/not_a_bug, chat
intents, triage, media. CI (`.github/workflows/publish-pypi.yml`) runs the
suite on tag push and publishes to PyPI via Trusted Publishing after injecting
`FIXFLEET_GA_SECRET`.

## Gotchas

- `python3 -m bugfixer...` resolves the INSTALLED package unless cwd is the
  repo root — run from repo root or use the venv.
- Claude CLI refuses to launch nested inside a Claude Code session
  (`CLAUDECODE` env) — `env -u CLAUDECODE` when testing backends from one.
- On this dev machine `/usr/local/bin/code` is Cursor; real VS Code is
  `/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code`.
- Jira uses `/rest/api/3/search/jql` + `nextPageToken` (old `/search` = HTTP 410).
- Bitbucket new issues are state `"new"` — filter includes new/open/on hold.
- GitHub `since` filters by updated_at; created-window enforced client-side.
- Interactive `fixfleet` (no flags) is GitLab-only by design.
- `git-ignored secrets`: `bugfixer/_ga.py`, `vscode/ga-keys.json` — never commit.
