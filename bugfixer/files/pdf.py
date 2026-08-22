"""PDF bug source — requires the optional `pypdf` dependency.

Install with: pip install fixfleet[files]
"""

from pathlib import Path


def parse_pdf(path: str) -> list:
    from . import FileSourceError
    from .freetext import extract_bugs_from_text

    try:
        from pypdf import PdfReader
    except ImportError:
        raise FileSourceError(
            "missing_dependency",
            "PDF support needs the optional dependency. "
            "Install with: pip install fixfleet[files]",
        )

    try:
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        raise FileSourceError("parse_error", f"Could not read PDF: {e}")

    bugs = extract_bugs_from_text(text, source_label=f"file://{Path(path).name}")
    if not bugs:
        raise FileSourceError(
            "no_bugs_found",
            "No bugs recognized in the PDF. Expected numbered items or "
            "'Bug:' style headings; export from your tracker as a table "
            "PDF, or use Excel for best results.",
        )

    from .media import attach_screenshots, extract_pdf_images
    images = extract_pdf_images(path)
    if images:
        attach_screenshots(bugs, {Path(p).name: p for p in images}, {})
    return bugs
