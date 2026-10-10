"""Text from Word (.docx) and Excel (.xlsx) files using only the standard library.

Both formats are zip files of XML. Safety limits: the archive and each part must be small,
compression ratios must be sane (no zip bombs), XML with DOCTYPE/entities is refused, and
output is capped. Macros (.docm/.xlsm) are never run; only text and cell values are read.
"""
import re
import zipfile
import xml.etree.ElementTree as ET

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_PART_BYTES = 30 * 1024 * 1024
MAX_RATIO = 100
MAX_CHARS = 10240

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class OfficeError(ValueError):
    pass


def _part(z: zipfile.ZipFile, name: str, required: bool = True):
    try:
        info = z.getinfo(name)
    except KeyError:
        if required:
            raise OfficeError("The file is not a valid Word/Excel document.") from None
        return None
    if info.file_size > MAX_PART_BYTES or (info.compress_size and info.file_size / info.compress_size > MAX_RATIO):
        raise OfficeError("The document is unusually large or compressed; not opening it.")
    data = z.read(info)
    head = data[:2048].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise OfficeError("The document contains unsafe XML; not opening it.")
    return ET.fromstring(data)


def _open(path: str) -> zipfile.ZipFile:
    import os
    if os.path.getsize(path) > MAX_ARCHIVE_BYTES:
        raise OfficeError("The document is larger than 25 MB.")
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise OfficeError("The file is not a valid Word/Excel document (maybe an old .doc/.xls?).") from None


def docx_text(path: str) -> str:
    with _open(path) as z:
        root = _part(z, "word/document.xml")
    lines = []
    for para in root.iter(f"{W}p"):
        text = "".join(t.text or "" for t in para.iter(f"{W}t"))
        tabs = len(list(para.iter(f"{W}tab")))
        lines.append(text if not tabs else text)
        if sum(len(l) for l in lines) > MAX_CHARS * 2:
            break
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


MAX_PDF_PAGES = 50


def pdf_text(path: str) -> str:
    """Text layer of a PDF (pypdf). Scanned PDFs have no text layer; that is said plainly."""
    import os
    if os.path.getsize(path) > MAX_ARCHIVE_BYTES:
        raise OfficeError("The PDF is larger than 25 MB.")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        raise OfficeError("PDF support is not installed.") from None
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            raise OfficeError("The PDF is password-protected; Sentinel does not open protected files.")
        out, total = [], 0
        for n, page in enumerate(reader.pages):
            if n >= MAX_PDF_PAGES:
                out.append(f"… (only the first {MAX_PDF_PAGES} pages were read)")
                break
            text = (page.extract_text() or "").strip()
            if text:
                out.append(f"## Page {n + 1}\n{text}")
                total += len(text)
            if total > MAX_CHARS * 2:
                break
    except OfficeError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError):
        raise OfficeError("The file is not a readable PDF.") from None
    if not out:
        return "(This PDF has no text layer; it is probably a scan. Reading scanned pages needs OCR, which is not available yet.)"
    return "\n\n".join(out)


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def xlsx_text(path: str, max_rows: int = 200) -> str:
    with _open(path) as z:
        shared_root = _part(z, "xl/sharedStrings.xml", required=False)
        shared = ["".join(t.text or "" for t in si.iter(f"{S}t")) for si in shared_root.iter(f"{S}si")] if shared_root is not None else []
        workbook = _part(z, "xl/workbook.xml")
        rels = _part(z, "xl/_rels/workbook.xml.rels")
        targets = {r.get("Id"): r.get("Target") for r in rels}
        out = []
        for sheet in workbook.iter(f"{S}sheet"):
            target = targets.get(sheet.get(f"{R}id"), "")
            target = target.lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            data = _part(z, target, required=False)
            if data is None:
                continue
            out.append(f"## Sheet: {sheet.get('name')}")
            for n, row in enumerate(data.iter(f"{S}row")):
                if n >= max_rows:
                    out.append(f"… (more rows not shown)")
                    break
                cells = {}
                for c in row.iter(f"{S}c"):
                    v = c.find(f"{S}v")
                    if c.get("t") == "s" and v is not None:
                        value = shared[int(v.text)] if v.text and v.text.isdigit() and int(v.text) < len(shared) else ""
                    elif c.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in c.iter(f"{S}t"))
                    else:
                        value = v.text if v is not None and v.text is not None else ""
                    cells[_col_index(c.get("r", ""))] = value
                if cells:
                    width = max(cells) + 1
                    out.append(" | ".join(cells.get(i, "") for i in range(min(width, 50))))
            if sum(len(l) for l in out) > MAX_CHARS * 2:
                break
    return "\n".join(out).strip()
