"""Claude Code CLI backend."""

from ..base import Backend, RunResult
from .._subprocess import run_with_tee


class ClaudeCLIBackend(Backend):
    name = "claude"
    display_name = "Claude Code (Anthropic)"
    requires_binary = "claude"

    DEFAULT_ALLOWED_TOOLS = "Read,Edit,Write,Grep,Glob,Bash"

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        cmd = [
            "claude",
            "--print",
            prompt,
            "--allowedTools",
            self.DEFAULT_ALLOWED_TOOLS,
        ]
        return run_with_tee(cmd, cwd=project_dir, timeout=timeout)
