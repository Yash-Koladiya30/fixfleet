"""GitHub provider — stub. UI visible, not yet implemented."""

import re
import urllib.parse

from .base import Provider, ProviderNotImplementedError


class GitHubProvider(Provider):
    key = "github"
    display_name = "GitHub"
    tagline = "github.com or GitHub Enterprise"
    host_patterns = ("github.", "github.com")
    implemented = False
    token_url = "https://github.com/settings/tokens"
    token_scope_hint = "repo (full) or public_repo (public only)"

    def parse_url(self, raw: str) -> tuple:
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            path = parsed.path.lstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            # Strip trailing /issues, /pulls, etc.
            path = re.sub(r"/(issues|pulls|wiki|actions|projects)(/.*)?$", "", path)
            path = path.rstrip("/")
            parts = path.split("/")
            if len(parts) < 2:
                raise ValueError(f"need owner/repo, got: {raw}")
            return host, f"{parts[0]}/{parts[1]}"

        if s.startswith("git@github.com:"):
            path = s.split(":", 1)[1].rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return "github.com", path

        if "/" in s and not s.startswith(("/", ".", "~")):
            return "github.com", s.rstrip("/")

        raise ValueError(f"unrecognized GitHub reference: {raw}")

    def fetch_bugs(self, *args, **kwargs):
        raise ProviderNotImplementedError("GitHub")
