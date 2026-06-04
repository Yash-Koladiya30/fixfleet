"""GitHub provider — fully implemented.

REST API v3:
  GET /repos/{owner}/{repo}/issues?state=open&labels=bug
  Auth: 'Authorization: Bearer <PAT>'

Filters out pull requests (GitHub's issues endpoint returns both).
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from .base import (
    Provider,
    ProviderAuthError,
    ProviderError,
    ProviderNetworkError,
    ProviderNotFoundError,
)


DEFAULT_HOST = "github.com"
API_HOST_MAP = {"github.com": "api.github.com"}
PER_PAGE = 100
MAX_PAGES = 20


class GitHubProvider(Provider):
    key = "github"
    display_name = "GitHub"
    tagline = "github.com or GitHub Enterprise"
    host_patterns = ("github.", "github.com")
    implemented = True
    token_url = "https://github.com/settings/tokens"
    token_scope_hint = "repo (full) or public_repo (public only)"

    # ── URL parsing ─────────────────────────────────────────────

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
            path = re.sub(r"/(issues|pulls|wiki|actions|projects|tree|blob)(/.*)?$", "", path)
            path = path.rstrip("/")
            parts = path.split("/")
            if len(parts) < 2:
                raise ValueError(f"need owner/repo, got: {raw}")
            return host, f"{parts[0]}/{parts[1]}"

        if s.startswith("git@") and ":" in s:
            host, path = s.split(":", 1)
            host = host.split("@", 1)[1]
            path = path.rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return host, path

        if "/" in s and not s.startswith(("/", ".", "~")):
            return DEFAULT_HOST, s.rstrip("/")

        raise ValueError(f"unrecognized GitHub reference: {raw}")

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
        api_host = API_HOST_MAP.get(host or DEFAULT_HOST, f"{host}/api/v3")
        base_url = f"https://{api_host}/repos/{project_id}/issues"

        params = {
            "state": "open",
            "labels": "bug",
            "per_page": str(PER_PAGE),
            "sort": "created",
            "direction": "desc",
        }
        # GitHub supports `since=ISO` for updated_at filter — we use as best-effort created filter
        if date_from:
            params["since"] = f"{date_from}T00:00:00Z"
        elif date_str:
            params["since"] = f"{date_str}T00:00:00Z"

        results = []
        page = 1
        while page <= MAX_PAGES:
            params["page"] = str(page)
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "fixfleet",
                },
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    batch = json.loads(resp.read().decode())
                    link_header = resp.headers.get("Link", "")
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise ProviderAuthError(
                        code="token_invalid", status=401,
                        message="GitHub token is invalid or expired. Generate a new one with scope `repo` or `public_repo`.",
                    )
                if e.code == 403:
                    # Could be rate limit OR scope issue
                    raise ProviderAuthError(
                        code="token_forbidden", status=403,
                        message="GitHub token lacks required scope or rate limit exceeded. Need `repo` scope.",
                    )
                if e.code == 404:
                    raise ProviderNotFoundError(
                        code="project_not_found", status=404,
                        message=f"Repository not found at https://{host}/{project_id}. Check the URL and that your token has access.",
                    )
                raise ProviderError(
                    code=f"http_{e.code}", status=e.code,
                    message=f"GitHub API returned {e.code} {e.reason}",
                )
            except urllib.error.URLError as e:
                raise ProviderNetworkError(
                    code="network_error",
                    message=f"Couldn't reach https://{api_host} — {e.reason}",
                )

            if not batch:
                break

            # Filter out pull requests (GitHub's /issues endpoint returns both)
            for raw_issue in batch:
                if raw_issue.get("pull_request"):
                    continue
                # Optional client-side date_to filter (GitHub only supports `since`)
                if date_to:
                    created = raw_issue.get("created_at", "")[:10]
                    if created > date_to:
                        continue
                results.append(self._normalize(raw_issue, host, project_id))

            # Pagination via Link header
            if 'rel="next"' not in link_header:
                break
            page += 1

        return results

    def _normalize(self, issue: dict, host: str, project_id: str) -> dict:
        """Map GitHub issue shape to the unified shape consumed by parser/json_api.

        Unified keys: iid, title, description, labels, created_at, updated_at,
        web_url, author.
        """
        labels_raw = issue.get("labels", []) or []
        labels = []
        for lbl in labels_raw:
            if isinstance(lbl, dict):
                name = lbl.get("name", "")
            else:
                name = str(lbl)
            if name:
                labels.append(name)

        user = issue.get("user") or {}
        return {
            "iid": issue.get("number") or issue.get("id") or 0,
            "title": issue.get("title", ""),
            "description": issue.get("body") or "",
            "labels": labels,
            "created_at": issue.get("created_at", ""),
            "updated_at": issue.get("updated_at", ""),
            "web_url": issue.get("html_url", f"https://{host}/{project_id}/issues/{issue.get('number')}"),
            "author": {"username": user.get("login", "")},
        }
