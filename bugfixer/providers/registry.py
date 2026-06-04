"""Provider registry — list, lookup, auto-detect."""

from .github import GitHubProvider
from .gitlab import GitLabProvider
from .jira import JiraProvider
from .linear import LinearProvider


# Registered providers — order matters for UI dropdown rendering.
PROVIDERS = {
    "gitlab": GitLabProvider(),
    "github": GitHubProvider(),
    "jira":   JiraProvider(),
    "linear": LinearProvider(),
}

ALL_PROVIDER_KEYS = list(PROVIDERS.keys())


def get_provider(key: str):
    """Look up a provider by key. Returns None if unknown."""
    if not key:
        return None
    return PROVIDERS.get(key.lower())


def detect_provider_from_url(url: str):
    """Best-guess which provider a URL belongs to."""
    if not url:
        return None
    for p in PROVIDERS.values():
        if p.matches_url(url):
            return p
    return None


def provider_metadata() -> list:
    """Return JSON-friendly metadata for UI dropdowns."""
    return [
        {
            "key": p.key,
            "display_name": p.display_name,
            "tagline": p.tagline,
            "implemented": p.implemented,
            "token_url": p.token_url,
            "token_scope_hint": p.token_scope_hint,
        }
        for p in PROVIDERS.values()
    ]
