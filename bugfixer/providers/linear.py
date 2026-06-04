"""Linear provider — stub. UI visible, not yet implemented."""

import urllib.parse

from .base import Provider, ProviderNotImplementedError


class LinearProvider(Provider):
    key = "linear"
    display_name = "Linear"
    tagline = "linear.app workspace"
    host_patterns = ("linear.app",)
    implemented = False
    token_url = "https://linear.app/settings/api"
    token_scope_hint = "Personal API key (starts with lin_api_)"

    def parse_url(self, raw: str) -> tuple:
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            # linear.app/<workspace>/team/<TEAM>/...
            path = parsed.path.strip("/").split("/")
            if len(path) >= 1:
                workspace = path[0]
                return host, workspace
            raise ValueError(f"could not parse Linear URL: {raw}")

        # Bare workspace name
        return "linear.app", s.lower()

    def fetch_bugs(self, *args, **kwargs):
        raise ProviderNotImplementedError("Linear")
