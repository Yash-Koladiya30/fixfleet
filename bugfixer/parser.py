"""Issue body parser — extract structured sections from a GitLab issue description.

GitLab bug templates commonly contain markdown headings like:
    ## Description
    ## Steps to Reproduce
    ## Expected Behavior
    ## Actual Behavior
    ## Environment

This parser extracts those sections so the prompt builder can include them
explicitly instead of dumping the whole blob.
"""

import re
from dataclasses import dataclass, field

# Heading patterns mapped to canonical section names. Order matters — first
# match wins. Keys are lowercased compare-targets; values are normalized names.
SECTION_ALIASES = {
    "description": "description",
    "summary": "description",
    "overview": "description",
    "what happened": "description",
    "issue": "description",

    "steps to reproduce": "steps",
    "steps": "steps",
    "reproduction steps": "steps",
    "how to reproduce": "steps",
    "repro": "steps",
    "to reproduce": "steps",

    "expected behavior": "expected",
    "expected behaviour": "expected",
    "expected": "expected",
    "expected result": "expected",

    "actual behavior": "actual",
    "actual behaviour": "actual",
    "actual": "actual",
    "actual result": "actual",
    "current behavior": "actual",

    "environment": "environment",
    "env": "environment",
    "system": "environment",
    "version": "environment",
    "versions": "environment",

    "logs": "logs",
    "build log": "logs",
    "build logs": "logs",
    "compiler error": "logs",
    "compiler errors": "logs",
    "compile error": "logs",
    "compile errors": "logs",
    "stack trace": "logs",
    "stacktrace": "logs",
    "traceback": "logs",
    "error": "logs",

    "screenshots": "screenshots",
    "screenshot": "screenshots",

    "notes": "notes",
    "additional info": "notes",
    "additional information": "notes",
    "additional context": "notes",
    "context": "notes",
}

# Match markdown ATX headings (## Title) or setext-ish bold lines (**Title**:)
HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s+(.+?)\s*#*\s*$|\*\*(.+?)\*\*\s*:?\s*$)",
    re.MULTILINE,
)


@dataclass
class ParsedIssue:
    iid: int
    title: str
    url: str
    labels: list = field(default_factory=list)
    raw_description: str = ""
    description: str = ""
    steps: str = ""
    expected: str = ""
    actual: str = ""
    environment: str = ""
    logs: str = ""
    screenshots: str = ""
    notes: str = ""

    def has_section(self, name: str) -> bool:
        return bool(getattr(self, name, "").strip())


def _normalize_heading(text: str) -> str:
    """Lowercase, strip punctuation/emoji-ish chars, collapse whitespace."""
    text = text.strip().lower()
    text = re.sub(r"[:*_`~()\[\]]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _resolve_section(heading_text: str) -> str:
    """Map a raw heading to a canonical section name, or '' if unknown."""
    norm = _normalize_heading(heading_text)
    if norm in SECTION_ALIASES:
        return SECTION_ALIASES[norm]
    # Loose match — heading contains an alias as a whole-word substring
    for alias, canonical in SECTION_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", norm):
            return canonical
    return ""


def parse_description(body: str) -> dict:
    """Split a markdown issue body into canonical sections.

    Text before the first recognized heading becomes 'description'.
    Returns a dict keyed by canonical section name.
    """
    sections: dict = {}
    if not body:
        return sections

    body = body.replace("\r\n", "\n").replace("\r", "\n").strip()

    matches = list(HEADING_RE.finditer(body))

    if not matches:
        sections["description"] = body
        return sections

    # Preamble — text before the first heading
    first_start = matches[0].start()
    preamble = body[:first_start].strip()
    if preamble:
        sections["description"] = preamble

    for i, m in enumerate(matches):
        heading_text = (m.group(1) or m.group(2) or "").strip()
        canonical = _resolve_section(heading_text)
        if not canonical:
            continue
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[content_start:content_end].strip()
        if not content:
            continue
        # Append if section already populated (multiple headings of same kind)
        if canonical in sections and sections[canonical]:
            sections[canonical] = f"{sections[canonical]}\n\n{content}"
        else:
            sections[canonical] = content

    return sections


def parse_issue(issue: dict) -> ParsedIssue:
    """Convert a raw GitLab issue dict into a ParsedIssue."""
    body = issue.get("description") or ""
    sections = parse_description(body)

    return ParsedIssue(
        iid=issue.get("iid", 0),
        title=issue.get("title", "").strip(),
        url=issue.get("web_url", ""),
        labels=list(issue.get("labels", [])),
        raw_description=body,
        description=sections.get("description", ""),
        steps=sections.get("steps", ""),
        expected=sections.get("expected", ""),
        actual=sections.get("actual", ""),
        environment=sections.get("environment", ""),
        logs=sections.get("logs", ""),
        screenshots=sections.get("screenshots", ""),
        notes=sections.get("notes", ""),
    )
