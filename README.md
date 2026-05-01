<div align="center">

# 🚀 FixFleet

### **Auto-fix GitLab bugs with AI agents — bring your own CLI or free API.**

*Reads open `Bug` issues from GitLab → parses stack traces and steps → pre-narrows the search to relevant files → dispatches to your AI agent of choice → scores the fix's confidence. All locally. No commits. No lock-in.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-54%20passing-brightgreen.svg)](#-testing)
[![Stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-success.svg)](#-quick-start)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-ff69b4.svg)](#-contributing)

**One command. Any AI. Zero waste.**

`Claude Code` · `Codex` · `Gemini CLI` · `Cursor Agent` · `Aider` · `Qwen Code` · `Groq` · `Gemini API` · `OpenRouter` · `Cerebras` · `Ollama` · `LM Studio`

</div>

---

> 🎯 **What this tool does in one sentence:**
> *Pulls open bug tickets from GitLab, hands each one to an AI coding agent with the right context already pre-loaded, and scores how confident the fix is — so you only review the ones worth reviewing.*

Built by **Yash Koladiya**.

---

## ✨ What it does

1. Fetches **open issues with the `Bug` label** from any GitLab project (gitlab.com or self-hosted).
2. Parses each issue body — pulling out **Description, Steps to Reproduce, Expected/Actual behavior, Logs, Stack Traces** automatically.
3. Pre-narrows the search space: extracts file paths, stack frames, symbols → **ranks candidate files in your local repo** so the AI doesn't waste tokens hunting.
4. Dispatches the structured prompt to your chosen AI agent (CLI or API).
5. Computes a **confidence score** for the fix using diff metrics + model self-rating + hedge-density.
6. Tracks **token usage per backend per day** so you don't blow through paid quotas.
7. **Never commits or pushes** — leaves the working tree dirty for human review.

---

## 🚀 Quick start

```bash
git clone https://github.com/Yash-Koladiya30/fixfleet.git
cd fixfleet
python3 fix_bugs.py
```

No `pip install` required — pure stdlib. Works on Python 3.9+.

---

## 🔌 Backend options

You need **at least one** of these. Mix and match per session.

### CLI backends (use existing paid plans)

| CLI | Install | Login | Plan source |
|---|---|---|---|
| **Claude Code** | `npm i -g @anthropic-ai/claude-code` | `claude login` | Claude Pro/Max |
| **Codex** | `npm i -g @openai/codex` | `codex login` | ChatGPT Plus/Pro |
| **Gemini CLI** | `npm i -g @google/gemini-cli` | `gemini auth` | Google account (free tier) |
| **Cursor Agent** | install from cursor.sh | `cursor-agent login` | Cursor Pro |
| **Aider** | `pip install aider-chat` | API key | Bring your own |
| **Qwen Code** | `npm i -g @qwen-code/qwen-code` | OAuth or key | Free tier |

### API backends (free tier-friendly)

Single OpenAI-compatible client serves all of these:

| Provider | Free? | Get key |
|---|---|---|
| **Groq** | ✅ Free, fast (~500 tok/s) | https://console.groq.com/keys |
| **Google Gemini** | ✅ Free tier, big quota | https://aistudio.google.com/apikey |
| **OpenRouter** | ✅ Many free models | https://openrouter.ai/keys |
| **Cerebras** | ✅ Free tier | https://cloud.cerebras.ai |
| **Ollama** | ✅ Local, no key, offline | https://ollama.com |
| **LM Studio** | ✅ Local, no key | https://lmstudio.ai |

---

## 🔑 Generating a GitLab token

1. Go to **gitlab.com → top-right avatar → Edit profile → Access Tokens**.
2. Create a Personal Access Token with scope: **`api`** or **`read_api`**.
3. Copy the `glpat-...` token. GitLab shows it **once**.
4. Paste when FixFleet asks. Typing is hidden via `getpass`.

> ⚠️ **Never commit tokens.** This repo's `.gitignore` already excludes `.env`, `*.token`, `secrets.*`, and the local config files (`~/.bugfixer.json`, `~/.bugfixer-state.json` are stored in your home dir, NOT in the repo).

---

## 🧭 Flow

```
Step 0  Choose Backend         → pick installed CLI or configure API
Step 1  GitLab Token           → paste glpat-...
Step 2  GitLab Project         → paste full URL (or short path / numeric ID)
Step 3  Local Project Dir      → path to cloned repo on your Mac
Step 4  Date Filter            → YYYY-MM-DD or Enter for all
Step 5  Fetching Issues        → auto-paginated
Step 6  Select Issues          → 1,3,5  |  all  |  unfixed  |  q
        → fixes each, shows budget + confidence per issue
```

After Step 0/2/3, defaults save to `~/.bugfixer.json` — next run press Enter to reuse.

### Inputs accepted at Step 2

| Input | Auto-extracts |
|---|---|
| `https://gitlab.com/group/project` | gitlab.com host + path |
| `https://gitlab.com/group/project.git` | strips `.git` |
| `https://gitlab.com/g/p/-/issues` | strips UI suffix |
| `git@gitlab.com:group/project.git` | SSH form |
| `https://gitlab.example.com/team/repo` | self-hosted host |
| `group/project` | short form |
| `12345` | numeric ID |

---

## 🎯 Confidence + Semantic Scoring

Every fix gets graded:

```
Confidence Report
  Final score:    0.84  ████████████████░░░░  (High)
  Self-rating:    8/10
  Root cause:     Missing null check in handleSubmit
  Diff focus:     0.92
  File relevance: 0.85
  Hedge density:  1.2%
  Tests run:      no
  Files changed:  1  (12 lines)
```

Sources: model self-rating from the structured `FIX REPORT` block, `git diff` metrics, hedge-word density, file-relevance vs candidate list.

---

## 💰 Token optimization

- **Locator** pre-greps the repo for candidate files → top file inlined directly into prompt
- **Section caps** trim long descriptions/logs before sending
- **Budget enforcement** — per-issue, session, daily caps in config
- **State persistence** — skips already-fixed issues, tracks daily usage per backend

Typical savings vs naive prompt: **60–80% tokens** for bugs with file/trace hints.

---

## ⚙️ Configuration

Local config: `~/.bugfixer.json`

```json
{
  "default_backend": "claude",
  "default_project_id": "group/project",
  "default_project_host": "gitlab.com",
  "default_project_dir": "/Users/you/work/project",
  "api": {
    "preset": "groq",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "gsk_...",
    "model": "llama-3.3-70b-versatile"
  },
  "budgets": {
    "session_max_tokens": 200000,
    "per_issue_max_tokens": 30000,
    "daily_max_tokens": 500000
  },
  "skip_already_fixed": true
}
```

> 🔒 Lives in your home directory, **NOT** the repo. The `.gitignore` excludes it from git regardless.

Override the backend per run with an env var:
```bash
BUGFIXER_BACKEND=codex python3 fix_bugs.py
```

---

## 🧪 Testing

```bash
python3 -m unittest tests.test_all -v
```

54+ unit tests cover parser, locator, budget, confidence, prompt, registry, diff-apply, state, config, URL parsing, path sanitization.

---

## 📂 Project layout

```
fixfleet/
├── bugfixer/
│   ├── ui.py              terminal styling
│   ├── gitlab.py          API client + URL parser
│   ├── parser.py          issue-body section extractor
│   ├── locator.py         signal extraction + file ranking + inlining
│   ├── prompt.py          structured prompt builder
│   ├── budget.py          token slimming + estimation + caps
│   ├── confidence.py      diff metrics + self-rating + hedge density
│   ├── state.py           ~/.bugfixer-state.json
│   ├── config.py          ~/.bugfixer.json
│   ├── cli.py             interactive flow orchestration
│   └── backends/
│       ├── base.py        Backend ABC
│       ├── _subprocess.py tee runner
│       ├── registry.py    detect installed CLIs + API presets
│       ├── cli/           claude · codex · gemini · cursor · aider · qwen
│       └── api/openai_compat.py
├── fix_bugs.py            entry shim
└── tests/test_all.py
```

---

## 🛡️ Security notes

- Tokens / API keys typed via `getpass` — never echoed to terminal, never written to repo.
- All issue body content is **fenced** in the prompt with adaptive fence length to prevent prompt-injection from malicious issue authors.
- The `.gitignore` excludes config + state files, common secret files (`.env`, `*.token`, `*.key`).
- The tool **never** commits or pushes — manual review required before sharing fixes.

---

## 🐞 Troubleshooting

| Symptom | Fix |
|---|---|
| `claude command not found` | Install one CLI or pick the API option in Step 0 |
| `HTTP 401` from GitLab | Token expired or wrong scope (`read_api`/`api` needed) |
| `HTTP 404` | Wrong project URL/ID format |
| "No bugs found" | GitLab issues need exact `Bug` label (case-sensitive) |
| Path with spaces fails | Drag-drop folder from Finder works (auto-unescapes) |
| Want to reset config | `rm ~/.bugfixer.json ~/.bugfixer-state.json` |

---

## 🤝 Contributing

Issues / PRs welcome. Guidelines:

- Pure stdlib — no `requirements.txt` dependencies in core
- All new code paths need unit tests
- Run `python3 -m unittest tests.test_all` before submitting

---

## 📄 License

MIT — see [LICENSE](LICENSE). Built by **Yash Koladiya**.
