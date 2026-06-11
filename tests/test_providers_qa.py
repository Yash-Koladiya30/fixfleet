"""QA suite for all 6 issue-tracker providers — no real accounts needed.

Strategy: mock `urllib.request.urlopen` with canned responses that replicate
each provider's REAL API shape (taken from official API docs). This exercises
the full code path: request building → response parsing → normalization →
error mapping. Only thing not covered is live network/auth, which is
provider-side anyway.
"""

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bugfixer.providers import (
    ProviderAuthError,
    ProviderNetworkError,
    ProviderNotFoundError,
    get_provider,
)


# ── Mock plumbing ──────────────────────────────────────────────

class FakeResponse:
    """Mimics urllib's addinfourl response object."""

    def __init__(self, body: dict | list, headers: dict = None):
        self._body = json.dumps(body).encode()
        self.headers = _HeadersDict(headers or {})

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _HeadersDict(dict):
    def get(self, key, default=""):
        return super().get(key, default)


def http_error(code: int, reason: str = "err"):
    return urllib.error.HTTPError(
        url="https://x", code=code, msg=reason, hdrs={}, fp=io.BytesIO(b"{}"),
    )


# ══════════════════════════════════════════════════════════════
# GitHub
# ══════════════════════════════════════════════════════════════

GITHUB_ISSUE = {
    "number": 1347,
    "id": 1,
    "title": "App crashes on login",
    "body": "## Steps to Reproduce\n1. Open app\n2. Login\n\n## Expected\nWorks",
    "state": "open",
    "labels": [{"name": "bug"}, {"name": "High"}, {"name": "ios"}],
    "user": {"login": "octocat"},
    "created_at": "2026-06-01T10:00:00Z",
    "updated_at": "2026-06-02T11:00:00Z",
    "html_url": "https://github.com/owner/repo/issues/1347",
}

GITHUB_PR_DISGUISED_AS_ISSUE = {
    **GITHUB_ISSUE,
    "number": 1348,
    "title": "Some pull request",
    "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/1348"},
}


class TestGitHubQA(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("github")

    def test_fetch_normalizes_issue(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse([GITHUB_ISSUE])):
            out = self.p.fetch_bugs("ghp_test", "owner/repo")
        self.assertEqual(len(out), 1)
        bug = out[0]
        self.assertEqual(bug["iid"], 1347)
        self.assertEqual(bug["title"], "App crashes on login")
        self.assertIn("Steps to Reproduce", bug["description"])
        self.assertEqual(bug["labels"], ["bug", "High", "ios"])
        self.assertEqual(bug["author"]["username"], "octocat")
        self.assertEqual(bug["web_url"], "https://github.com/owner/repo/issues/1347")

    def test_filters_out_pull_requests(self):
        with patch("urllib.request.urlopen",
                   return_value=FakeResponse([GITHUB_ISSUE, GITHUB_PR_DISGUISED_AS_ISSUE])):
            out = self.p.fetch_bugs("ghp_test", "owner/repo")
        self.assertEqual(len(out), 1)  # PR excluded
        self.assertEqual(out[0]["iid"], 1347)

    def test_date_to_client_filter(self):
        late_issue = {**GITHUB_ISSUE, "number": 99, "created_at": "2026-06-30T10:00:00Z"}
        with patch("urllib.request.urlopen",
                   return_value=FakeResponse([GITHUB_ISSUE, late_issue])):
            out = self.p.fetch_bugs("ghp_test", "owner/repo", date_to="2026-06-15")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["iid"], 1347)

    def test_401_raises_auth_error(self):
        with patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(ProviderAuthError):
                self.p.fetch_bugs("bad", "owner/repo")

    def test_404_raises_not_found(self):
        with patch("urllib.request.urlopen", side_effect=http_error(404)):
            with self.assertRaises(ProviderNotFoundError):
                self.p.fetch_bugs("ghp_test", "owner/nonexistent")

    def test_network_error(self):
        with patch("urllib.request.urlopen",
                   side_effect=urllib.error.URLError("dns fail")):
            with self.assertRaises(ProviderNetworkError):
                self.p.fetch_bugs("ghp_test", "owner/repo")

    def test_request_has_bearer_auth(self):
        captured = {}
        def capture(req, timeout=0):
            captured["auth"] = req.get_header("Authorization")
            captured["url"] = req.full_url
            return FakeResponse([])
        with patch("urllib.request.urlopen", side_effect=capture):
            self.p.fetch_bugs("ghp_secret", "owner/repo")
        self.assertEqual(captured["auth"], "Bearer ghp_secret")
        self.assertIn("api.github.com/repos/owner/repo/issues", captured["url"])
        self.assertIn("labels=bug", captured["url"])
        self.assertIn("state=open", captured["url"])


# ══════════════════════════════════════════════════════════════
# Bitbucket
# ══════════════════════════════════════════════════════════════

BITBUCKET_PAGE = {
    "values": [
        {
            "id": 42,
            "title": "Payment fails on checkout",
            "kind": "bug",
            "priority": "critical",
            "state": "open",
            "content": {"raw": "**Steps:**\n1. Add to cart\n2. Checkout"},
            "reporter": {"display_name": "Jane Doe", "nickname": "jane"},
            "created_on": "2026-06-01T08:00:00Z",
            "updated_on": "2026-06-01T09:00:00Z",
        }
    ],
    "next": None,
}


class TestBitbucketQA(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("bitbucket")

    def test_fetch_normalizes(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(BITBUCKET_PAGE)):
            out = self.p.fetch_bugs("user:app-pass", "team/repo")
        self.assertEqual(len(out), 1)
        bug = out[0]
        self.assertEqual(bug["iid"], 42)
        self.assertEqual(bug["title"], "Payment fails on checkout")
        self.assertIn("Steps", bug["description"])
        # critical → High mapping
        self.assertIn("High", bug["labels"])
        self.assertIn("Bug", bug["labels"])
        self.assertEqual(bug["author"]["username"], "Jane Doe")
        self.assertEqual(bug["web_url"], "https://bitbucket.org/team/repo/issues/42")

    def test_token_without_colon_rejected(self):
        with self.assertRaises(ProviderAuthError) as ctx:
            self.p.fetch_bugs("no-colon-token", "team/repo")
        self.assertIn("username:app-password", ctx.exception.message)

    def test_pagination_follows_next(self):
        page1 = {**BITBUCKET_PAGE, "next": "https://api.bitbucket.org/2.0/page2"}
        page2 = {"values": [{**BITBUCKET_PAGE["values"][0], "id": 43}], "next": None}
        responses = [FakeResponse(page1), FakeResponse(page2)]
        with patch("urllib.request.urlopen", side_effect=responses):
            out = self.p.fetch_bugs("u:p", "team/repo")
        self.assertEqual([b["iid"] for b in out], [42, 43])

    def test_401(self):
        with patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(ProviderAuthError):
                self.p.fetch_bugs("u:bad", "team/repo")


# ══════════════════════════════════════════════════════════════
# Linear
# ══════════════════════════════════════════════════════════════

LINEAR_RESPONSE = {
    "data": {
        "team": {
            "id": "uuid-1",
            "key": "ENG",
            "name": "Engineering",
            "issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {
                        "id": "uuid-issue-1",
                        "identifier": "ENG-101",
                        "number": 101,
                        "title": "Search returns stale results",
                        "description": "## Steps\n1. Search 'foo'\n2. Update doc\n3. Search again",
                        "createdAt": "2026-06-01T12:00:00.000Z",
                        "updatedAt": "2026-06-02T12:00:00.000Z",
                        "url": "https://linear.app/acme/issue/ENG-101/search-stale",
                        "creator": {"displayName": "Alex", "name": "alex", "email": "a@x.com"},
                        "labels": {"nodes": [{"name": "Bug"}, {"name": "search"}]},
                        "priorityLabel": "Urgent",
                        "state": {"name": "Todo", "type": "unstarted"},
                    }
                ],
            },
        }
    }
}

LINEAR_AUTH_ERROR = {"errors": [{"message": "Authentication required - api key is invalid"}]}
LINEAR_TEAM_NOT_FOUND = {"data": {"team": None}}


class TestLinearQA(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("linear")

    def test_fetch_normalizes(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(LINEAR_RESPONSE)):
            out = self.p.fetch_bugs("lin_api_test", "ENG")
        self.assertEqual(len(out), 1)
        bug = out[0]
        self.assertEqual(bug["iid"], 101)
        self.assertEqual(bug["title"], "Search returns stale results")
        self.assertIn("Steps", bug["description"])
        # Urgent → High mapping; original labels kept
        self.assertIn("High", bug["labels"])
        self.assertIn("Bug", bug["labels"])
        self.assertEqual(bug["author"]["username"], "Alex")
        self.assertEqual(bug["web_url"], "https://linear.app/acme/issue/ENG-101/search-stale")

    def test_graphql_auth_error_with_200_status(self):
        # Linear returns 200 + errors[] for bad keys — must still raise auth error
        with patch("urllib.request.urlopen", return_value=FakeResponse(LINEAR_AUTH_ERROR)):
            with self.assertRaises(ProviderAuthError):
                self.p.fetch_bugs("bad_key", "ENG")

    def test_team_not_found(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(LINEAR_TEAM_NOT_FOUND)):
            with self.assertRaises(ProviderNotFoundError):
                self.p.fetch_bugs("lin_api_test", "NOPE")

    def test_request_sends_raw_key_no_bearer(self):
        captured = {}
        def capture(req, timeout=0):
            captured["auth"] = req.get_header("Authorization")
            captured["body"] = json.loads(req.data.decode())
            return FakeResponse(LINEAR_RESPONSE)
        with patch("urllib.request.urlopen", side_effect=capture):
            self.p.fetch_bugs("lin_api_secret", "ENG")
        # Linear wants raw key, NOT 'Bearer ...'
        self.assertEqual(captured["auth"], "lin_api_secret")
        self.assertEqual(captured["body"]["variables"]["teamKey"], "ENG")


# ══════════════════════════════════════════════════════════════
# Jira
# ══════════════════════════════════════════════════════════════

JIRA_ADF_DESCRIPTION = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 2},
         "content": [{"type": "text", "text": "Steps to Reproduce"}]},
        {"type": "paragraph",
         "content": [{"type": "text", "text": "1. Open settings 2. Click save"}]},
    ],
}

JIRA_SEARCH_RESPONSE = {
    "total": 1,
    "issues": [
        {
            "key": "MYPROJ-42",
            "fields": {
                "summary": "Settings page throws 500",
                "description": JIRA_ADF_DESCRIPTION,
                "labels": ["backend"],
                "priority": {"name": "Highest"},
                "created": "2026-06-01T07:00:00.000+0000",
                "updated": "2026-06-01T08:00:00.000+0000",
                "creator": {"displayName": "Sam Lee", "emailAddress": "sam@x.com"},
                "issuetype": {"name": "Bug"},
                "status": {"name": "Open"},
            },
        }
    ],
}


class TestJiraQA(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("jira")

    def test_fetch_normalizes_with_adf_extraction(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(JIRA_SEARCH_RESPONSE)):
            out = self.p.fetch_bugs("me@x.com:token", "MYPROJ", host="acme.atlassian.net")
        self.assertEqual(len(out), 1)
        bug = out[0]
        self.assertEqual(bug["iid"], "MYPROJ-42")  # string key, not int
        self.assertEqual(bug["title"], "Settings page throws 500")
        # ADF extracted to plain text
        self.assertIn("Steps to Reproduce", bug["description"])
        self.assertIn("Open settings", bug["description"])
        # Highest → High mapping; original labels kept
        self.assertIn("High", bug["labels"])
        self.assertIn("backend", bug["labels"])
        self.assertEqual(bug["author"]["username"], "Sam Lee")
        self.assertEqual(bug["web_url"], "https://acme.atlassian.net/browse/MYPROJ-42")

    def test_token_without_colon_rejected(self):
        with self.assertRaises(ProviderAuthError):
            self.p.fetch_bugs("token-no-email", "MYPROJ", host="acme.atlassian.net")

    def test_missing_host_rejected(self):
        with self.assertRaises(ProviderNotFoundError) as ctx:
            self.p.fetch_bugs("me@x.com:token", "MYPROJ", host="")
        self.assertIn("host", ctx.exception.message.lower())

    def test_jql_contains_bug_filter(self):
        captured = {}
        def capture(req, timeout=0):
            captured["url"] = req.full_url
            return FakeResponse({"total": 0, "issues": []})
        with patch("urllib.request.urlopen", side_effect=capture):
            self.p.fetch_bugs("me@x.com:tok", "MYPROJ", host="acme.atlassian.net",
                              date_from="2026-06-01", date_to="2026-06-04")
        from urllib.parse import unquote_plus
        jql = unquote_plus(captured["url"].split("jql=")[1].split("&")[0])
        self.assertIn('project = "MYPROJ"', jql)
        self.assertIn('issuetype = "Bug"', jql)
        self.assertIn('created >= "2026-06-01"', jql)
        self.assertIn('created <= "2026-06-04"', jql)

    def test_401(self):
        with patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(ProviderAuthError):
                self.p.fetch_bugs("me@x.com:bad", "MYPROJ", host="acme.atlassian.net")


# ══════════════════════════════════════════════════════════════
# Azure DevOps
# ══════════════════════════════════════════════════════════════

AZURE_WIQL_RESPONSE = {
    "workItems": [{"id": 7}, {"id": 9}],
}

AZURE_DETAILS_RESPONSE = {
    "value": [
        {
            "id": 7,
            "fields": {
                "System.Title": "Crash on startup",
                "System.Description": "<div>Open app <br/>It crashes</div>",
                "System.CreatedDate": "2026-06-01T06:00:00Z",
                "System.ChangedDate": "2026-06-01T07:00:00Z",
                "System.CreatedBy": {"displayName": "Pat Kim", "uniqueName": "pat@x.com"},
                "System.Tags": "mobile; regression",
                "Microsoft.VSTS.Common.Priority": 1,
            },
        },
        {
            "id": 9,
            "fields": {
                "System.Title": "Slow load",
                "Microsoft.VSTS.TCM.ReproSteps": "<p>1. Open dashboard</p><p>2. Wait</p>",
                "System.CreatedDate": "2026-06-02T06:00:00Z",
                "System.ChangedDate": "2026-06-02T07:00:00Z",
                "System.CreatedBy": {"displayName": "Lee"},
                "Microsoft.VSTS.Common.Priority": 3,
            },
        },
    ],
}


class TestAzureQA(unittest.TestCase):
    def setUp(self):
        self.p = get_provider("azure")

    def test_two_step_fetch_normalizes(self):
        responses = [FakeResponse(AZURE_WIQL_RESPONSE), FakeResponse(AZURE_DETAILS_RESPONSE)]
        with patch("urllib.request.urlopen", side_effect=responses):
            out = self.p.fetch_bugs("pat-token", "myorg/myproject")
        self.assertEqual(len(out), 2)

        bug1 = out[0]
        self.assertEqual(bug1["iid"], 7)
        self.assertEqual(bug1["title"], "Crash on startup")
        # HTML stripped
        self.assertNotIn("<div>", bug1["description"])
        self.assertIn("Open app", bug1["description"])
        # Priority 1 → High; tags split on ;
        self.assertIn("High", bug1["labels"])
        self.assertIn("mobile", bug1["labels"])
        self.assertIn("regression", bug1["labels"])
        self.assertEqual(bug1["author"]["username"], "Pat Kim")
        self.assertEqual(
            bug1["web_url"],
            "https://dev.azure.com/myorg/myproject/_workitems/edit/7",
        )

        bug2 = out[1]
        # ReproSteps fallback when no Description
        self.assertIn("Open dashboard", bug2["description"])
        self.assertIn("Low", bug2["labels"])  # priority 3 → Low

    def test_empty_wiql_returns_empty(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse({"workItems": []})):
            out = self.p.fetch_bugs("pat", "org/proj")
        self.assertEqual(out, [])

    def test_auth_uses_basic_with_empty_username(self):
        import base64
        captured = {}
        def capture(req, timeout=0):
            captured.setdefault("auth", req.get_header("Authorization"))
            return FakeResponse({"workItems": []})
        with patch("urllib.request.urlopen", side_effect=capture):
            self.p.fetch_bugs("my-pat", "org/proj")
        expected = "Basic " + base64.b64encode(b":my-pat").decode()
        self.assertEqual(captured["auth"], expected)

    def test_401(self):
        with patch("urllib.request.urlopen", side_effect=http_error(401)):
            with self.assertRaises(ProviderAuthError):
                self.p.fetch_bugs("bad", "org/proj")

    def test_bad_project_id_format(self):
        with self.assertRaises(ValueError):
            self.p.fetch_bugs("pat", "no-slash-here")


# ══════════════════════════════════════════════════════════════
# End-to-end: provider output → parser → prompt
# ══════════════════════════════════════════════════════════════

class TestEndToEndPipeline(unittest.TestCase):
    """Verify normalized issues from every provider flow through the
    downstream parser + prompt builder without errors."""

    def _pipeline(self, raw_issue: dict):
        from bugfixer.parser import parse_issue
        from bugfixer.prompt import build_prompt
        parsed = parse_issue(raw_issue)
        prompt = build_prompt(parsed)
        return parsed, prompt

    def test_github_issue_through_pipeline(self):
        p = get_provider("github")
        with patch("urllib.request.urlopen", return_value=FakeResponse([GITHUB_ISSUE])):
            bugs = p.fetch_bugs("t", "o/r")
        parsed, prompt = self._pipeline(bugs[0])
        self.assertIn("Open app", parsed.steps)          # section extracted
        self.assertIn("Steps to Reproduce", prompt)
        self.assertIn("#1347", prompt)

    def test_jira_issue_through_pipeline(self):
        p = get_provider("jira")
        with patch("urllib.request.urlopen", return_value=FakeResponse(JIRA_SEARCH_RESPONSE)):
            bugs = p.fetch_bugs("e@x.com:t", "MYPROJ", host="acme.atlassian.net")
        parsed, prompt = self._pipeline(bugs[0])
        # iid is a string key — parser must not crash
        self.assertEqual(parsed.iid, "MYPROJ-42")
        self.assertIn("MYPROJ-42", prompt)

    def test_azure_issue_through_pipeline(self):
        p = get_provider("azure")
        responses = [FakeResponse(AZURE_WIQL_RESPONSE), FakeResponse(AZURE_DETAILS_RESPONSE)]
        with patch("urllib.request.urlopen", side_effect=responses):
            bugs = p.fetch_bugs("t", "org/proj")
        parsed, prompt = self._pipeline(bugs[0])
        self.assertIn("Crash on startup", prompt)

    def test_linear_issue_through_pipeline(self):
        p = get_provider("linear")
        with patch("urllib.request.urlopen", return_value=FakeResponse(LINEAR_RESPONSE)):
            bugs = p.fetch_bugs("k", "ENG")
        parsed, prompt = self._pipeline(bugs[0])
        self.assertIn("Search returns stale results", prompt)

    def test_bitbucket_issue_through_pipeline(self):
        p = get_provider("bitbucket")
        with patch("urllib.request.urlopen", return_value=FakeResponse(BITBUCKET_PAGE)):
            bugs = p.fetch_bugs("u:p", "t/r")
        parsed, prompt = self._pipeline(bugs[0])
        self.assertIn("Payment fails", prompt)


# ══════════════════════════════════════════════════════════════
# JSON API end-to-end with mocked provider
# ══════════════════════════════════════════════════════════════

class TestJsonApiWithProviders(unittest.TestCase):
    """Run the actual CLI argument path with mocked HTTP."""

    def _run_list_bugs(self, provider_key, project_url, mock_responses):
        import subprocess
        # Instead of subprocess (can't mock across process), call internals.
        from bugfixer import json_api

        argv_backup = sys.argv
        sys.argv = [
            "fixfleet", "--list-bugs-json",
            "--provider", provider_key,
            "--token", "e@x.com:tok" if provider_key in ("jira", "bitbucket") else "tok",
            "--project-url", project_url,
        ]
        captured_out = io.StringIO()
        try:
            with patch("urllib.request.urlopen", side_effect=mock_responses), \
                 patch("sys.stdout", captured_out):
                try:
                    json_api.main()
                except SystemExit:
                    pass
        finally:
            sys.argv = argv_backup
        lines = [l for l in captured_out.getvalue().splitlines() if l.startswith("{")]
        return json.loads(lines[-1]) if lines else {}

    def test_github_e2e(self):
        result = self._run_list_bugs(
            "github", "https://github.com/owner/repo",
            [FakeResponse([GITHUB_ISSUE])],
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["issues"][0]["iid"], 1347)
        # Sections parsed
        self.assertIn("Open app", result["issues"][0]["sections"]["steps"])

    def test_jira_e2e(self):
        result = self._run_list_bugs(
            "jira", "https://acme.atlassian.net/browse/MYPROJ-42",
            [FakeResponse(JIRA_SEARCH_RESPONSE)],
        )
        self.assertTrue(result.get("ok"))
        self.assertEqual(result["issues"][0]["iid"], "MYPROJ-42")

    def test_auto_detection_picks_github(self):
        result = self._run_list_bugs(
            "", "https://github.com/owner/repo",
            [FakeResponse([GITHUB_ISSUE])],
        )
        self.assertTrue(result.get("ok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
