"""Google Gemini CLI backend."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class GeminiCLIBackend(Backend):
    name = "gemini"
    display_name = "Gemini CLI (Google)"
    requires_binary = "gemini"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        # --yolo auto-approves all tool calls.
        cmd = [
            "gemini",
            "--yolo",
            "-p",
            prompt,
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
