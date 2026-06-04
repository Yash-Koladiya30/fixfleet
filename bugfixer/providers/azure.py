"""Azure DevOps Boards provider — WIQL (Work Item Query Language).

Two-step query:
  1. POST /{org}/{project}/_apis/wit/wiql?api-version=7.0  (returns IDs)
  2. GET  /{org}/_apis/wit/workitems?ids=N1,N2&$expand=relations (returns details)

Auth: Basic with empty username + PAT in password slot:  Base64(":PAT")
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


API_VERSION = "7.0"
API_HOST = "dev.azure.com"
MAX_IDS_PER_REQUEST = 200


class AzureDevOpsProvider(Provider):
    key = "azure"
    display_name = "Azure DevOps"
    tagline = "dev.azure.com Boards"
    host_patterns = ("dev.azure.com", "visualstudio.com")
    implemented = True
    token_url = "https://dev.azure.com/_usersSettings/tokens"
    token_scope_hint = "PAT with `Work Items (read)` scope. Paste PAT alone — no email prefix needed."

    # ── URL parsing ─────────────────────────────────────────────

    def parse_url(self, raw: str) -> tuple:
        """Return (host, project_id).

        project_id encodes both organization and project as "org/project".

        Accept:
          - https://dev.azure.com/myorg/myproject
          - https://dev.azure.com/myorg/myproject/_workitems/...
          - org/project (bare)
        """
        s = (raw or "").strip()
        if not s:
            raise ValueError("empty input")

        if s.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(s)
            host = parsed.netloc
            path = parsed.path.lstrip("/")
            parts = path.split("/")
            if len(parts) < 2:
                raise ValueError(f"need org/project, got: {raw}")
            org, project = parts[0], parts[1]
            # Decode URL-encoded project names
            project = urllib.parse.unquote(project)
            return host, f"{org}/{project}"

        if "/" in s and not s.startswith(("/", ".", "~")):
            return API_HOST, s.rstrip("/")

        raise ValueError(f"unrecognized Azure DevOps reference: {raw}")

    # ── API ─────────────────────────────────────────────────────

    def fetch_bugs(
        self,
        token: str,
        project_id: str,
        host: str = API_HOST,
        date_str: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list:
        if "/" not in project_id:
            raise ValueError("Azure project_id must be 'org/project'")
        org, project = project_id.split("/", 1)

        # Basic auth: empty username + PAT in password slot
        auth = base64.b64encode(f":{token}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "fixfleet",
        }

        # Step 1: WIQL query → list of IDs
        wiql_parts = [
            "SELECT [System.Id], [System.Title], [System.State]",
            "FROM WorkItems",
            f"WHERE [System.WorkItemType] = 'Bug'",
            "  AND [System.State] NOT IN ('Closed', 'Done', 'Resolved', 'Removed')",
        ]
        if date_from:
            wiql_parts.append(f"  AND [System.CreatedDate] >= '{date_from}T00:00:00Z'")
        elif date_str:
            wiql_parts.append(f"  AND [System.CreatedDate] >= '{date_str}T00:00:00Z'")
        if date_to:
            wiql_parts.append(f"  AND [System.CreatedDate] <= '{date_to}T23:59:59Z'")
        wiql_parts.append("ORDER BY [System.CreatedDate] DESC")
        wiql = " ".join(wiql_parts)

        wiql_url = f"https://{host}/{org}/{project}/_apis/wit/wiql?api-version={API_VERSION}"
        wiql_req = urllib.request.Request(
            wiql_url,
            data=json.dumps({"query": wiql}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(wiql_req, timeout=30) as resp:
                wiql_data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ProviderAuthError(
                    code="token_invalid", status=401,
                    message="Azure DevOps PAT is invalid or expired.",
                )
            if e.code == 403:
                raise ProviderAuthError(
                    code="token_forbidden", status=403,
                    message="Azure DevOps PAT lacks 'Work Items (Read)' scope.",
                )
            if e.code == 404:
                raise ProviderNotFoundError(
                    code="project_not_found", status=404,
                    message=f"Azure DevOps project not found at https://{host}/{org}/{project}.",
                )
            raise ProviderError(
                code=f"http_{e.code}", status=e.code,
                message=f"Azure DevOps WIQL returned {e.code} {e.reason}",
            )
        except urllib.error.URLError as e:
            raise ProviderNetworkError(
                code="network_error",
                message=f"Couldn't reach https://{host} — {e.reason}",
            )

        ids = [wi.get("id") for wi in wiql_data.get("workItems", []) if wi.get("id")]
        if not ids:
            return []

        # Step 2: batch-fetch work item details
        results = []
        for i in range(0, len(ids), MAX_IDS_PER_REQUEST):
            chunk = ids[i:i + MAX_IDS_PER_REQUEST]
            ids_str = ",".join(str(x) for x in chunk)
            details_url = (
                f"https://{host}/{org}/_apis/wit/workitems"
                f"?ids={ids_str}&$expand=none&api-version={API_VERSION}"
            )
            req = urllib.request.Request(details_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    details = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                # Skip chunk on error — partial results better than none
                continue
            for wi in details.get("value", []):
                results.append(self._normalize(wi, host, org, project))

        return results

    def _normalize(self, wi: dict, host: str, org: str, project: str) -> dict:
        fields = wi.get("fields", {}) or {}
        wi_id = wi.get("id", 0)

        title = fields.get("System.Title", "")
        # Description may be in System.Description (rich HTML) or Repro Steps
        description = (
            fields.get("System.Description", "")
            or fields.get("Microsoft.VSTS.TCM.ReproSteps", "")
            or ""
        )
        # Strip HTML tags for plain-text rendering downstream
        description = _strip_html(description)

        priority_num = fields.get("Microsoft.VSTS.Common.Priority")
        priority_label = ""
        if priority_num == 1: priority_label = "High"
        elif priority_num == 2: priority_label = "Medium"
        elif priority_num in (3, 4): priority_label = "Low"

        tags_str = fields.get("System.Tags", "")
        tags = [t.strip() for t in tags_str.split(";") if t.strip()] if tags_str else []
        if priority_label:
            tags.append(priority_label)

        created_by = fields.get("System.CreatedBy") or {}
        author_name = (
            created_by.get("displayName")
            or created_by.get("uniqueName")
            or (created_by if isinstance(created_by, str) else "")
        )

        return {
            "iid": wi_id,
            "title": title,
            "description": description,
            "labels": tags,
            "created_at": fields.get("System.CreatedDate", ""),
            "updated_at": fields.get("System.ChangedDate", ""),
            "web_url": f"https://{host}/{org}/{project}/_workitems/edit/{wi_id}",
            "author": {"username": author_name},
        }


def _strip_html(s: str) -> str:
    """Quick + dirty HTML-to-plaintext (no deps)."""
    if not s:
        return ""
    import re
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return s.strip()
