#!/usr/bin/env python3

from __future__ import annotations

from copy import deepcopy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W_NS}


PARAGRAPH_REPLACEMENTS = {
    7: "{d.appendix.xray_customer_name}",
    16: "{d.appendix.xray_inspection_date_cn}",
    25: "二、日志自动检查项",
    28: "三、日志自动检查详情",
    36: "四、异常摘要与处置建议",
    37: "巡检结论：{d.appendix.xray_result_conclusion}",
    38: "重点告警：{d.appendix.xray_key_alerts}",
    39: "关键运行概况：{d.appendix.xray_key_runtime_overview}",
    40: "问题 - 证据 - 建议（按风险优先级排序）",
    41: "说明：以下问题按照“重启/健康检查告警 > 服务/容器异常 > 资源风险 > 其他观察”排序展示。",
    49: "巡检人：{d.appendix.xray_inspector_name}",
    50: "巡检时间：{d.appendix.xray_inspection_date}",
}

ISSUE_PARAGRAPHS = [
    "问题 1：{d.appendix.xray_issue_1_problem}",
    "证据：{d.appendix.xray_issue_1_evidence}",
    "建议：{d.appendix.xray_issue_1_recommendation}",
    "",
    "问题 2：{d.appendix.xray_issue_2_problem}",
    "证据：{d.appendix.xray_issue_2_evidence}",
    "建议：{d.appendix.xray_issue_2_recommendation}",
    "",
    "问题 3：{d.appendix.xray_issue_3_problem}",
    "证据：{d.appendix.xray_issue_3_evidence}",
    "建议：{d.appendix.xray_issue_3_recommendation}",
]

TABLE_REPLACEMENTS = {
    (0, 0, 1): "{d.appendix.xray_node_info}",
    (0, 1, 1): "{d.appendix.xray_product_version}",
    (0, 2, 1): "{d.appendix.xray_engine_version}",
    (0, 3, 1): "{d.appendix.xray_vuln_db_version}",
    (0, 4, 1): "{d.appendix.xray_machine_id}",
    (0, 5, 1): "{d.appendix.xray_license_validity}",
    (1, 1, 0): "自动检查项（日志自动可得）",
    (1, 1, 1): "当前日志 / health 输出",
    (1, 1, 2): "-",
    (1, 1, 3): "以下项目结论直接来自本次上传日志",
    (1, 2, 0): "管理节点健康检查",
    (1, 2, 1): "在安装目录执行 ./minion mgmt health",
    (1, 2, 2): "{d.appendix.xray_mgmt_health_result}",
    (1, 2, 3): "{d.appendix.xray_mgmt_health_note}",
    (1, 3, 0): "引擎节点健康检查",
    (1, 3, 1): "在安装目录执行 ./minion engine health",
    (1, 3, 2): "{d.appendix.xray_engine_health_result}",
    (1, 3, 3): "{d.appendix.xray_engine_health_note}",
    (1, 4, 0): "运行状态检查",
    (1, 4, 1): "minion 日志 + docker ps -a + 服务状态",
    (1, 4, 2): "{d.appendix.xray_runtime_status_result}",
    (1, 4, 3): "{d.appendix.xray_runtime_status_note}",
    (2, 0, 0): "管理节点自动检查摘要",
    (2, 0, 1): "{d.appendix.xray_mgmt_node_health}",
    (2, 1, 0): "节点负载状态",
    (2, 1, 1): "CPU使用率",
    (2, 2, 0): "",
    (2, 2, 1): "内存使用率",
    (3, 0, 0): "引擎节点自动检查摘要",
    (3, 0, 1): "{d.appendix.xray_engine_node_health}",
    (3, 1, 0): "节点负载状态",
    (3, 1, 1): "CPU使用率",
    (3, 2, 0): "",
    (3, 2, 1): "内存使用率",
}

PARAGRAPH_TEXTS_TO_REMOVE = {
    "{d.appendix.xray_cover_summary_1}",
    "{d.appendix.xray_cover_summary_2}",
    "总体情况",
    "巡检详情",
    "以下内容为具体设备巡检详情：",
}

TABLE_ROWS_TO_REMOVE = {
    1: [8, 7, 6, 5],
}


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: build_xray_template_v1.py <source_docx> <target_docx>",
            file=sys.stderr,
        )
        return 1

    source_path = Path(sys.argv[1]).expanduser().resolve()
    target_path = Path(sys.argv[2]).expanduser().resolve()

    if not source_path.exists():
        print(f"Source template does not exist: {source_path}", file=sys.stderr)
        return 1

    files = _read_docx_files(source_path)
    root = ET.fromstring(files["word/document.xml"])
    body = root.find("w:body", NS)
    if body is None:
        print("word/document.xml does not contain <w:body>.", file=sys.stderr)
        return 1

    paragraphs = [child for child in body if child.tag == _w_tag("p")]
    tables = [child for child in body if child.tag == _w_tag("tbl")]

    for index, replacement in PARAGRAPH_REPLACEMENTS.items():
        _replace_paragraph_text(paragraphs[index], replacement)

    for (table_index, row_index, cell_index), replacement in TABLE_REPLACEMENTS.items():
        _replace_cell_text(tables[table_index], row_index, cell_index, replacement)

    _remove_paragraphs_by_text(body, PARAGRAPH_TEXTS_TO_REMOVE)
    _remove_paragraphs_starting_with(
        body,
        "整体状态：{d.appendix.xray_executive_status}",
    )
    _remove_table_rows(tables, TABLE_ROWS_TO_REMOVE)

    issue_note_anchor = _find_body_paragraph(
        body,
        PARAGRAPH_REPLACEMENTS[41],
    )
    inspector_anchor = _find_body_paragraph(
        body,
        PARAGRAPH_REPLACEMENTS[49],
    )
    _reset_issue_section(
        body,
        after_paragraph=issue_note_anchor,
        before_paragraph=inspector_anchor,
        paragraph_template=paragraphs[38],
        texts=ISSUE_PARAGRAPHS,
    )
    _remove_duplicate_trailing_issue_paragraphs(body)

    files["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    _write_docx_files(target_path, files)
    print(target_path)
    return 0


def _read_docx_files(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _write_docx_files(path: Path, files: dict[str, bytes]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _replace_cell_text(table: ET.Element, row_index: int, cell_index: int, text: str) -> None:
    rows = table.findall("w:tr", NS)
    cells = rows[row_index].findall("w:tc", NS)
    paragraphs = cells[cell_index].findall("w:p", NS)
    if not paragraphs:
        paragraph = ET.SubElement(cells[cell_index], _w_tag("p"))
    else:
        paragraph = paragraphs[0]
    _replace_paragraph_text(paragraph, text)
    for extra_paragraph in paragraphs[1:]:
        _replace_paragraph_text(extra_paragraph, "")


def _replace_paragraph_text(paragraph: ET.Element, text: str) -> None:
    for child in list(paragraph):
        if child.tag != _w_tag("pPr"):
            paragraph.remove(child)

    run = ET.SubElement(paragraph, _w_tag("r"))
    ET.SubElement(run, _w_tag("rPr"))
    text_node = ET.SubElement(run, _w_tag("t"))
    if text.startswith(" ") or text.endswith(" "):
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = text


def _reset_issue_section(
    body: ET.Element,
    *,
    after_paragraph: ET.Element,
    before_paragraph: ET.Element,
    paragraph_template: ET.Element,
    texts: list[str],
) -> None:
    children = list(body)
    start_index = children.index(after_paragraph) + 1
    end_index = children.index(before_paragraph)
    for child in children[start_index:end_index]:
        body.remove(child)

    for offset, text in enumerate(texts):
        paragraph = deepcopy(paragraph_template)
        _replace_paragraph_text(paragraph, text)
        body.insert(start_index + offset, paragraph)


def _find_body_paragraph(body: ET.Element, text: str) -> ET.Element:
    for child in body:
        if child.tag != _w_tag("p"):
            continue
        if _paragraph_text(child) == text:
            return child
    raise ValueError(f"Paragraph not found: {text}")


def _remove_paragraphs_by_text(body: ET.Element, texts: set[str]) -> None:
    for child in list(body):
        if child.tag == _w_tag("p") and _paragraph_text(child).strip() in texts:
            body.remove(child)


def _remove_paragraphs_starting_with(body: ET.Element, prefix: str) -> None:
    for child in list(body):
        if child.tag == _w_tag("p") and _paragraph_text(child).strip().startswith(prefix):
            body.remove(child)


def _remove_table_rows(tables: list[ET.Element], rows_by_table: dict[int, list[int]]) -> None:
    for table_index, row_indexes in rows_by_table.items():
        if table_index >= len(tables):
            continue
        rows = tables[table_index].findall("w:tr", NS)
        for row_index in row_indexes:
            if row_index < len(rows):
                tables[table_index].remove(rows[row_index])


def _remove_duplicate_trailing_issue_paragraphs(body: ET.Element) -> None:
    seen_inspection_date = False
    for child in list(body):
        if child.tag != _w_tag("p"):
            continue
        if _paragraph_text(child).strip() == "巡检时间：{d.appendix.xray_inspection_date}":
            if not seen_inspection_date:
                seen_inspection_date = True
                continue
        elif not seen_inspection_date:
            continue
        body.remove(child)


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(_w_tag("t")))


def _w_tag(name: str) -> str:
    return f"{{{W_NS}}}{name}"


if __name__ == "__main__":
    raise SystemExit(main())
