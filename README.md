<div align="center">

<img src="vscode/media/icon.png" alt="FixFleet" width="140" />

# FixFleet

### AI Bug Fixer for GitHub · GitLab · Jira · Linear · Bitbucket · Azure DevOps — or any Excel / Word / PDF bug list

*Reads bugs from your tracker **or straight from a bug file** (no tracker or token needed), parses stack traces and screenshots, pre-narrows the search to the right files, and dispatches to your AI of choice. Chat "fix all" — real bugs get fixed, suggestions get implemented, only solid fixes are kept (anything uncertain is undone), and items that aren't actually bugs are reported, not "fixed". All local. No commits. Bring your own AI.*

<p>
  <a href="https://pypi.org/project/fixfleet/"><img src="https://img.shields.io/pypi/v/fixfleet.svg?label=pypi&color=2D6A4F&style=for-the-badge" alt="PyPI" /></a>
  <a href="https://marketplace.visualstudio.com/items?itemName=YashKoladiya30.fixfleet"><img src="https://img.shields.io/visual-studio-marketplace/v/YashKoladiya30.fixfleet?label=vscode&color=722F37&style=for-the-badge" alt="VSCode Marketplace" /></a>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img src="https://img.shields.io/badge/license-GPL_v3-C8A47E?style=for-the-badge" alt="License GPL v3" /></a>
  <img src="https://img.shields.io/badge/python-3.9+-1F2421?style=for-the-badge" alt="Python 3.9+" />
</p>

<p>
  <a href="#-screenshots"><b>Screenshots</b></a> •
  <a href="#-install"><b>Install</b></a> •
  <a href="#-connect-your-tracker-token-setup-guides"><b>Token setup</b></a> •
  <a href="#-how-it-works"><b>How it works</b></a> •
  <a href="#-supported-ai-agents"><b>AI backends</b></a> •
  <a href="#-faq"><b>FAQ</b></a>
</p>

</div>

---

## 📸 Screenshots

<table>
<tr>
<td width="33%" align="center">
<img src="vscode/media/screenshots/welcome.png" alt="Welcome screen" />
<br/><sub><b>Welcome</b><br/>Tracker or bug file — your choice</sub>
</td>
<td width="33%" align="center">
<img src="vscode/media/screenshots/chat.png" alt="FixFleet Chat" />
<br/><sub><b>Chat</b><br/>Load bug files · "fix all" · QA-checked results</sub>
</td>
<td width="33%" align="center">
<img src="vscode/media/screenshots/settings-tracker.png" alt="Settings" />
<br/><sub><b>Settings</b><br/>6 trackers or token-free file mode · pick your AI</sub>
</td>
</tr>
</table>

---

## 📦 Install

### 🪄 VSCode Extension (recommended — premium UI)

<a href="https://marketplace.visualstudio.com/items?itemName=YashKoladiya30.fixfleet"><img src="https://img.shields.io/badge/Install_from_Marketplace-722F37?style=for-the-badge&logo=visualstudiocode&logoColor=white" alt="Install from VSCode Marketplace" /></a>

Or paste in terminal:
```bash
code --install-extension YashKoladiya30.fixfleet
```

### 🐍 Python CLI (terminal-only users)

```bash
pip3 install --user fixfleet
fixfleet
```

> ⚠️ If `fixfleet: command not found` — add user-bin to PATH:
> ```bash
> echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
> ```

---

## ⚡ Quick start (60 seconds)

### Fastest path — a bug file, no tracker, no token

1. **Install** the VSCode extension (1 click above)
2. **Click 🚀 FixFleet icon** → **💬 Start with a bug file — no token needed**
3. **📎 Load** your Excel / Word / PDF bug list — any column layout works, screenshots included
4. Say **`fix all`** — real bugs get fixed, suggestions get implemented, anything uncertain is undone, and non-bugs are reported back to you
5. **Review the diff, commit yourself** — FixFleet never commits or pushes

### With your issue tracker

1. **Get an access token** for your tracker — [full guides below](#-connect-your-tracker-token-setup-guides)
2. **Configure** → Bug Source: **Issue Tracker** → pick provider → paste token + project URL → save
3. **Click any bug** in the sidebar → **✨ Fix This Bug with AI** — or select several and batch-fix
4. **Review the diff, commit yourself**

---

## 🔑 Connect Your Tracker (Token Setup Guides)

FixFleet supports **6 issue trackers**. Pick yours below — each guide covers exactly where to click, which permissions to grant, and what to paste into FixFleet.

> 🔒 **Security note:** tokens are stored in your VSCode user settings on your machine only. FixFleet has no servers — your token goes directly from your laptop to your tracker's API and nowhere else.

<details>
<summary><b>🟧 GitLab</b> — gitlab.com or self-hosted</summary>

### 1. Generate the token

1. Open **https://gitlab.com/-/user_settings/personal_access_tokens** (or `https://YOUR-GITLAB-HOST/-/user_settings/personal_access_tokens` for self-hosted)
2. Click **"Add new token"**
3. Fill in:
   - **Token name**: `fixfleet`
   - **Expiration date**: up to 1 year ahead
4. **Select scopes** — tick ONE of:
   - ✅ `read_api` — read-only (list + read bugs). Enough for fixing.
   - ✅ `api` — read + write. Needed later for auto-commenting / closing issues.
5. Click **"Create personal access token"**
6. **Copy the token immediately** — GitLab shows it only once. Format: `glpat-xxxxxxxxxxxxxxxxxxxx`

### 2. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **GitLab** |
| Token | `glpat-xxxxxxxxxxxxxxxxxxxx` |
| Project URL | `https://gitlab.com/group/project` — any GitLab URL works (with `.git`, `/-/issues`, SSH form, or short `group/project`) |

### Requirements
- Bugs must carry the label **`Bug`** (capital B) to show up
- Your account needs at least **Reporter** role on the project

</details>

<details>
<summary><b>⬛ GitHub</b> — github.com or GitHub Enterprise</summary>

### 1. Generate the token (classic PAT)

1. Open **https://github.com/settings/tokens**
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Fill in:
   - **Note**: `fixfleet`
   - **Expiration**: 90 days or custom
4. **Select scopes** — tick ONE of:
   - ✅ `repo` — full repository access (covers private repos)
   - ✅ `public_repo` — public repos only (lighter permission)
5. Click **"Generate token"**
6. **Copy immediately** — shown once. Format: `ghp_xxxxxxxxxxxxxxxxxxxx`

*Alternative: fine-grained PATs also work — grant "Issues: Read" on the target repository.*

### 2. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **GitHub** |
| Token | `ghp_xxxxxxxxxxxxxxxxxxxx` |
| Project URL | `https://github.com/owner/repo` — also accepts `.git`, `/issues`, SSH, or short `owner/repo` |

### Requirements
- Bugs must carry the label **`bug`** (lowercase — GitHub's default label)
- Pull requests are automatically filtered out

</details>

<details>
<summary><b>🟦 Jira</b> — Atlassian Cloud (*.atlassian.net)</summary>

### 1. Generate the API token

1. Open **https://id.atlassian.com/manage-profile/security/api-tokens**
2. Click **"Create API token"**
3. **Label**: `fixfleet` → click **Create**
4. **Copy the token** — shown once

### 2. Combine email + token ⚠️ IMPORTANT

Jira authenticates with your **Atlassian account email AND the token together**. Paste them combined with a colon:

```
your-email@example.com:your-api-token
```

Example: `jane@acme.com:ATATT3xFfGF0aBcDeFgH...`

### 3. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **Jira** |
| Token | `email@example.com:api-token` (combined with `:`) |
| Project URL | `https://yourcompany.atlassian.net/browse/MYPROJ-1` or `https://yourcompany.atlassian.net/jira/projects/MYPROJ` |

> ⚠️ **Must paste the full URL** (not just the project key) — FixFleet reads your Atlassian host from it.

### Requirements
- Issues must have **Issue Type = Bug**
- Issues in any status except Done-category show up
- Your account needs **Browse Projects** permission

</details>

<details>
<summary><b>🟪 Linear</b> — linear.app</summary>

### 1. Generate the API key

1. Open **https://linear.app/settings/api**
2. Under **"Personal API keys"** click **"Create key"**
3. **Label**: `fixfleet` → create
4. **Copy** — format: `lin_api_xxxxxxxxxxxxxxxxxxxx`

### 2. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **Linear** |
| Token | `lin_api_xxxxxxxxxxxxxxxxxxxx` (paste as-is) |
| Project URL | `https://linear.app/yourworkspace/team/ENG/all` or any issue URL like `https://linear.app/yourworkspace/issue/ENG-42/...` — also accepts bare team key `ENG` |

### Requirements
- Issues must carry the label **`Bug`**
- Issues in Backlog / Todo / In-Progress states show up (completed/canceled excluded)
- FixFleet works per **team** — the team key (e.g. `ENG`) comes from your URL

</details>

<details>
<summary><b>🟫 Bitbucket</b> — bitbucket.org (Cloud)</summary>

### 1. Generate an App Password

1. Open **https://bitbucket.org/account/settings/app-passwords/**
2. Click **"Create app password"**
3. **Label**: `fixfleet`
4. **Permissions** — tick:
   - ✅ **Issues → Read**
5. Click **Create** → **copy the password** — shown once

### 2. Combine username + app password ⚠️ IMPORTANT

Bitbucket authenticates with your **username AND app password together**. Find your username at https://bitbucket.org/account/settings/ (it's NOT your email). Paste combined:

```
your-username:your-app-password
```

Example: `janedoe:ATBBxxxxxxxxxxxxxxxx`

### 3. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **Bitbucket** |
| Token | `username:app-password` (combined with `:`) |
| Project URL | `https://bitbucket.org/workspace/repo` or short `workspace/repo` |

### Requirements
- The repo's **issue tracker must be enabled** (Repository settings → Issue tracker)
- Issues with **kind = bug** and **state = open** show up
- Bitbucket Server (self-hosted) is NOT supported — Cloud only

</details>

<details>
<summary><b>🟦 Azure DevOps</b> — dev.azure.com Boards</summary>

### 1. Generate a PAT

1. Open **https://dev.azure.com** → sign in
2. Click the **user settings icon** (top-right, next to your avatar) → **"Personal access tokens"**
3. Click **"+ New Token"**
4. Fill in:
   - **Name**: `fixfleet`
   - **Organization**: select your org (or "All accessible organizations")
   - **Expiration**: up to 1 year
5. **Scopes** → click **"Custom defined"** → find **Work Items** → tick:
   - ✅ **Read**
6. Click **Create** → **copy the token** — shown once

### 2. What to paste in FixFleet

| Field | Value |
|---|---|
| Provider | **Azure DevOps** |
| Token | the PAT alone (no email, no colon — paste as-is) |
| Project URL | `https://dev.azure.com/yourorg/yourproject` or short `yourorg/yourproject` |

### Requirements
- Work items must have **Work Item Type = Bug**
- Bugs in any state except Closed/Done/Resolved/Removed show up
- Priority field maps automatically: 1 → High, 2 → Medium, 3-4 → Low

</details>

### Token format cheat-sheet

| Provider | Paste format | Example |
|---|---|---|
| GitLab | token alone | `glpat-abc123...` |
| GitHub | token alone | `ghp_abc123...` |
| Jira | `email:token` | `jane@acme.com:ATATT3x...` |
| Linear | key alone | `lin_api_abc123...` |
| Bitbucket | `username:app-password` | `janedoe:ATBBabc...` |
| Azure DevOps | PAT alone | `a1b2c3d4...` |

---

## 🧠 How it works

```
┌─ Bug source: tracker issue (GitHub / GitLab / Jira / Linear / Bitbucket / Azure DevOps)
│            OR a bug file (Excel / Word / PDF — screenshots included, no token needed)
│
├─ Parse: description, steps, expected/actual, stack traces, logs, embedded screenshots
│
├─ QA check: does this item belong to THIS project? (wrong-project items are
│            reported to you, never "fixed")
│
├─ Locate: extract file paths, symbols, stack frames → rank candidates → inline top file
│
├─ Dispatch to AI agent (Claude / Codex / Gemini / Cursor / Aider / Qwen / any free API)
│   The AI decides: defect → fix it · suggestion → implement it ·
│   code already correct → change nothing, tell you why
│
├─ Keep or undo: only solid fixes are kept — anything uncertain is reverted
│                automatically and marked "needs review"
│
└─ Done — local-only changes + a bug ledger (fixed / needs review / not a bug /
          not this project), ready for your review
```

**Chat-driven**: the 💬 chat panel runs this whole flow conversationally — `load bugs.xlsx`, `fix all`, `status`.

**Token-aware**: per-issue, session, and daily budgets prevent paid-plan overruns.

**Multi-backend**: detected CLI agents shown as installed; pick one per session.

**Nothing fixed twice**: a persistent ledger tracks every bug across sources, catches duplicates, and remembers what's done.

---

## 🤖 Supported AI agents

### CLI backends (uses your existing paid plans)

| Agent | Plan source |
|---|---|
| 🟪 **Claude Code** | Claude Pro / Max |
| 🟢 **Codex** | ChatGPT Plus / Pro |
| 🟦 **Gemini CLI** | Google AI free tier |
| ⚫ **Cursor Agent** | Cursor Pro |
| 🟧 **Aider** | Bring your own key |
| 🟨 **Qwen Code** | Alibaba free tier |

### API backends (free-tier friendly)

One OpenAI-compatible client serves all:

| Provider | Free | Get key |
|---|---|---|
| **Groq** | ✅ | https://console.groq.com/keys |
| **Google Gemini** | ✅ | https://aistudio.google.com/apikey |
| **OpenRouter** | ✅ | https://openrouter.ai/keys |
| **Cerebras** | ✅ | https://cloud.cerebras.ai |
| **Ollama** (local) | ✅ | https://ollama.com |
| **LM Studio** (local) | ✅ | https://lmstudio.ai |

---

## 🎯 Why FixFleet

### vs. doing it manually
Triages 50 bugs in the time it takes you to read 5 — and tells you which ones aren't even bugs.

### vs. AI inside the issue (e.g. GitLab Duo, GitHub Copilot Workspace)
- **Costs nothing extra** — uses AI plans you already pay for
- **Works without a tracker at all** — your QA team's Excel sheet is enough
- **Edits actual files locally**, not just comments
- **You pick the AI** — not locked to one vendor
- **One tool for all trackers** — GitHub + GitLab + Jira + Linear + Bitbucket + Azure DevOps
- **Works on private/self-hosted instances** without exposing source to a SaaS

### vs. running Claude/Codex CLI manually
- **Structured prompts** — extracts steps, logs, and screenshots automatically
- **Pre-narrows file scope** — saves 60–80% tokens
- **Keeps only solid fixes** — anything uncertain is undone automatically, so a bulk run can't wreck your tree
- **QA gate built in** — wrong-project items and not-actually-bugs get reported, not "fixed"
- **Bug ledger** — batch 50 bugs without fixing anything twice
- **Budget caps** — never blows through paid quotas

---

## ❓ FAQ

<details>
<summary><b>Does this use any paid backend / hidden costs?</b></summary>

No. FixFleet runs **100% locally** on your machine. No FixFleet servers, no Azure, no cloud component. You pay for nothing beyond AI plans you already own. The VSCode extension is free. The PyPI package is free. Updates forever, free.

</details>

<details>
<summary><b>Does FixFleet collect any data?</b></summary>

Only anonymous usage analytics (via Google Analytics): event names and coarse metadata like provider key, backend name, and success/failure — **never your code, tokens, project URLs, or issue content**. Used purely to find bugs and see which trackers/backends need attention.

Opt out anytime:
- CLI: `fixfleet --config-set telemetry.enabled=false` (or set `DO_NOT_TRACK=1`)
- VSCode: uncheck `fixfleet.telemetry` in settings (the global VS Code telemetry setting is respected too)

</details>

<details>
<summary><b>What's the difference between the VSCode extension and the CLI?</b></summary>

Same engine, two interfaces:
- **CLI** (`pip install fixfleet`) — interactive terminal flow (GitLab), plus flags for everything: `--file bugs.xlsx --auto-fix` fixes a bug file in one command; `--list-bugs-json --provider github ...` for the other trackers.
- **VSCode extension** — premium UI sidebar, 💬 chat, and click-to-fix workflow for all 6 trackers and bug files; calls the CLI under the hood

Install both if you want flexibility. Extension auto-installs the CLI on first run if missing.

</details>

<details>
<summary><b>Will it ever commit or push my changes?</b></summary>

Never. FixFleet edits files locally and leaves your working tree dirty. You review the diff (`git diff`), then commit + push manually. This is intentional — AI fixes need human review before shipping.

</details>

<details>
<summary><b>Can I use it without any issue tracker?</b></summary>

Yes — that's the fastest path. Switch Bug Source to **Local bug files (Chat)**, load an **Excel (.xlsx), Word (.docx), or PDF** bug list (any column layout — headers are mapped automatically, embedded screenshots are extracted for the AI to look at), and say `fix all`. No tracker account, no token. PDF needs one optional extra: `pip install "fixfleet[files]"`.

</details>

<details>
<summary><b>What happens to items that aren't real bugs?</b></summary>

FixFleet doesn't blindly "fix" everything on the list:
- **Suggestions / feature requests** (however they're phrased) get **implemented**
- **Reports where the code is actually correct** — the AI inspects the code first and tells you *"checked the code — no defect found"* instead of changing things
- **Items that don't belong to your project** (wrong files/components) are flagged with a warning and skipped
- **Uncertain fixes are undone automatically** and marked "needs review" — a bulk run can never wreck your working tree

</details>

<details>
<summary><b>Which issue trackers are supported?</b></summary>

All six, fully implemented:

| Tracker | Bug filter | Notes |
|---|---|---|
| **GitLab** | label `Bug` | gitlab.com + self-hosted |
| **GitHub** | label `bug` | github.com + Enterprise, PRs auto-filtered |
| **Jira** | Issue Type = Bug | Atlassian Cloud |
| **Linear** | label `Bug` | per-team |
| **Bitbucket** | kind = bug | Cloud only |
| **Azure DevOps** | Work Item Type = Bug | Boards |

Paste any URL — FixFleet auto-detects the provider. See [Token setup guides](#-connect-your-tracker-token-setup-guides).

</details>

<details>
<summary><b>Does it work with self-hosted GitLab / GitHub Enterprise?</b></summary>

Yes. Paste your full URL (e.g. `https://gitlab.mycompany.com/group/project`) and FixFleet auto-detects the host. No config needed.

</details>

<details>
<summary><b>Which AI should I use?</b></summary>

- **Best quality** → Claude Code (Claude Pro)
- **Fastest** → Groq (free Llama 3.3 70B)
- **Biggest free quota** → Google Gemini API
- **Fully offline** → Ollama with `qwen2.5-coder:7b`

</details>

<details>
<summary><b>How is FixFleet different from Cursor / Cody / Copilot?</b></summary>

Those are **autocomplete + chat** tools. FixFleet is a **bug-triage automator** — reads your bug tracker, dispatches each ticket to an AI, scores the fix. They complement each other.

</details>

<details>
<summary><b>Is my code sent to FixFleet servers?</b></summary>

There are no FixFleet servers. Your code goes from your machine → directly to whichever AI provider you pick (Anthropic / OpenAI / Google / Groq / Ollama / etc.) using your own credentials. FixFleet is open-source — read the code and verify.

</details>

---

## 🛡️ Privacy & Security

- 🔒 Tokens typed via `getpass` — never echoed, never written to repo
- 🛡️ Issue content fenced in prompts to prevent prompt-injection from malicious issue authors
- 📂 Config + state stored in `~/.bugfixer.json` / `~/.bugfixer-state.json` (your home dir, never in any repo)
- 🚫 Never commits, never pushes, never collects telemetry

---

## 📜 License

**GPL-3.0-or-later** — see [LICENSE](LICENSE).

This means anyone can use, study, modify, and redistribute FixFleet — but **derivative works must also be open-source under GPL-3**. No closed-source forks. No proprietary repackaging.

Built by **[Yash Koladiya](https://github.com/Yash-Koladiya30)** • © 2026.

---

<div align="center">

**If FixFleet saved you time, drop a ⭐ on the repo**.

[Report a bug](https://github.com/Yash-Koladiya30/fixfleet/issues) · [Request feature](https://github.com/Yash-Koladiya30/fixfleet/issues) · [VSCode Extension](https://marketplace.visualstudio.com/items?itemName=YashKoladiya30.fixfleet) · [PyPI Package](https://pypi.org/project/fixfleet/)

</div>
