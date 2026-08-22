"""Extract embedded screenshots from bug files (.xlsx / .docx / .pdf).

Images are saved under ~/.fixfleet-media/<file-hash>/ and their paths are
attached to bugs so agentic AI backends (Claude Code, Cursor, ...) can open
and actually look at them while fixing.

Association strategy:
  - xlsx: drawing anchors give the worksheet row an image is pinned to →
    image is attached to the bug from that data row. Unanchorable images
    become file-level (attached to every bug).
  - docx / pdf: file-level (attached to every bug).
"""

import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MEDIA_ROOT = Path.home() / ".fixfleet-media"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
MAX_IMAGES = 20  # sanity cap per file


def _dest_dir(path: str) -> Path:
    h = hashlib.sha1(str(Path(path).resolve()).encode()).hexdigest()[:12]
    d = MEDIA_ROOT / h
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(dest: Path, name: str, data: bytes) -> str:
    out = dest / Path(name).name
    try:
        out.write_bytes(data)
        return str(out)
    except OSError:
        return ""


def _xlsx_row_anchors(z: zipfile.ZipFile) -> dict:
    """Map media file name -> anchored worksheet row (1-based), best-effort."""
    anchors: dict = {}
    try:
        drawing_names = [n for n in z.namelist()
                         if re.match(r"xl/drawings/drawing\d+\.xml$", n)]
        for dn in drawing_names:
            # rel id -> media target
            rels_name = f"xl/drawings/_rels/{Path(dn).name}.rels"
            rels: dict = {}
            try:
                rroot = ET.fromstring(z.read(rels_name))
                for rel in rroot:
                    rels[rel.get("Id", "")] = Path(rel.get("Target", "")).name
            except (KeyError, ET.ParseError):
                continue
            droot = ET.fromstring(z.read(dn))
            ns = {
                "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            }
            for anchor in list(droot):
                row_el = anchor.find("xdr:from/xdr:row", ns)
                blip = anchor.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
                if row_el is None or blip is None:
                    continue
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", "")
                media = rels.get(rid)
                if media:
                    anchors[media] = int(row_el.text or 0) + 1  # 0-based → 1-based
    except Exception:
        return {}
    return anchors


def extract_from_zip_office(path: str, media_prefix: str) -> tuple:
    """Extract images from an office zip. Returns (saved_paths_by_name, row_anchors)."""
    saved: dict = {}
    anchors: dict = {}
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if n.startswith(media_prefix)
                     and n.lower().endswith(IMAGE_EXTS)][:MAX_IMAGES]
            if not names:
                return {}, {}
            dest = _dest_dir(path)
            for n in names:
                p = _save(dest, n, z.read(n))
                if p:
                    saved[Path(n).name] = p
            if media_prefix.startswith("xl/"):
                anchors = _xlsx_row_anchors(z)
    except (zipfile.BadZipFile, OSError, KeyError):
        return {}, {}
    return saved, anchors


def extract_pdf_images(path: str) -> list:
    """File-level image extraction via pypdf (optional dependency)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    out = []
    try:
        dest = _dest_dir(path)
        reader = PdfReader(path)
        count = 0
        for pi, page in enumerate(reader.pages, 1):
            for img in getattr(page, "images", []):
                if count >= MAX_IMAGES:
                    return out
                name = f"page{pi}-{img.name}" if img.name else f"page{pi}-img{count}.png"
                p = _save(dest, name, img.data)
                if p:
                    out.append(p)
                    count += 1
    except Exception:
        pass
    return out


def attach_screenshots(bugs: list, saved: dict, anchors: dict,
                       header_rows: int = 1):
    """Attach screenshot paths to bugs.

    Row-anchored images go to the bug whose sheet row matches; the rest are
    file-level and attached to every bug. Appends a '## Screenshots' section
    to descriptions so the AI backend knows to open them.
    """
    if not saved:
        return
    file_level = []
    by_row: dict = {}
    for name, p in saved.items():
        row = anchors.get(name)
        if row and row > header_rows:
            by_row.setdefault(row - header_rows, []).append(p)  # data-row index (1-based)
        else:
            file_level.append(p)

    for idx, bug in enumerate(bugs, 1):
        paths = by_row.get(idx, []) + file_level
        if not paths:
            continue
        bug["screenshots"] = paths
        listing = "\n".join(f"- {p}" for p in paths)
        bug["description"] = (bug.get("description") or "") + (
            "\n\n## Screenshots\n"
            "Open and inspect these image files — they show the reported problem:\n"
            + listing
        )
