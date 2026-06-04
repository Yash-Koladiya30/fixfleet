"""Issue-tracker provider abstraction.

Fully implemented: GitLab, GitHub, Bitbucket, Jira, Linear, Azure DevOps.

Add a new provider:
  1. Create bugfixer/providers/<name>.py implementing Provider.
  2. Register it in bugfixer/providers/registry.py.
"""

from .base import (
    Provider,
    ProviderError,
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderNetworkError,
    ProviderNotImplementedError,
)
from .registry import (
    PROVIDERS,
    ALL_PROVIDER_KEYS,
    get_provider,
    detect_provider_from_url,
)

__all__ = [
    "Provider",
    "ProviderError",
    "ProviderAuthError",
    "ProviderNotFoundError",
    "ProviderNetworkError",
    "ProviderNotImplementedError",
    "PROVIDERS",
    "ALL_PROVIDER_KEYS",
    "get_provider",
    "detect_provider_from_url",
]
