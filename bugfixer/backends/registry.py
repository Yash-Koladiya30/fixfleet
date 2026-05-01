"""Backend registry — list, detect, instantiate."""

from .api.openai_compat import OpenAICompatBackend
from .base import Backend
from .cli.aider import AiderCLIBackend
from .cli.claude import ClaudeCLIBackend
from .cli.codex import CodexCLIBackend
from .cli.cursor import CursorAgentBackend
from .cli.gemini import GeminiCLIBackend
from .cli.qwen import QwenCLIBackend


CLI_BACKENDS = [
    ClaudeCLIBackend,
    CodexCLIBackend,
    GeminiCLIBackend,
    CursorAgentBackend,
    AiderCLIBackend,
    QwenCLIBackend,
]


def list_cli_backends() -> list:
    """Instantiate all CLI backend classes (regardless of availability)."""
    return [cls() for cls in CLI_BACKENDS]


def detect_available_clis() -> list:
    """Return only CLI backends whose binary is on PATH."""
    return [b for b in list_cli_backends() if b.available()]


def detect_unavailable_clis() -> list:
    """Return CLI backends whose binary is missing (for display)."""
    return [b for b in list_cli_backends() if not b.available()]


# ── Free-tier API presets ──────────────────────────────────────

API_PRESETS = {
    "groq": {
        "label": "Groq (free, fast)",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
    },
    "gemini": {
        "label": "Google Gemini (free tier, big quota)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-2.0-flash",
        "key_url": "https://aistudio.google.com/apikey",
    },
    "openrouter": {
        "label": "OpenRouter (free models available)",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "deepseek/deepseek-chat-v3.1:free",
        "key_url": "https://openrouter.ai/keys",
    },
    "cerebras": {
        "label": "Cerebras (free tier, very fast)",
        "base_url": "https://api.cerebras.ai/v1",
        "default_model": "llama-3.3-70b",
        "key_url": "https://cloud.cerebras.ai",
    },
    "ollama": {
        "label": "Ollama (local, no key, free forever)",
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5-coder:7b",
        "key_url": "https://ollama.com",
    },
    "lmstudio": {
        "label": "LM Studio (local, no key)",
        "base_url": "http://localhost:1234/v1",
        "default_model": "local-model",
        "key_url": "https://lmstudio.ai",
    },
    "custom": {
        "label": "Custom OpenAI-compatible endpoint",
        "base_url": "",
        "default_model": "",
        "key_url": "",
    },
}


def build_api_backend(base_url: str, api_key: str, model: str, **kwargs) -> Backend:
    return OpenAICompatBackend(base_url=base_url, api_key=api_key, model=model, **kwargs)
