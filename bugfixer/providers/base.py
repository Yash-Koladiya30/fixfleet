"""Provider abstract base class + shared exception types.

Each issue-tracker integration (GitLab, GitHub, Jira, Linear, ...) implements
this interface so the rest of the codebase (json_api, prompt builder, locator,
extension) can stay provider-agnostic.
"""

from abc import ABC, abstractmethod
from typing import Optional


# ── Errors ────────────────────────────────────────────────────────

class ProviderError(Exception):
    """Base provider error. Carries a stable `code` so JSON callers can react."""

    def __init__(self, code: str, message: str, status: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "status": self.status}


class ProviderAuthError(ProviderError):
    """Token invalid, expired, or lacks scope."""


class ProviderNotFoundError(ProviderError):
    """Project / repo / workspace not found OR token has no access."""


class ProviderNetworkError(ProviderError):
    """Couldn't reach the provider host (DNS, connection refused, timeout)."""


class ProviderNotImplementedError(ProviderError):
    """Provider is registered but not yet fully implemented."""

    def __init__(self, provider_name: str):
        super().__init__(
            code="not_implemented",
            message=(
                f"FixFleet support for {provider_name} is on the roadmap but not yet "
                f"implemented. Only GitLab is fully supported today. "
                f"Track progress at https://github.com/Yash-Koladiya30/fixfleet/issues"
            ),
        )


# ── Provider interface ───────────────────────────────────────────

class Provider(ABC):
    """Abstract issue-tracker provider."""

    #: Stable identifier used in config, JSON API, and UI dropdowns.
    key: str = "base"

    #: Human-readable name shown in UI.
    display_name: str = "Base"

    #: Shortest description for help text.
    tagline: str = ""

    #: Hostname patterns that signal this provider (e.g. ["gitlab.com"]).
    host_patterns: tuple = ()

    #: Whether this provider is fully implemented. UI shows "coming soon"
    #: badge when False.
    implemented: bool = False

    #: Token URL — where users go to generate a credential.
    token_url: str = ""

    #: Required token scope description (shown in UI).
    token_scope_hint: str = ""

    @classmethod
    def matches_url(cls, url: str) -> bool:
        """Heuristic: does this provider own this URL?"""
        if not url:
            return False
        lower = url.lower()
        return any(p in lower for p in cls.host_patterns)

    @abstractmethod
    def parse_url(self, raw: str) -> tuple:
        """Parse user-supplied input into (host, project_id).

        Should accept full URL, short path, .git URL, ssh URL, numeric ID.
        Raises ValueError on bad input.
        """

    @abstractmethod
    def fetch_bugs(
        self,
        token: str,
        project_id: str,
        host: str,
        date_str: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list:
        """Fetch open bug issues. Return list of raw provider-shaped dicts.

        Each dict should at minimum contain:
          iid, title, description, labels, created_at, updated_at, web_url, author
        """
