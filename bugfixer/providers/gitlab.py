"""GitLab issue-tracker provider — fully implemented."""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from .base import (
    Provider,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderNotFoundError,
)


DEFAULT_HOST = "gitlab.com"
PER_PAGE = 100
MAX_PAGES = 20

_SSH_RE = re.compile(r"^(?:ssh://)?(?:git@)?([^:/]+)[:/](.+?)(?:\.git)?/?$")


class GitLabProvider(Provider):
    key = "gitlab"
    display_name = "GitLab"
    tagline = "gitlab.com or self-hosted"
    host_patterns = ("gitlab.",)  # gitlab.com, gitlab.example.com, etc.
    implemented = True
    token_url = "https://gitlab.com/-/user_settings/personal_access_tokens"
    token_scope_hint = "api (read+write) or read_api (read-only)"

    # ── URL parsing ─────────────────────────────────────────────

    def parse_url(self, raw: str) -> tuple:
        if not raw or not raw.strip():
            raise ValueError("empty input")
        s = raw.strip()

        # Numeric ID
        if s.isdigit():
            return DEFAULT_HOST, s

        # http(s) URL
        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            path = parsed.path.lstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            if "/-/" in path:
                path = path.split("/-/")[0]
            path = path.rstrip("/")
            if not host or not path:
                raise ValueError(f"could not parse URL: {raw}")
            return host, path

        # SSH / SCP-style
        m = _SSH_RE.match(s)
        if m and (s.startswith(("ssh://", "git@")) or "@" in s):
            host = m.group(1)
            path = m.group(2).rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return host, path

        # Plain path
        if "/" in s and not s.startswith(("/", ".", "~")):
            if s.startswith("gitlab.com/"):
                return DEFAULT_HOST, s[len("gitlab.com/"):].rstrip("/")
            return DEFAULT_HOST, s.rstrip("/")

        raise ValueError(f"unrecognized project reference: {raw}")

    # ── API ─────────────────────────────────────────────────────

    def fetch_bugs(
        self,
        token: str,
        project_id: str,
        host: str = DEFAULT_HOST,
        date_str: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list:
        host = host or DEFAULT_HOST
        api_base = f"https://{host}/api/v4"
        encoded_project = urllib.parse.quote(project_id, safe="")
        base_url = f"{api_base}/projects/{encoded_project}/issues"

        params = {
            "labels": "Bug",
            "state": "opened",
            "per_page": str(PER_PAGE),
            "order_by": "created_at",
            "sort": "desc",
        }

        if date_from or date_to:
            if date_from:
                params["created_after"] = f"{date_from}T00:00:00Z"
            if date_to:
                params["created_before"] = f"{_next_day(date_to)}T00:00:00Z"
        elif date_str:
            end_date = _next_day(date_str)
            params["created_after"] = f"{date_str}T00:00:00Z"
            params["created_before"] = f"{end_date}T00:00:00Z"

        all_issues = []
        page = 1
        while page <= MAX_PAGES:
            params["page"] = str(page)
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    batch = json.loads(resp.read().decode())
                    next_page = resp.headers.get("X-Next-Page", "").strip()
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise ProviderAuthError(
                        code="token_invalid", status=401,
                        message="GitLab token is invalid or expired. Generate a new one with scope `api` or `read_api`.",
                    )
                if e.code == 403:
                    raise ProviderAuthError(
                        code="token_forbidden", status=403,
                        message="GitLab token lacks required scope. Need `api` or `read_api`.",
                    )
                if e.code == 404:
                    raise ProviderNotFoundError(
                        code="project_not_found", status=404,
                        message=f"Project not found at https://{host}/{project_id}. Check the URL and that your token has access.",
                    )
                raise ProviderError(
                    code=f"http_{e.code}", status=e.code,
                    message=f"GitLab API returned {e.code} {e.reason}",
                )
            except urllib.error.URLError as e:
                raise ProviderNetworkError(
                    code="network_error",
                    message=f"Couldn't reach https://{host} — {e.reason}",
                )

            if not batch:
                break
            all_issues.extend(batch)
            if not next_page:
                break
            page = int(next_page)

        return all_issues


def _next_day(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y-%m-%d")
