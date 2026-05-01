"""GitLab API client — fetch open bug issues with pagination.

Also exposes `parse_project_input` which accepts ANY of:
  - Full HTTPS URL: https://gitlab.com/group/subgroup/project
  - .git URL:        https://gitlab.com/group/project.git
  - Issues URL:      https://gitlab.com/group/project/-/issues/42
  - SSH URL:         git@gitlab.com:group/project.git
  - SCP-style:       ssh://git@gitlab.com/group/project.git
  - Self-hosted:     https://gitlab.example.com/group/project
  - Path only:       group/subgroup/project
  - Numeric ID:      12345
and returns (host, project_path).
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from . import ui

DEFAULT_HOST = "gitlab.com"
PER_PAGE = 100
MAX_PAGES = 20  # hard cap to avoid runaway loops


# ── URL parsing ────────────────────────────────────────────────

_SSH_RE = re.compile(r"^(?:ssh://)?(?:git@)?([^:/]+)[:/](.+?)(?:\.git)?/?$")


def parse_project_input(raw: str) -> tuple:
    """Return (host, project_path). Defaults to gitlab.com when no host given.

    Raises ValueError if the input clearly isn't a project reference.
    """
    if not raw or not raw.strip():
        raise ValueError("empty input")

    s = raw.strip()

    # 1. Numeric ID — pass through, host defaults to gitlab.com
    if s.isdigit():
        return DEFAULT_HOST, s

    # 2. http(s) URL
    if s.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(s)
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        # Strip trailing .git
        if path.endswith(".git"):
            path = path[:-4]
        # Strip GitLab UI suffixes: /-/issues, /-/blob/main, /-/tree/...
        if "/-/" in path:
            path = path.split("/-/")[0]
        # Strip trailing slash
        path = path.rstrip("/")
        if not host or not path:
            raise ValueError(f"could not parse URL: {raw}")
        return host, path

    # 3. SSH / SCP-style: git@host:group/project.git or ssh://git@host/group/project
    m = _SSH_RE.match(s)
    if m and (s.startswith(("ssh://", "git@")) or "@" in s):
        host = m.group(1)
        path = m.group(2).rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return host, path

    # 4. Plain path: group/project or group/subgroup/project
    if "/" in s and not s.startswith(("/", ".", "~")):
        # Strip leading "gitlab.com/" if user typed it without scheme
        if s.startswith("gitlab.com/"):
            return DEFAULT_HOST, s[len("gitlab.com/"):].rstrip("/")
        return DEFAULT_HOST, s.rstrip("/")

    raise ValueError(f"unrecognized project reference: {raw}")


# ── Date helpers ───────────────────────────────────────────────

def _next_day(date_str: str) -> str:
    """Return YYYY-MM-DD for the day after the given date."""
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# ── API ────────────────────────────────────────────────────────

def fetch_bug_issues(token: str, project_id: str, date_str: str = None,
                     host: str = DEFAULT_HOST) -> list:
    """Fetch all open issues with 'Bug' label. Paginated, optionally filtered by date.

    Date filter is inclusive: bugs created on `date_str` (UTC).
    """
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

    if date_str:
        end_date = _next_day(date_str)
        params["created_after"] = f"{date_str}T00:00:00Z"
        params["created_before"] = f"{end_date}T00:00:00Z"

    all_issues: list = []
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
            ui.print_error(f"GitLab API error: {e.code} {e.reason}")
            if e.code == 401:
                ui.print_info("Token invalid or expired. Create a new one.")
            elif e.code == 403:
                ui.print_info("Token lacks required scope. Need 'api' or 'read_api'.")
            elif e.code == 404:
                ui.print_info(f"Project not found at https://{host}/{project_id}")
                ui.print_info("Check that the URL is correct and your token has access.")
            sys.exit(1)
        except urllib.error.URLError as e:
            ui.print_error(f"Network error: {e.reason}")
            sys.exit(1)

        if not batch:
            break

        all_issues.extend(batch)

        if not next_page:
            break

        page = int(next_page)

    return all_issues


# Backwards-compat alias (some tests / older code)
GITLAB_API_BASE = f"https://{DEFAULT_HOST}/api/v4"
