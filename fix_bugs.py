#!/usr/bin/env python3
"""FixFleet — Fleet of AI agents fixing GitLab bugs.

Reads open bug issues from GitLab, parses their description (including
"Steps to Reproduce", expected/actual behavior, environment, logs), pre-narrows
the search space, and dispatches a structured prompt to your chosen AI agent
(Claude Code, Codex, Gemini, Cursor, Aider, Qwen, or any OpenAI-compatible API)
to fix them locally.

No commits or pushes — you review and commit yourself.

Built by Yash Koladiya.
"""

from bugfixer.cli import main

if __name__ == "__main__":
    main()
