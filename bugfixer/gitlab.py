"""Backwards-compat shim — original GitLab module API preserved.

Real implementation lives in `bugfixer.providers.gitlab`.
This file keeps existing imports (`from bugfixer.gitlab import fetch_bug_issues`)
and tests working without changes.

New code should use `bugfixer.providers.get_provider("gitlab")`.
"""

from typing import Optional

from .providers.gitlab import GitLabProvider, DEFAULT_HOST
# Re-export errors under the old names for backwards compat.
from .providers.base import (
    ProviderAuthError as GitLabAuthError,
    ProviderError as GitLabError,
    ProviderNetworkError as GitLabNetworkError,
    ProviderNotFoundError as GitLabNotFoundError,
)

_provider = GitLabProvider()


def parse_project_input(raw: str) -> tuple:
    """Return (host, project_path). Delegates to GitLabProvider."""
    return _provider.parse_url(raw)


def fetch_bug_issues(
    token: str,
    project_id: str,
    date_str: Optional[str] = None,
    host: str = DEFAULT_HOST,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list:
    """Fetch all open Bug-labeled issues. Delegates to GitLabProvider."""
    return _provider.fetch_bugs(
        token=token,
        project_id=project_id,
        host=host,
        date_str=date_str,
        date_from=date_from,
        date_to=date_to,
    )


# Backwards-compat constant
GITLAB_API_BASE = f"https://{DEFAULT_HOST}/api/v4"


__all__ = [
    "fetch_bug_issues",
    "parse_project_input",
    "GitLabError",
    "GitLabAuthError",
    "GitLabNotFoundError",
    "GitLabNetworkError",
    "DEFAULT_HOST",
    "GITLAB_API_BASE",
]
