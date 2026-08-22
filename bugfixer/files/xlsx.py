"""Pure-stdlib .xlsx reader — xlsx is a zip of XML parts.

Reads the first non-empty worksheet: shared strings + inline strings +
numeric cells. No formatting, no formula evaluation (cached values only).
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _shared_strings(z: zipfile.ZipFile) -> list:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    strings = []
    for si in root.findall("m:si", NS):
        # Concatenate all text runs inside the string item.
        strings.append("".join(t.text or "" for t in si.iter(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return strings


def _col_index(cell_ref: str) -> int:
    """'B7' -> 1  (0-based column index)."""
    letters = re.match(r"[A-Z]+", cell_ref or "A")
    idx = 0
    for ch in (letters.group(0) if letters else "A"):
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _sheet_paths(z: zipfile.ZipFile) -> list:
    """Worksheet part names in workbook order."""
    names = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    return sorted(names, key=lambda n: int(re.search(r"(\d+)", n).group(1)))


def read_rows(path: str) -> list:
    """Return rows (list of list of str) from the first non-empty worksheet."""
    with zipfile.ZipFile(path) as z:
        shared = _shared_strings(z)
        for sheet_name in _sheet_paths(z):
            root = ET.fromstring(z.read(sheet_name))
            rows: list = []
            for row_el in root.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                cells: dict = {}
                for c in row_el.findall("m:c", NS):
                    ref = c.get("r", "")
                    ctype = c.get("t", "n")
                    v_el = c.find("m:v", NS)
                    if ctype == "s" and v_el is not None:
                        try:
                            value = shared[int(v_el.text)]
                        except (ValueError, IndexError):
                            value = ""
                    elif ctype == "inlineStr":
                        is_el = c.find("m:is", NS)
                        value = "".join(t.text or "" for t in (is_el.iter(
                            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                            if is_el is not None else []))
                    else:
                        value = v_el.text if v_el is not None and v_el.text else ""
                    # Trim float artifacts on integer ids: "3.0" -> "3"
                    if re.fullmatch(r"\d+\.0", value):
                        value = value[:-2]
                    cells[_col_index(ref)] = value
                if cells:
                    width = max(cells) + 1
                    rows.append([cells.get(i, "") for i in range(width)])
            if any(any(str(c).strip() for c in r) for r in rows):
                return rows
    return []


def parse_xlsx(path: str) -> list:
    from . import FileSourceError
    from .mapper import rows_to_bugs

    try:
        rows = read_rows(path)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        raise FileSourceError("parse_error", f"Could not read Excel file: {e}")

    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if len(rows) < 2:
        raise FileSourceError(
            "no_bugs_found",
            "Sheet needs a header row plus at least one bug row.",
        )
    try:
        bugs = rows_to_bugs(rows[0], rows[1:], source_label=f"file://{Path(path).name}")
    except ValueError as e:
        raise FileSourceError("mapping_failed", str(e))
    if not bugs:
        raise FileSourceError(
            "no_bugs_found",
            "No open bugs found in the sheet (rows with closed/fixed status are skipped).",
        )
    return bugs
