"""OpenAI-compatible API backend.

Works with: Groq, OpenRouter, Gemini (compat endpoint), Cerebras, Mistral,
Together, DeepSeek, Ollama (localhost), LM Studio, vLLM, etc.

Strategy: send prompt + a hint about repo structure, expect a unified diff
back. Apply the diff with `git apply` (or `patch`) inside project_dir.
No agentic tool-use loop — keeps token usage minimal.
"""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..base import Backend, RunResult


SYSTEM_PROMPT = """You are an expert software engineer fixing bugs in a codebase.

You CANNOT execute tools. You will be given a bug description and a list of likely-relevant files (with their contents inlined where possible). Output a fix as a unified diff.

OUTPUT FORMAT (strict):
1. Brief explanation (2-4 lines) of the root cause.
2. A unified diff inside a single fenced block tagged ```diff
3. End with the FIX REPORT block exactly as instructed in the user prompt.

The diff MUST:
- Use standard unified-diff format (--- a/path, +++ b/path, @@ hunks).
- Use forward-slash paths relative to the repo root.
- Include enough context (3 lines) for `git apply` to work.
- Not contain any prose between the fence markers.
"""


class OpenAICompatBackend(Backend):
    name = "openai_compat"
    display_name = "OpenAI-Compatible API"
    requires_binary = ""  # network-only

    def __init__(self, base_url: str, api_key: str, model: str,
                 max_output_tokens: int = 4096, temperature: float = 0.1,
                 apply_diff: bool = True):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature
        self.apply_diff = apply_diff

    def available(self) -> bool:
        return bool(self.base_url) and bool(self.model)

    def version(self) -> str:
        return f"{self.model} @ {self.base_url}"

    def _chat(self, messages: list, timeout: int) -> dict:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}" if self.api_key else "",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def run(self, prompt: str, project_dir: str, timeout: int = 600) -> RunResult:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._chat(messages, timeout=timeout)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="ignore")
            return RunResult(returncode=e.code, stderr=f"HTTP {e.code}: {err_body[:500]}")
        except urllib.error.URLError as e:
            return RunResult(returncode=2, stderr=f"Network error: {e.reason}")
        except Exception as e:
            return RunResult(returncode=3, stderr=f"Unexpected error: {e}")

        try:
            content = response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            return RunResult(returncode=4, stderr=f"Bad response shape: {json.dumps(response)[:500]}")

        # Echo to user so they can read the model's reasoning live.
        print(content, flush=True)

        usage = response.get("usage", {}) or {}
        token_summary = (
            f"\n[tokens] prompt={usage.get('prompt_tokens', '?')} "
            f"completion={usage.get('completion_tokens', '?')} "
            f"total={usage.get('total_tokens', '?')}\n"
        )
        print(token_summary, file=sys.stderr, flush=True)

        if not self.apply_diff:
            return RunResult(returncode=0, stdout=content)

        diff = _extract_diff(content)
        if not diff:
            # Model didn't produce a diff — surface to user but treat as no-op fail.
            return RunResult(
                returncode=5,
                stdout=content,
                stderr="Model did not return a unified diff. No changes applied.",
            )

        rc, msg = _apply_diff(diff, project_dir)
        if rc != 0:
            return RunResult(returncode=rc, stdout=content, stderr=f"Diff apply failed: {msg}")

        return RunResult(returncode=0, stdout=content + "\n[diff applied successfully]")


# ── Diff extraction + apply ────────────────────────────────────

DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)\n```", re.DOTALL)


def _extract_diff(text: str) -> str:
    """Pull the first fenced diff block out of the model output."""
    matches = DIFF_FENCE_RE.findall(text)
    for m in matches:
        if "---" in m and "+++" in m and "@@" in m:
            return m.strip() + "\n"
    # Fallback: maybe model emitted raw diff without fences
    if text.lstrip().startswith("---") and "+++" in text:
        return text.strip() + "\n"
    return ""


def _apply_diff(diff_text: str, project_dir: str) -> tuple:
    """Try `git apply`, fall back to `patch -p1`. Return (rc, message)."""
    project = Path(project_dir)

    # Use stdin to feed the diff
    try:
        result = subprocess.run(
            ["git", "apply", "--whitespace=fix", "-"],
            input=diff_text,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return 0, "git apply succeeded"
        git_err = result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        git_err = str(e)

    # Try patch as fallback
    try:
        result = subprocess.run(
            ["patch", "-p1", "--forward"],
            input=diff_text,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return 0, "patch succeeded"
        return result.returncode, f"git apply: {git_err}; patch: {result.stderr}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 1, f"git apply: {git_err}; patch unavailable: {e}"
