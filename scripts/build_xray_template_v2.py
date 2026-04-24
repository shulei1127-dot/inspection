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
    13: "{d.appendix.xray_inspection_date_cn}",
    28: "（2）引擎节点",
    34: "巡检结论：{d.appendix.xray_result_conclusion}",
    35: "",
    36: "重点告警：{d.appendix.xray_key_alerts}",
    37: "关键运行概况：{d.appendix.xray_key_runtime_overview}",
    41: "问题 1：{d.appendix.xray_issue_1_problem}",
    42: "证据：{d.appendix.xray_issue_1_evidence}",
    43: "建议：{d.appendix.xray_issue_1_recommendation}",
    45: "问题 2：{d.appendix.xray_issue_2_problem}",
    46: "证据：{d.appendix.xray_issue_2_evidence}",
    47: "建议：{d.appendix.xray_issue_2_recommendation}",
    49: "问题 3：{d.appendix.xray_issue_3_problem}",
    50: "证据：{d.appendix.xray_issue_3_evidence}",
    51: "建议：{d.appendix.xray_issue_3_recommendation}",
    52: "巡检人：{d.appendix.xray_inspector_name}",
    53: "巡检时间：{d.appendix.xray_inspection_date}",
}


TABLE_REPLACEMENTS = {
    (0, 0, 1): "{d.appendix.xray_node_info}",
    (0, 1, 1): "{d.appendix.xray_product_version}",
    (0, 2, 1): "{d.appendix.xray_engine_version}",
    (0, 3, 1): "{d.appendix.xray_vuln_db_version}",
    (0, 4, 1): "{d.appendix.xray_machine_id}",
    (1, 1, 1): "{d.appendix.xray_mgmt_health_result}",
    (1, 1, 2): "{d.appendix.xray_mgmt_health_note}",
    (1, 2, 1): "{d.appendix.xray_engine_health_result}",
    (1, 2, 2): "{d.appendix.xray_engine_health_note}",
    (1, 3, 1): "正常",
    (1, 3, 2): "{d.appendix.xray_mgmt_cpu}",
    (1, 4, 1): "正常",
    (1, 4, 2): "{d.appendix.xray_mgmt_memory}",
    (1, 5, 1): "{d.appendix.xray_runtime_status_result}",
    (1, 5, 2): "{d.appendix.xray_runtime_status_note}",
    (3, 1, 0): "CPU使用率",
    (3, 1, 1): "{d.appendix.xray_mgmt_cpu}",
    (3, 2, 0): "内存使用率",
    (3, 2, 1): "{d.appendix.xray_mgmt_memory}",
    (3, 3, 0): "磁盘使用率",
    (3, 3, 1): "{d.appendix.xray_mgmt_disk}",
    (4, 1, 0): "CPU使用率",
    (4, 1, 1): "{d.appendix.xray_engine_cpu}",
    (4, 2, 0): "内存使用率",
    (4, 2, 1): "{d.appendix.xray_engine_memory}",
    (4, 3, 0): "服务状态",
    (4, 3, 1): "{d.appendix.xray_engine_service_status}",
    (4, 4, 0): "磁盘使用率",
    (4, 4, 1): "{d.appendix.xray_engine_disk}",
}


CONTAINER_LOOP_ROWS = [
    [
        "{d.container_rows[i].name}",
        "{d.container_rows[i].status_label}",
        "{d.container_rows[i].cpu_percent}",
        "{d.container_rows[i].memory_percent}",
    ],
    [
        "{d.container_rows[i+1].name}",
        "{d.container_rows[i+1].status_label}",
        "{d.container_rows[i+1].cpu_percent}",
        "{d.container_rows[i+1].memory_percent}",
    ],
]


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: build_xray_template_v2.py <source_docx> <target_docx>",
            file=sys.stderr,
        )
        return 1

    source_path = Path(sys.argv[1]).expanduser().resolve()
    target_path = Path(sys.argv[2]).expanduser().resolve()
    if not source_path.exists():
        print(f"Source DOCX does not exist: {source_path}", file=sys.stderr)
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
        if index < len(paragraphs):
            _replace_paragraph_text(paragraphs[index], replacement)

    for (table_index, row_index, cell_index), replacement in TABLE_REPLACEMENTS.items():
        _replace_cell_text(tables[table_index], row_index, cell_index, replacement)

    _rewrite_container_table(tables[2])
    _rewrite_node_detail_table(
        tables[3],
        rows=[
            ("节点负载状态", "CPU 使用率", "{d.appendix.xray_mgmt_cpu}", "restart"),
            ("", "内存使用率", "{d.appendix.xray_mgmt_memory}", "continue"),
            ("磁盘状态", "磁盘使用率", "{d.appendix.xray_mgmt_disk}", None),
            ("操作系统", "", "", None),
        ],
    )
    _rewrite_node_detail_table(
        tables[4],
        rows=[
            ("节点负载状态", "CPU 使用率", "{d.appendix.xray_engine_cpu}", "restart"),
            ("", "内存使用率", "{d.appendix.xray_engine_memory}", "continue"),
            ("磁盘状态", "磁盘使用率", "{d.appendix.xray_engine_disk}", None),
            ("服务状态", "服务状态", "{d.appendix.xray_engine_service_status}", None),
            ("操作系统", "", "", None),
        ],
    )
    _remove_empty_paragraph_after_conclusion(body)

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


def _rewrite_container_table(table: ET.Element) -> None:
    rows = table.findall("w:tr", NS)
    if len(rows) < 2:
        return

    row_template = deepcopy(rows[1])
    for row in rows[1:]:
        table.remove(row)

    for row_values in CONTAINER_LOOP_ROWS:
        row = deepcopy(row_template)
        for cell_index, value in enumerate(row_values):
            _replace_cell_text_in_row(row, cell_index, value)
        table.append(row)


def _rewrite_node_detail_table(
    table: ET.Element,
    *,
    rows: list[tuple[str, str, str, str | None]],
) -> None:
    existing_rows = table.findall("w:tr", NS)
    if len(existing_rows) < 2:
        return

    header_template = deepcopy(existing_rows[0])
    row_template = deepcopy(existing_rows[1])
    for row in existing_rows:
        table.remove(row)

    _reset_row_cells(header_template, ["节点检查", "详情"])
    header_cells = header_template.findall("w:tc", NS)
    _set_cell_grid_span(header_cells[1], "2")
    table.append(header_template)

    for label, metric, detail, merge_mode in rows:
        row = deepcopy(row_template)
        _reset_row_cells(row, [label, metric, detail])
        cells = row.findall("w:tc", NS)
        if merge_mode is not None:
            _set_cell_vmerge(cells[0], merge_mode)
        else:
            _remove_cell_vmerge(cells[0])
        if metric == "" and detail == "":
            _set_cell_grid_span(cells[1], "2")
            row.remove(cells[2])
        table.append(row)


def _reset_row_cells(row: ET.Element, values: list[str]) -> None:
    cells = row.findall("w:tc", NS)
    while len(cells) < len(values):
        cells.append(deepcopy(cells[-1]))
        row.append(cells[-1])

    for cell in cells:
        _remove_cell_grid_span(cell)
        _remove_cell_vmerge(cell)

    for index, value in enumerate(values):
        _replace_cell_text_in_row(row, index, value)

    for extra_cell in cells[len(values):]:
        row.remove(extra_cell)


def _set_cell_grid_span(cell: ET.Element, value: str) -> None:
    tc_pr = _ensure_tc_pr(cell)
    _remove_cell_grid_span(cell)
    grid_span = ET.SubElement(tc_pr, _w_tag("gridSpan"))
    grid_span.set(_w_tag("val"), value)


def _remove_cell_grid_span(cell: ET.Element) -> None:
    tc_pr = cell.find("w:tcPr", NS)
    if tc_pr is None:
        return
    for grid_span in tc_pr.findall("w:gridSpan", NS):
        tc_pr.remove(grid_span)


def _set_cell_vmerge(cell: ET.Element, value: str) -> None:
    tc_pr = _ensure_tc_pr(cell)
    _remove_cell_vmerge(cell)
    vmerge = ET.SubElement(tc_pr, _w_tag("vMerge"))
    if value != "continue":
        vmerge.set(_w_tag("val"), value)


def _remove_cell_vmerge(cell: ET.Element) -> None:
    tc_pr = cell.find("w:tcPr", NS)
    if tc_pr is None:
        return
    for vmerge in tc_pr.findall("w:vMerge", NS):
        tc_pr.remove(vmerge)


def _ensure_tc_pr(cell: ET.Element) -> ET.Element:
    tc_pr = cell.find("w:tcPr", NS)
    if tc_pr is not None:
        return tc_pr
    tc_pr = ET.Element(_w_tag("tcPr"))
    cell.insert(0, tc_pr)
    return tc_pr


def _remove_empty_paragraph_after_conclusion(body: ET.Element) -> None:
    for child in list(body):
        if child.tag == _w_tag("p") and _paragraph_text(child) == "":
            # Keep intentional spacing elsewhere; only remove the empty paragraph
            # that sits between the conclusion label and the dynamic conclusion.
            previous = _previous_body_child(body, child)
            if previous is not None and _paragraph_text(previous).startswith("巡检结论："):
                body.remove(child)
                return


def _previous_body_child(body: ET.Element, target: ET.Element) -> ET.Element | None:
    previous = None
    for child in body:
        if child is target:
            return previous
        previous = child
    return None


def _replace_cell_text(table: ET.Element, row_index: int, cell_index: int, text: str) -> None:
    rows = table.findall("w:tr", NS)
    _replace_cell_text_in_row(rows[row_index], cell_index, text)


def _replace_cell_text_in_row(row: ET.Element, cell_index: int, text: str) -> None:
    cells = row.findall("w:tc", NS)
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


def _cell_text(cell: ET.Element) -> str:
    return "".join(node.text or "" for node in cell.iter(_w_tag("t")))


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(_w_tag("t")))


def _w_tag(name: str) -> str:
    return f"{{{W_NS}}}{name}"


if __name__ == "__main__":
    raise SystemExit(main())
