"""Word/Excel reading with the standard library, and its safety limits."""
import zipfile

import pytest

from app.core.office_text import OfficeError, docx_text, xlsx_text
from app.core.tool_registry import is_failure

DOCX_XML = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>Quarterly report</w:t></w:r></w:p>'
            '<w:p><w:r><w:t xml:space="preserve">Sales rose </w:t></w:r><w:r><w:t>12%.</w:t></w:r></w:p>'
            '</w:body></w:document>')

XLSX = {
    "xl/workbook.xml": ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                        '<sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets></workbook>'),
    "xl/_rels/workbook.xml.rels": ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>'),
    "xl/sharedStrings.xml": ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                             '<si><t>Item</t></si><si><t>Rent</t></si><si><t>Amount</t></si></sst>'),
    "xl/worksheets/sheet1.xml": ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                                 '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>2</v></c></row>'
                                 '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="C2"><v>15000</v></c></row>'
                                 '</sheetData></worksheet>'),
}


def make_zip(path, parts, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compression) as z:
        for name, text in parts.items():
            z.writestr(name, text)
    return str(path)


def test_docx_text(tmp_path):
    assert docx_text(make_zip(tmp_path / "r.docx", {"word/document.xml": DOCX_XML})) == "Quarterly report\nSales rose 12%."


def test_xlsx_text_keeps_columns(tmp_path):
    text = xlsx_text(make_zip(tmp_path / "b.xlsx", XLSX))
    assert text.splitlines() == ["## Sheet: Budget", "Item | Amount", "Rent |  | 15000"]


def test_xml_entities_are_refused(tmp_path):
    evil = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><w:document xmlns:w="x">&a;</w:document>'
    with pytest.raises(OfficeError, match="unsafe XML"):
        docx_text(make_zip(tmp_path / "e.docx", {"word/document.xml": evil}))


def test_zip_bomb_is_refused(tmp_path):
    bomb = DOCX_XML.replace("Quarterly report", "A" * (5 * 1024 * 1024))
    with pytest.raises(OfficeError, match="unusually large"):
        docx_text(make_zip(tmp_path / "bomb.docx", {"word/document.xml": bomb}))


def test_not_a_document(tmp_path):
    (tmp_path / "fake.docx").write_text("hello")
    with pytest.raises(OfficeError, match="not a valid"):
        docx_text(str(tmp_path / "fake.docx"))


def test_skill_reads_from_sentinel_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_FILES", str(tmp_path))
    make_zip(tmp_path / "plan.docx", {"word/document.xml": DOCX_XML})
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4")
    from skills.document_analysis import read_document
    assert "Sales rose 12%." in read_document("plan.docx")
    pdf = read_document("scan.pdf")
    assert is_failure(pdf) and "not a readable PDF" in pdf          # a broken PDF is refused plainly
    outside = read_document(str(tmp_path.parent / "elsewhere.docx"))
    assert is_failure(outside)


def minimal_pdf(text: str) -> bytes:
    """A tiny one-page PDF with a real text layer (byte offsets computed so the xref is valid)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_text(tmp_path):
    from app.core.office_text import pdf_text
    path = tmp_path / "letter.pdf"
    path.write_bytes(minimal_pdf("Invoice total 4200 rupees"))
    assert pdf_text(str(path)) == "## Page 1\nInvoice total 4200 rupees"


def test_pdf_without_text_is_explained(tmp_path):
    from app.core.office_text import pdf_text
    path = tmp_path / "scan.pdf"
    path.write_bytes(minimal_pdf(""))
    assert "no text layer" in pdf_text(str(path))
