"""Linear provider — GraphQL API.

Endpoint: https://api.linear.app/graphql
Auth: Authorization: <personal API key>  (no Bearer prefix)

Linear's concept of "bug" = label named 'Bug' (configurable per team).
"""

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


API_URL = "https://api.linear.app/graphql"
PAGE_SIZE = 50
MAX_PAGES = 20


# Single GraphQL query — filters by team key + open + label "Bug".
ISSUES_QUERY = """
query Issues($teamKey: String!, $cursor: String, $first: Int!, $createdAfter: DateTime, $createdBefore: DateTime) {
  team(id: $teamKey) {
    id
    key
    name
    issues(
      first: $first,
      after: $cursor,
      filter: {
        state: { type: { in: ["unstarted", "started", "backlog"] } },
        labels: { name: { eqIgnoreCase: "Bug" } },
        createdAt: { gte: $createdAfter, lte: $createdBefore }
      }
      orderBy: createdAt
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        identifier
        number
        title
        description
        createdAt
        updatedAt
        url
        creator { displayName name email }
        labels { nodes { name } }
        priorityLabel
        state { name type }
      }
    }
  }
}
"""


class LinearProvider(Provider):
    key = "linear"
    display_name = "Linear"
    tagline = "linear.app workspace"
    host_patterns = ("linear.app",)
    implemented = True
    token_url = "https://linear.app/settings/api"
    token_scope_hint = "Personal API key (starts with lin_api_)"

    # ── URL parsing ─────────────────────────────────────────────

    def parse_url(self, raw: str) -> tuple:
        """Linear's 'project_id' is a TEAM KEY (e.g. 'ENG', 'BUG').

        Accept:
          - linear.app/<workspace>/team/<TEAM>/all
          - linear.app/<workspace>/team/<TEAM>/active
          - linear.app/<workspace>/issue/<TEAM-123>/...
          - bare team key like "ENG"
        """
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            parts = [p for p in parsed.path.split("/") if p]
            # /<workspace>/team/<TEAM>/...
            if len(parts) >= 3 and parts[1] == "team":
                return host, parts[2].upper()
            # /<workspace>/issue/<TEAM-123>/...
            if len(parts) >= 3 and parts[1] == "issue":
                ident = parts[2]
                team_key = ident.split("-")[0]
                return host, team_key.upper()
            raise ValueError(f"could not find team key in Linear URL: {raw}")

        # Bare team key like "ENG"
        if s.isalnum():
            return "linear.app", s.upper()

        raise ValueError(f"unrecognized Linear reference: {raw}")

    # ── API ─────────────────────────────────────────────────────

    def fetch_bugs(
        self,
        token: str,
        project_id: str,
        host: str = "linear.app",
        date_str: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list:
        # Resolve team UUID from team key (Linear's id can be UUID or key in newer API).
        # We pass the key; Linear accepts both.
        date_after = (
            f"{date_from}T00:00:00Z" if date_from
            else (f"{date_str}T00:00:00Z" if date_str else None)
        )
        date_before = f"{date_to}T23:59:59Z" if date_to else None

        results = []
        cursor = None
        page = 0
        while page < MAX_PAGES:
            variables = {
                "teamKey": project_id,
                "cursor": cursor,
                "first": PAGE_SIZE,
                "createdAfter": date_after,
                "createdBefore": date_before,
            }
            body = json.dumps({"query": ISSUES_QUERY, "variables": variables}).encode()
            req = urllib.request.Request(
                API_URL,
                data=body,
                headers={
                    "Authorization": token,
                    "Content-Type": "application/json",
                    "User-Agent": "fixfleet",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise ProviderAuthError(
                        code="token_invalid", status=401,
                        message="Linear API key is invalid or expired.",
                    )
                if e.code == 403:
                    raise ProviderAuthError(
                        code="token_forbidden", status=403,
                        message="Linear API key lacks required permissions.",
                    )
                raise ProviderError(
                    code=f"http_{e.code}", status=e.code,
                    message=f"Linear API returned {e.code} {e.reason}",
                )
            except urllib.error.URLError as e:
                raise ProviderNetworkError(
                    code="network_error",
                    message=f"Couldn't reach {API_URL} — {e.reason}",
                )

            # GraphQL errors come back with 200 status but errors[] field
            if data.get("errors"):
                first_err = data["errors"][0]
                msg = first_err.get("message", "Unknown Linear GraphQL error")
                if "authenticat" in msg.lower():
                    raise ProviderAuthError(
                        code="token_invalid", status=401, message=msg,
                    )
                if "not found" in msg.lower() or "no team" in msg.lower():
                    raise ProviderNotFoundError(
                        code="project_not_found", status=404,
                        message=f"Linear team '{project_id}' not found: {msg}",
                    )
                raise ProviderError(code="graphql_error", status=200, message=msg)

            team = (data.get("data") or {}).get("team")
            if not team:
                raise ProviderNotFoundError(
                    code="project_not_found", status=404,
                    message=f"Linear team '{project_id}' not found.",
                )

            issues_data = team.get("issues", {})
            for raw_issue in issues_data.get("nodes", []):
                results.append(self._normalize(raw_issue, host, project_id))

            page_info = issues_data.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            page += 1

        return results

    def _normalize(self, issue: dict, host: str, project_id: str) -> dict:
        labels = [n.get("name", "") for n in (issue.get("labels") or {}).get("nodes", []) if n.get("name")]
        priority = issue.get("priorityLabel", "")
        if priority:
            # Linear's priority labels are "Urgent" / "High" / "Medium" / "Low" / "No priority"
            if priority in ("High", "Medium", "Low"):
                labels.append(priority)
            elif priority == "Urgent":
                labels.append("High")

        creator = issue.get("creator") or {}
        return {
            "iid": issue.get("number") or 0,
            "title": issue.get("title", ""),
            "description": issue.get("description") or "",
            "labels": labels,
            "created_at": issue.get("createdAt", ""),
            "updated_at": issue.get("updatedAt", ""),
            "web_url": issue.get("url", ""),
            "author": {"username": creator.get("displayName") or creator.get("name") or creator.get("email", "")},
        }
