"""Bitbucket provider — Bitbucket Cloud REST API v2.

  GET /2.0/repositories/{owner}/{repo}/issues?q=kind="bug" AND state="open"
  Auth: Basic (username:app-password)

Note: Bitbucket Server (on-prem) uses a different API — not supported here.
"""

import base64
import json
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


DEFAULT_HOST = "bitbucket.org"
API_HOST = "api.bitbucket.org"
PER_PAGE = 50
MAX_PAGES = 20


class BitbucketProvider(Provider):
    key = "bitbucket"
    display_name = "Bitbucket"
    tagline = "bitbucket.org (Cloud)"
    host_patterns = ("bitbucket.org",)
    implemented = True
    token_url = "https://bitbucket.org/account/settings/app-passwords/"
    token_scope_hint = "App password — paste as `username:app-password` (combined with colon)"

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
            parts = path.split("/")
            if len(parts) < 2:
                raise ValueError(f"need workspace/repo, got: {raw}")
            return host, f"{parts[0]}/{parts[1]}"

        if "/" in s and not s.startswith(("/", ".", "~")):
            return DEFAULT_HOST, s.rstrip("/")

        raise ValueError(f"unrecognized Bitbucket reference: {raw}")

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
        # Token must be "username:app-password"
        if ":" not in token:
            raise ProviderAuthError(
                code="token_invalid", status=400,
                message="Bitbucket token must be `username:app-password` (with the colon).",
            )

        auth = base64.b64encode(token.encode()).decode()
        base_url = f"https://{API_HOST}/2.0/repositories/{project_id}/issues"

        # Build BBQL query
        query_parts = ['kind="bug"', 'state="open"']
        if date_from:
            query_parts.append(f'created_on >= {date_from}T00:00:00Z')
        elif date_str:
            query_parts.append(f'created_on >= {date_str}T00:00:00Z')
        if date_to:
            query_parts.append(f'created_on <= {date_to}T23:59:59Z')

        params = {
            "q": " AND ".join(query_parts),
            "pagelen": str(PER_PAGE),
            "sort": "-created_on",
        }

        results = []
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        page = 0
        while page < MAX_PAGES and url:
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Basic {auth}",
                    "Accept": "application/json",
                    "User-Agent": "fixfleet",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise ProviderAuthError(
                        code="token_invalid", status=401,
                        message="Bitbucket app password is invalid or expired.",
                    )
                if e.code == 403:
                    raise ProviderAuthError(
                        code="token_forbidden", status=403,
                        message="Bitbucket token lacks `issues:read` scope.",
                    )
                if e.code == 404:
                    raise ProviderNotFoundError(
                        code="project_not_found", status=404,
                        message=f"Repository not found at https://{host}/{project_id}.",
                    )
                raise ProviderError(
                    code=f"http_{e.code}", status=e.code,
                    message=f"Bitbucket API returned {e.code} {e.reason}",
                )
            except urllib.error.URLError as e:
                raise ProviderNetworkError(
                    code="network_error",
                    message=f"Couldn't reach https://{API_HOST} — {e.reason}",
                )

            for raw_issue in data.get("values", []):
                results.append(self._normalize(raw_issue, host, project_id))

            url = data.get("next")  # full URL for next page or None
            page += 1

        return results

    def _normalize(self, issue: dict, host: str, project_id: str) -> dict:
        kind = issue.get("kind", "")
        priority = issue.get("priority", "")
        labels = []
        if kind:
            labels.append(kind.capitalize())
        if priority:
            # Map BB priority to FixFleet priority labels
            mapping = {
                "trivial": "Low", "minor": "Low",
                "major": "Medium",
                "critical": "High", "blocker": "High",
            }
            labels.append(mapping.get(priority.lower(), priority.capitalize()))

        reporter = issue.get("reporter") or {}
        bb_id = issue.get("id", 0)
        return {
            "iid": bb_id,
            "title": issue.get("title", ""),
            "description": (issue.get("content") or {}).get("raw") or "",
            "labels": labels,
            "created_at": issue.get("created_on", ""),
            "updated_at": issue.get("updated_on", ""),
            "web_url": f"https://{host}/{project_id}/issues/{bb_id}",
            "author": {"username": reporter.get("display_name") or reporter.get("nickname", "")},
        }
