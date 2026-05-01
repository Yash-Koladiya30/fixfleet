"""OpenAI Codex CLI backend."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class CodexCLIBackend(Backend):
    name = "codex"
    display_name = "Codex (OpenAI)"
    requires_binary = "codex"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        # `codex exec` is the non-interactive mode; --full-auto auto-approves edits within sandbox.
        cmd = [
            "codex",
            "exec",
            "--full-auto",
            prompt,
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
