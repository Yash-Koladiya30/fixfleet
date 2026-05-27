# 🚀 FixFleet — VSCode Extension

> **Auto-fix GitLab bugs with AI agents — directly inside VSCode.**

Premium UI on top of the [FixFleet](https://github.com/Yash-Koladiya30/fixfleet) Python CLI.

---

## ✨ Features

- 🐛 **Sidebar tree view** of open GitLab `Bug` issues, sorted by priority
- 🎨 **Premium webview** for each bug — description, steps, expected/actual, logs all parsed
- ✨ **One-click "Fix this bug"** — dispatches to your chosen AI agent
- 📊 **Confidence score** — see how sure the AI is before reviewing
- ⚙️ **Visual settings** — configure token, project, backend without touching JSON
- 🎯 **Multi-backend support** — Claude Code, Codex, Gemini, Cursor, Aider, Qwen, or any OpenAI-compatible API

## 📦 Install

### From VSCode Marketplace
Search `FixFleet` in the Extensions panel.

### Manual
```bash
code --install-extension fixfleet-0.1.0.vsix
```

## 🛠 Setup

1. Install the FixFleet CLI (Python):
   ```bash
   pip3 install --user fixfleet
   ```
2. Open VSCode → click the 🚀 FixFleet icon in the activity bar
3. Click **Configure FixFleet**
4. Paste your GitLab token + project URL → save
5. Click any bug in the sidebar → see detail → click **Fix This Bug**

## 🎨 Design

Premium classic palette:
- Royal indigo + champagne gold accents
- Glassmorphism cards
- Confidence gradient bars
- Adapts to light + dark themes

## 📝 License

**GNU General Public License v3.0 or later (GPL-3.0-or-later)** — see [LICENSE](LICENSE).

Derivative works must also be open-source under GPL-3. No closed-source forks.

Built by [Yash Koladiya](https://github.com/Yash-Koladiya30). © 2026.
