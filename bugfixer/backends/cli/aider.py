"""Aider CLI backend."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class AiderCLIBackend(Backend):
    name = "aider"
    display_name = "Aider"
    requires_binary = "aider"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        # --yes-always: skip all confirmations.
        # --no-auto-commits: bug fixer manages commits manually (user reviews).
        # --map-tokens 1024: tighter repo map to save tokens.
        # --no-stream: simpler stdout to capture.
        cmd = [
            "aider",
            "--message", prompt,
            "--yes-always",
            "--no-auto-commits",
            "--map-tokens", "1024",
            "--no-stream",
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
