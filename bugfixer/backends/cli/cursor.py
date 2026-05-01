"""Cursor Agent CLI backend."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class CursorAgentBackend(Backend):
    name = "cursor"
    display_name = "Cursor Agent"
    requires_binary = "cursor-agent"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        # -p / --print prints output non-interactively.
        cmd = [
            "cursor-agent",
            "-p",
            prompt,
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
