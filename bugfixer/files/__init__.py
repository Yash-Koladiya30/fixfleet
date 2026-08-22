"""File-based bug sources — Excel (.xlsx), Word (.docx), PDF (.pdf).

xlsx/docx are parsed with pure stdlib (they're zip+XML). PDF needs the
optional `pypdf` dependency: pip install fixfleet[files].

Each parser returns bugs in the same unified shape the tracker providers
use: iid, title, description, labels, created_at, updated_at, web_url, author.
"""

from pathlib import Path

from .xlsx import parse_xlsx
from .docx import parse_docx
from .pdf import parse_pdf

SUPPORTED_EXTENSIONS = (".xlsx", ".docx", ".pdf")


class FileSourceError(Exception):
    """Raised when a bug file can't be read or contains no recognizable bugs."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_bug_file(path: str) -> list:
    """Parse a bug list from a local file. Returns unified bug dicts.

    Raises FileSourceError with a stable code for JSON callers.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileSourceError("file_not_found", f"File not found: {path}")

    ext = p.suffix.lower()
    if ext == ".xlsx":
        return parse_xlsx(str(p))
    if ext == ".docx":
        return parse_docx(str(p))
    if ext == ".pdf":
        return parse_pdf(str(p))
    if ext in (".xls",):
        raise FileSourceError(
            "unsupported_format",
            "Legacy .xls is not supported — re-save the sheet as .xlsx and retry.",
        )
    raise FileSourceError(
        "unsupported_format",
        f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
    )
