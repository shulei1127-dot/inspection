from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

SECTION_HEADING_RE = re.compile(r"^[一二三四五六七八九十0-9]+[、.．)]")


class ManualReportParseError(Exception):
    pass


@dataclass(frozen=True)
class ParsedParagraph:
    text: str
    section: str | None


@dataclass(frozen=True)
class ParsedTable:
    section: str | None
    rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedManualReport:
    paragraphs: list[ParsedParagraph] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)


def parse_manual_report(docx_path: Path) -> ParsedManualReport:
    if not docx_path.exists():
        raise ManualReportParseError("Manual report file does not exist.")
    if docx_path.suffix.lower() != ".docx":
        raise ManualReportParseError("Only .docx report files are supported.")

    try:
        with ZipFile(docx_path) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception as exc:  # pragma: no cover - zip-level corruption guard
        raise ManualReportParseError("Failed to read the .docx report.") from exc

    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise ManualReportParseError("Failed to parse the Word document XML.") from exc

    body = root.find("w:body", NS)
    if body is None:
        raise ManualReportParseError("The Word document does not contain a body.")

    paragraphs: list[ParsedParagraph] = []
    tables: list[ParsedTable] = []
    current_section: str | None = None

    for child in body:
        if child.tag == _w_tag("p"):
            text = _paragraph_text(child)
            if not text:
                continue
            if _is_section_heading(text):
                current_section = text
            paragraphs.append(ParsedParagraph(text=text, section=current_section))
        elif child.tag == _w_tag("tbl"):
            rows: list[list[str]] = []
            for row in child.findall("w:tr", NS):
                cells = [
                    _cell_text(cell)
                    for cell in row.findall("w:tc", NS)
                ]
                if any(cell for cell in cells):
                    rows.append(cells)
            if rows:
                tables.append(ParsedTable(section=current_section, rows=rows))

    return ParsedManualReport(paragraphs=paragraphs, tables=tables)


def _is_section_heading(text: str) -> bool:
    normalized = " ".join(text.split())
    return bool(
        SECTION_HEADING_RE.match(normalized)
        or normalized.endswith("检查")
        or normalized.endswith("结论")
        or normalized.endswith("建议")
    )


def _paragraph_text(paragraph: ET.Element) -> str:
    text = "".join(node.text or "" for node in paragraph.iter(_w_tag("t")))
    return " ".join(text.split())


def _cell_text(cell: ET.Element) -> str:
    text = "".join(node.text or "" for node in cell.iter(_w_tag("t")))
    return " ".join(text.split())


def _w_tag(name: str) -> str:
    return f"{{{W_NS}}}{name}"
