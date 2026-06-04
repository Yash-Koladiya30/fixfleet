"""Jira provider — stub. UI visible, not yet implemented."""

import urllib.parse

from .base import Provider, ProviderNotImplementedError


class JiraProvider(Provider):
    key = "jira"
    display_name = "Jira"
    tagline = "Atlassian Cloud or self-hosted"
    host_patterns = ("atlassian.net", ".jira.")
    implemented = False
    token_url = "https://id.atlassian.com/manage-profile/security/api-tokens"
    token_scope_hint = "API token (paste email + token combined)"

    def parse_url(self, raw: str) -> tuple:
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            # Jira project key after /browse/ or /jira/projects/<KEY>
            path = parsed.path
            for marker in ("/browse/", "/jira/projects/", "/projects/"):
                if marker in path:
                    key = path.split(marker, 1)[1].split("/", 1)[0]
                    return host, key.upper()
            raise ValueError(f"could not find Jira project key in URL: {raw}")

        # Bare project key (e.g. PROJ)
        if s.isalnum() and s.isupper():
            return "", s

        raise ValueError(f"unrecognized Jira reference: {raw}")

    def fetch_bugs(self, *args, **kwargs):
        raise ProviderNotImplementedError("Jira")
