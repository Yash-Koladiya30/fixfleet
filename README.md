<div align="center">

<img src="vscode/media/icon.png" alt="FixFleet" width="140" />

# FixFleet

### Auto-fix GitLab bugs with AI agents — directly in VSCode.

*Reads open `Bug` issues, parses stack traces, pre-narrows the search to the right files, dispatches to your AI of choice, and scores fix confidence. All local. No commits. Bring your own AI.*

<p>
  <a href="https://pypi.org/project/fixfleet/"><img src="https://img.shields.io/pypi/v/fixfleet.svg?label=pypi&color=2D6A4F&style=for-the-badge" alt="PyPI" /></a>
  <a href="https://marketplace.visualstudio.com/items?itemName=YashKoladiya30.fixfleet"><img src="https://img.shields.io/visual-studio-marketplace/v/YashKoladiya30.fixfleet?label=vscode&color=722F37&style=for-the-badge" alt="VSCode Marketplace" /></a>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img src="https://img.shields.io/badge/license-GPL_v3-C8A47E?style=for-the-badge" alt="License GPL v3" /></a>
  <img src="https://img.shields.io/badge/python-3.9+-1F2421?style=for-the-badge" alt="Python 3.9+" />
</p>

<p>
  <a href="#-screenshots"><b>Screenshots</b></a> •
  <a href="#-install"><b>Install</b></a> •
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
<br/><sub><b>Welcome</b><br/>3-step onboarding</sub>
</td>
<td width="33%" align="center">
<img src="vscode/media/screenshots/settings-credentials.png" alt="Settings credentials" />
<br/><sub><b>Settings</b><br/>GitLab credentials + project</sub>
</td>
<td width="33%" align="center">
<img src="vscode/media/screenshots/settings-backends.png" alt="Settings backends" />
<br/><sub><b>AI Backends</b><br/>Pick your agent · date filter</sub>
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

1. **Install** the VSCode extension (1 click above)
2. **Get a GitLab token** at https://gitlab.com → Settings → Access Tokens (scope: `read_api`)
3. **Click 🚀 FixFleet icon** in VSCode activity bar → **Configure** → paste token + project URL → save
4. **Click any bug** in sidebar → premium detail panel opens
5. **Click ✨ Fix This Bug with AI** → AI agent reads the code, fixes the bug, scores confidence
6. **Review the diff, commit yourself** — FixFleet never commits or pushes

---

## 🧠 How it works

```
┌─ Open GitLab bug issue
│
├─ Parse: description, steps, expected/actual, stack traces, logs
│
├─ Locate: extract file paths, symbols, stack frames → rank candidates → inline top file
│
├─ Dispatch to AI agent (Claude / Codex / Gemini / Cursor / Aider / Qwen / any free API)
│
├─ Score confidence: diff focus + self-rating + file relevance + hedge density
│
└─ Done — local-only changes ready for your review
```

**Token-aware**: per-issue, session, and daily budgets prevent paid-plan overruns.

**Multi-backend**: detected CLI agents shown as installed; pick one per session.

**Confidence scored**: every fix gets a 0.0–1.0 score so you know which to review first.

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
Triages 50 bugs in the time it takes you to read 5.

### vs. AI inside the issue (e.g. GitLab Duo)
- **Costs nothing extra** — uses AI plans you already pay for
- **Edits actual files locally**, not just comments
- **You pick the AI** — not locked to one vendor
- **Works on private/self-hosted GitLab** without exposing source to a SaaS

### vs. running Claude/Codex CLI manually
- **Structured prompts** — extracts steps/logs automatically
- **Pre-narrows file scope** — saves 60–80% tokens
- **Confidence scoring** — review only uncertain fixes
- **Budget caps** — never blows through paid quotas

---

## ❓ FAQ

<details>
<summary><b>Does this use any paid backend / hidden costs?</b></summary>

No. FixFleet runs **100% locally** on your machine. No FixFleet servers, no Azure, no cloud component. You pay for nothing beyond AI plans you already own. The VSCode extension is free. The PyPI package is free. Updates forever, free.

</details>

<details>
<summary><b>What's the difference between the VSCode extension and the CLI?</b></summary>

Same engine, two interfaces:
- **CLI** (`pip install fixfleet`) — interactive terminal flow, beautiful styled output
- **VSCode extension** — premium UI sidebar + click-to-fix workflow, calls the CLI under the hood

Install both if you want flexibility. Extension auto-installs the CLI on first run if missing.

</details>

<details>
<summary><b>Will it ever commit or push my changes?</b></summary>

Never. FixFleet edits files locally and leaves your working tree dirty. You review the diff (`git diff`), then commit + push manually. This is intentional — AI fixes need human review before shipping.

</details>

<details>
<summary><b>Does it work with self-hosted GitLab?</b></summary>

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
