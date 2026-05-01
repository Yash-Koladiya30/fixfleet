"""Qwen Code CLI backend (forked from Gemini CLI)."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class QwenCLIBackend(Backend):
    name = "qwen"
    display_name = "Qwen Code (Alibaba)"
    requires_binary = "qwen"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        cmd = [
            "qwen",
            "--yolo",
            "-p",
            prompt,
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
