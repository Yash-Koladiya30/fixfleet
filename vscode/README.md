# 🚀 FixFleet — VSCode Extension

> **Auto-fix GitLab bugs with AI agents — directly inside VSCode.**

Premium UI on top of the [FixFleet](https://github.com/Yash-Koladiya30/fixfleet) Python CLI.

---

## 📸 Screenshots

### Welcome — 3-step onboarding

![Welcome screen](media/screenshots/welcome.png)

### Settings — GitLab credentials + project

![Settings credentials](media/screenshots/settings-credentials.png)

### Settings — AI backend grid + date filter

![Settings backends](media/screenshots/settings-backends.png)

---

## ✨ Features

- 🐛 **Sidebar bug list** with priority badges (High / Medium / Low) sorted by priority
- 📅 **Date range filter** — From / To inputs in the sidebar toolbar
- ☑️ **Multi-select + batch fix** — tick multiple bugs, fix sequentially with live progress bar
- 🎨 **Premium webview** for each bug — description, steps, expected/actual, logs all parsed automatically
- ✨ **One-click "Fix this bug"** — dispatches to your chosen AI agent
- 📊 **Confidence score** — see how sure the AI is before reviewing
- ⚙️ **Visual settings** — configure token, project, backend without touching JSON
- 🎯 **Multi-backend support** — Claude Code, Codex, Gemini, Cursor, Aider, Qwen, or any OpenAI-compatible API
- 🔐 **Structured error states** — 🔐 Token rejected · 📭 Project not found · 🌐 Network error · 📦 CLI missing — each with one-click recovery
- 🔁 **Status bar** — live count of open bugs and current fix progress

## 📦 Install

### From VSCode Marketplace
Search `FixFleet` in the Extensions panel.

### Manual
```bash
code --install-extension fixfleet-0.1.2.vsix
```

## 🛠 Setup

1. Install the FixFleet CLI (Python):
   ```bash
   pip3 install --user fixfleet
   ```
   Add user-bin to PATH (one-time):
   ```bash
   echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```
2. Open VSCode → click the 🚀 FixFleet icon in the activity bar
3. Click **Configure FixFleet**
4. Paste your GitLab token + project URL → save
5. Click any bug in the sidebar → see detail → click **Fix This Bug**

## 🎨 Design

Premium natural palette extracted from the FixFleet icon:
- Forest green + cream ivory + walnut brown + champagne gold
- Glassmorphism cards adapting to light + dark themes
- Confidence gradient bars
- Per-card status badges with pulsing animation during fix

## 📝 License

**GNU General Public License v3.0 or later (GPL-3.0-or-later)** — see [LICENSE](LICENSE).

Derivative works must also be open-source under GPL-3. No closed-source forks.

Built by [Yash Koladiya](https://github.com/Yash-Koladiya30). © 2026.
