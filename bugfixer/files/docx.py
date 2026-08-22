"""Pure-stdlib .docx reader — docx is a zip containing word/document.xml.

Extraction order:
  1. If the document contains tables → treat the first table with a
     recognizable header row like a spreadsheet (same mapper as Excel).
  2. Otherwise → fall back to free-text bug extraction (shared with PDF).
"""

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _cell_text(tc) -> str:
    return "\n".join(
        "".join(t.text or "" for t in p.iter(f"{W}t"))
        for p in tc.iter(f"{W}p")
    ).strip()


def read_document(path: str) -> dict:
    """Return {"tables": [rows...], "text": "full plain text"}."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))

    tables = []
    for tbl in root.iter(f"{W}tbl"):
        rows = []
        for tr in tbl.findall(f"{W}tr"):
            rows.append([_cell_text(tc) for tc in tr.findall(f"{W}tc")])
        if rows:
            tables.append(rows)

    body = root.find(f"{W}body")
    paragraphs = []
    for p in (body.iter(f"{W}p") if body is not None else []):
        text = "".join(t.text or "" for t in p.iter(f"{W}t")).strip()
        if text:
            paragraphs.append(text)

    return {"tables": tables, "text": "\n".join(paragraphs)}


def parse_docx(path: str) -> list:
    from . import FileSourceError
    from .freetext import extract_bugs_from_text
    from .mapper import map_headers, rows_to_bugs

    try:
        doc = read_document(path)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        raise FileSourceError("parse_error", f"Could not read Word file: {e}")

    label = f"file://{Path(path).name}"

    # Prefer a table whose header row maps to a title column.
    for rows in doc["tables"]:
        rows = [r for r in rows if any(c.strip() for c in r)]
        if len(rows) >= 2 and "title" in map_headers(rows[0]):
            try:
                bugs = rows_to_bugs(rows[0], rows[1:], source_label=label)
            except ValueError:
                continue
            if bugs:
                return bugs

    # Free-form document → heuristic/AI text extraction.
    bugs = extract_bugs_from_text(doc["text"], source_label=label)
    if not bugs:
        raise FileSourceError(
            "no_bugs_found",
            "No bugs recognized in the document. Use a table with a Title "
            "column, or numbered items / 'Bug:' headings in the text.",
        )
    return bugs
