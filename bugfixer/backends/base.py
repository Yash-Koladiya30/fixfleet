"""Backend interface contract."""

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    skipped: bool = False
    skip_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.skipped


class Backend(ABC):
    """Abstract backend. Implementations wrap a CLI or API."""

    name: str = "base"
    display_name: str = "Base"
    requires_binary: str = ""  # name of binary on PATH, empty = no requirement

    def available(self) -> bool:
        """Return True if backend can be used right now (binary present, key set, etc)."""
        if self.requires_binary:
            return shutil.which(self.requires_binary) is not None
        return True

    def version(self) -> str:
        """Best-effort version string. Empty if unknown."""
        if not self.requires_binary:
            return ""
        try:
            out = subprocess.run(
                [self.requires_binary, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
        except Exception:
            return ""

    @abstractmethod
    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        """Execute the backend against `prompt` inside `project_dir`. Return RunResult."""
        raise NotImplementedError
