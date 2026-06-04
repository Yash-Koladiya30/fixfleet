"""Jira provider — Atlassian Cloud REST API v3 + JQL.

Endpoint: https://{your-domain}.atlassian.net/rest/api/3/search
Auth: Basic (email:api-token, base64-encoded)

User must paste token as: 'email@example.com:atlassian-api-token'
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


PER_PAGE = 50
MAX_PAGES = 20


class JiraProvider(Provider):
    key = "jira"
    display_name = "Jira"
    tagline = "Atlassian Cloud (*.atlassian.net)"
    host_patterns = ("atlassian.net",)
    implemented = True
    token_url = "https://id.atlassian.com/manage-profile/security/api-tokens"
    token_scope_hint = "Token format: email@example.com:atlassian-api-token (combine with colon)"

    # ── URL parsing ─────────────────────────────────────────────

    def parse_url(self, raw: str) -> tuple:
        """Return (host, project_key).

        Accept:
          - https://acme.atlassian.net/jira/projects/MYPROJ
          - https://acme.atlassian.net/jira/software/projects/MYPROJ/boards/1
          - https://acme.atlassian.net/browse/MYPROJ-42
          - bare project key like "MYPROJ"  (host must be set separately via config)
        """
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            path = parsed.path
            # /browse/MYPROJ-42 → MYPROJ
            for marker in ("/browse/", "/jira/projects/", "/jira/software/projects/", "/projects/"):
                if marker in path:
                    rest = path.split(marker, 1)[1]
                    candidate = rest.split("/", 1)[0]
                    # Strip trailing -NN if browse URL
                    if "-" in candidate and candidate.split("-")[-1].isdigit():
                        candidate = candidate.rsplit("-", 1)[0]
                    return host, candidate.upper()
            raise ValueError(f"could not find Jira project key in URL: {raw}")

        if s.isalnum():
            return "", s.upper()

        raise ValueError(f"unrecognized Jira reference: {raw}")

    # ── API ─────────────────────────────────────────────────────

    def fetch_bugs(
        self,
        token: str,
        project_id: str,
        host: str = "",
        date_str: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list:
        if ":" not in token:
            raise ProviderAuthError(
                code="token_invalid", status=400,
                message="Jira token must be `email:api-token` (with the colon).",
            )
        if not host:
            raise ProviderNotFoundError(
                code="project_not_found", status=400,
                message="Jira host missing. Paste the full URL (https://yourcompany.atlassian.net/...) so the host can be detected.",
            )

        auth = base64.b64encode(token.encode()).decode()
        base_url = f"https://{host}/rest/api/3/search"

        # Build JQL
        jql_parts = [f'project = "{project_id}"', 'issuetype = "Bug"', 'statusCategory != Done']
        if date_from:
            jql_parts.append(f'created >= "{date_from}"')
        elif date_str:
            jql_parts.append(f'created >= "{date_str}"')
        if date_to:
            jql_parts.append(f'created <= "{date_to}"')
        jql = " AND ".join(jql_parts) + " ORDER BY created DESC"

        results = []
        start_at = 0
        page = 0
        while page < MAX_PAGES:
            params = {
                "jql": jql,
                "startAt": str(start_at),
                "maxResults": str(PER_PAGE),
                "fields": "summary,description,labels,priority,created,updated,creator,reporter,issuetype,status",
            }
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
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
                        message="Jira credentials invalid. Check `email:api-token` format and token validity.",
                    )
                if e.code == 403:
                    raise ProviderAuthError(
                        code="token_forbidden", status=403,
                        message="Jira account lacks permission to browse this project.",
                    )
                if e.code == 404:
                    raise ProviderNotFoundError(
                        code="project_not_found", status=404,
                        message=f"Jira project '{project_id}' not found at https://{host}.",
                    )
                raise ProviderError(
                    code=f"http_{e.code}", status=e.code,
                    message=f"Jira API returned {e.code} {e.reason}",
                )
            except urllib.error.URLError as e:
                raise ProviderNetworkError(
                    code="network_error",
                    message=f"Couldn't reach https://{host} — {e.reason}",
                )

            issues_batch = data.get("issues", [])
            for raw_issue in issues_batch:
                results.append(self._normalize(raw_issue, host, project_id))

            total = data.get("total", 0)
            start_at += len(issues_batch)
            if start_at >= total or not issues_batch:
                break
            page += 1

        return results

    def _normalize(self, issue: dict, host: str, project_id: str) -> dict:
        fields = issue.get("fields", {}) or {}
        labels = list(fields.get("labels", []) or [])

        priority = (fields.get("priority") or {}).get("name", "")
        # Map Jira priorities → FixFleet labels
        priority_map = {
            "Highest": "High", "Blocker": "High", "Critical": "High",
            "High": "High",
            "Medium": "Medium",
            "Low": "Low", "Lowest": "Low",
        }
        if priority in priority_map:
            labels.append(priority_map[priority])

        creator = fields.get("creator") or fields.get("reporter") or {}
        key = issue.get("key", "")
        # Jira description is now Atlassian Document Format (ADF) — extract plain text best-effort
        description = self._extract_adf_text(fields.get("description"))

        return {
            "iid": key,  # e.g. "MYPROJ-42" — string, not int
            "title": fields.get("summary", ""),
            "description": description,
            "labels": labels,
            "created_at": fields.get("created", ""),
            "updated_at": fields.get("updated", ""),
            "web_url": f"https://{host}/browse/{key}",
            "author": {"username": creator.get("displayName") or creator.get("emailAddress", "")},
        }

    def _extract_adf_text(self, adf) -> str:
        """Recursively pull plain text out of Atlassian Document Format."""
        if adf is None:
            return ""
        if isinstance(adf, str):
            return adf
        if isinstance(adf, dict):
            parts = []
            if adf.get("type") == "text":
                parts.append(adf.get("text", ""))
            for child in adf.get("content", []) or []:
                parts.append(self._extract_adf_text(child))
            # Add a blank line after paragraphs/headings/lists
            if adf.get("type") in ("paragraph", "heading", "bulletList", "orderedList"):
                parts.append("\n")
            return "".join(parts)
        if isinstance(adf, list):
            return "".join(self._extract_adf_text(x) for x in adf)
        return ""
