from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, is_zipfile

from app.schemas.audit_result import AuditResultV1
from app.schemas.log_evidence import LogEvidenceV1
from app.services.audit_opinion_renderer import (
    build_audit_opinion_sections,
    build_container_audit_rows,
)
from app.schemas.trend_assessment import (
    TrendAssessmentV1,
    TrendFaultChain,
    TrendMetricAssessment,
    TrendStabilityEventCounts,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PR_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

NS = {
    "w": W_NS,
    "r": R_NS,
    "wp": WP_NS,
    "a": A_NS,
    "pic": PIC_NS,
}

for prefix, uri in {
    "w": W_NS,
    "r": R_NS,
    "wp": WP_NS,
    "a": A_NS,
    "pic": PIC_NS,
}.items():
    ET.register_namespace(prefix, uri)


class ReportAugmentError(Exception):
    pass


STATUS_LABELS = {
    "stable": "稳定",
    "pressure_high": "压力较高",
    "deteriorating": "呈恶化趋势",
    "unknown": "信息不足",
}

CONFIDENCE_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}

DATA_QUALITY_LABELS = {
    "sufficient": "较完整",
    "partial": "部分可用",
    "insufficient": "明显不足",
}


def augment_report_with_trend_appendix(
    base_report_path: Path,
    *,
    assessment: TrendAssessmentV1,
    chart_paths: list[Path],
    output_path: Path,
) -> Path:
    if not base_report_path.exists():
        raise ReportAugmentError("Base report docx does not exist.")
    if base_report_path.suffix.lower() != ".docx" or not is_zipfile(base_report_path):
        raise ReportAugmentError("Base report is not a valid .docx document.")
    try:
        files = _read_docx_files(base_report_path)
    except Exception as exc:  # pragma: no cover - corruption guard
        raise ReportAugmentError("Failed to read the base docx report.") from exc

    if "word/document.xml" not in files:
        raise ReportAugmentError("Base docx does not contain word/document.xml.")

    document_root = ET.fromstring(files["word/document.xml"])
    body = document_root.find("w:body", NS)
    if body is None:
        raise ReportAugmentError("Base docx does not contain word/document.xml body.")

    relationships_root = _load_relationships_root(files)
    _ensure_png_content_type(files)

    _append_paragraph(body, "附录：趋势增强分析")
    _append_paragraph(body, "一、数据来源与评估口径")
    _append_paragraph(body, "本附录仅基于状态分析报告中已存在的时间点与已记录事件，按规则生成保守趋势判断。")
    _append_paragraph(body, "二、总体趋势结论")
    _append_paragraph(body, _overall_text(assessment))
    _append_paragraph(body, "三、分项趋势判断")
    for label, metric in [
        ("CPU 趋势", assessment.metrics.cpu),
        ("内存趋势", assessment.metrics.memory),
        ("磁盘趋势", assessment.metrics.disk),
        ("稳定性 / 重启风险", assessment.metrics.stability),
    ]:
        _append_paragraph(body, label)
        _append_paragraph(body, _metric_text(metric))

    _append_paragraph(body, "四、趋势图表")
    if not chart_paths:
        _append_paragraph(body, "当前可用历史点少于 2 个，本阶段按保守策略未追加图表。")
    else:
        for chart_path in chart_paths:
            relationship_id = _add_image_relationship(files, relationships_root, chart_path)
            _append_paragraph(body, f"图表：{chart_path.name}")
            _append_image(body, relationship_id=relationship_id, image_path=chart_path)

    _append_paragraph(body, "五、保守说明")
    _append_paragraph(body, "本阶段只输出弱预测状态，不做数值外推；当证据不足时优先输出信息不足。")

    files["word/document.xml"] = ET.tostring(document_root, encoding="utf-8", xml_declaration=True)
    files["word/_rels/document.xml.rels"] = ET.tostring(
        relationships_root,
        encoding="utf-8",
        xml_declaration=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_docx_files(output_path, files)
    return output_path


def augment_report_with_audit_appendix(
    base_report_path: Path,
    *,
    audit_result: AuditResultV1,
    log_evidence: LogEvidenceV1 | None = None,
    output_path: Path,
) -> Path:
    if not base_report_path.exists():
        raise ReportAugmentError("Base report docx does not exist.")
    if base_report_path.suffix.lower() != ".docx" or not is_zipfile(base_report_path):
        raise ReportAugmentError("Base report is not a valid .docx document.")
    try:
        files = _read_docx_files(base_report_path)
    except Exception as exc:  # pragma: no cover - corruption guard
        raise ReportAugmentError("Failed to read the base docx report.") from exc

    if "word/document.xml" not in files:
        raise ReportAugmentError("Base docx does not contain word/document.xml.")

    document_root = ET.fromstring(files["word/document.xml"])
    body = document_root.find("w:body", NS)
    if body is None:
        raise ReportAugmentError("Base docx does not contain word/document.xml body.")

    _append_paragraph(body, "附录：日志核验意见")
    _append_paragraph(
        body,
        (
            f"核验统计：已证实 {audit_result.summary.confirmed_count} 项；"
            f"部分证实 {audit_result.summary.partially_confirmed_count} 项；"
            f"冲突 {audit_result.summary.conflict_count} 项；"
            f"证据不足 {audit_result.summary.insufficient_count} 项；"
            f"仍需人工判断 {audit_result.summary.manual_only_count} 项。"
        ),
    )
    for title, rows in build_audit_opinion_sections(audit_result, log_evidence=log_evidence):
        _append_paragraph(body, title)
        if title == "容器运行状况核验":
            container_rows = build_container_audit_rows(log_evidence)
            if container_rows:
                _append_table(
                    body,
                    headers=["容器名称", "当前状态", "CPU使用率", "内存使用率", "日志依据", "处置建议"],
                    rows=[
                        [
                            row.container_name,
                            row.status_label,
                            row.cpu_usage,
                            row.memory_usage,
                            row.risk_summary,
                            row.suggestion or "无",
                        ]
                        for row in container_rows
                    ],
                )
            for row in rows:
                if row.startswith("- 说明：") or row.startswith("- 当前"):
                    _append_paragraph(body, row)
            continue
        for row in rows:
            _append_paragraph(body, row)

    files["word/document.xml"] = ET.tostring(document_root, encoding="utf-8", xml_declaration=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_docx_files(output_path, files)
    return output_path


def _read_docx_files(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _write_docx_files(path: Path, files: dict[str, bytes]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def _load_relationships_root(files: dict[str, bytes]) -> ET.Element:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path in files:
        return ET.fromstring(files[rels_path])
    return ET.fromstring(
        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        b"<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'/>"
    )


def _ensure_png_content_type(files: dict[str, bytes]) -> None:
    root = ET.fromstring(files["[Content_Types].xml"])
    existing = {
        element.attrib.get("Extension", "").lower()
        for element in root.findall(f"{{{CT_NS}}}Default")
    }
    if "png" not in existing:
        default = ET.SubElement(root, f"{{{CT_NS}}}Default")
        default.set("Extension", "png")
        default.set("ContentType", "image/png")
        files["[Content_Types].xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _append_paragraph(body: ET.Element, text: str) -> None:
    paragraph = ET.Element(f"{{{W_NS}}}p")
    run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
    text_node = ET.SubElement(run, f"{{{W_NS}}}t")
    text_node.text = text
    _insert_before_sect_pr(body, paragraph)


def _append_table(body: ET.Element, *, headers: list[str], rows: list[list[str]]) -> None:
    table = ET.Element(f"{{{W_NS}}}tbl")
    table_properties = ET.SubElement(table, f"{{{W_NS}}}tblPr")
    table_borders = ET.SubElement(table_properties, f"{{{W_NS}}}tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = ET.SubElement(table_borders, f"{{{W_NS}}}{edge}")
        border.set(f"{{{W_NS}}}val", "single")
        border.set(f"{{{W_NS}}}sz", "4")
        border.set(f"{{{W_NS}}}space", "0")
        border.set(f"{{{W_NS}}}color", "auto")

    table_grid = ET.SubElement(table, f"{{{W_NS}}}tblGrid")
    for _ in headers:
        grid_col = ET.SubElement(table_grid, f"{{{W_NS}}}gridCol")
        grid_col.set(f"{{{W_NS}}}w", "2000")

    table.append(_build_table_row(headers, header=True))
    for row in rows:
        table.append(_build_table_row(row, header=False))
    _insert_before_sect_pr(body, table)


def _build_table_row(values: list[str], *, header: bool) -> ET.Element:
    row = ET.Element(f"{{{W_NS}}}tr")
    for value in values:
        cell = ET.SubElement(row, f"{{{W_NS}}}tc")
        cell_properties = ET.SubElement(cell, f"{{{W_NS}}}tcPr")
        cell_width = ET.SubElement(cell_properties, f"{{{W_NS}}}tcW")
        cell_width.set(f"{{{W_NS}}}type", "dxa")
        cell_width.set(f"{{{W_NS}}}w", "2000")
        paragraph = ET.SubElement(cell, f"{{{W_NS}}}p")
        run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
        if header:
            run_properties = ET.SubElement(run, f"{{{W_NS}}}rPr")
            ET.SubElement(run_properties, f"{{{W_NS}}}b")
        text_node = ET.SubElement(run, f"{{{W_NS}}}t")
        text_node.text = value
    return row


def _append_image(body: ET.Element, *, relationship_id: str, image_path: Path) -> None:
    width_px, height_px = _read_png_dimensions(image_path)
    scale = min(520 / max(width_px, 1), 1.0)
    width_emu = int(width_px * 9525 * scale)
    height_emu = int(height_px * 9525 * scale)

    paragraph = ET.Element(f"{{{W_NS}}}p")
    run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
    drawing = ET.SubElement(run, f"{{{W_NS}}}drawing")
    inline = ET.SubElement(drawing, f"{{{WP_NS}}}inline")
    inline.set("distT", "0")
    inline.set("distB", "0")
    inline.set("distL", "0")
    inline.set("distR", "0")
    extent = ET.SubElement(inline, f"{{{WP_NS}}}extent")
    extent.set("cx", str(width_emu))
    extent.set("cy", str(height_emu))
    doc_pr = ET.SubElement(inline, f"{{{WP_NS}}}docPr")
    doc_pr.set("id", "1")
    doc_pr.set("name", image_path.name)
    c_nv = ET.SubElement(inline, f"{{{WP_NS}}}cNvGraphicFramePr")
    locks = ET.SubElement(c_nv, f"{{{A_NS}}}graphicFrameLocks")
    locks.set("noChangeAspect", "1")
    graphic = ET.SubElement(inline, f"{{{A_NS}}}graphic")
    graphic_data = ET.SubElement(graphic, f"{{{A_NS}}}graphicData")
    graphic_data.set("uri", PIC_NS)
    pic = ET.SubElement(graphic_data, f"{{{PIC_NS}}}pic")
    nv_pic = ET.SubElement(pic, f"{{{PIC_NS}}}nvPicPr")
    c_nv_pr = ET.SubElement(nv_pic, f"{{{PIC_NS}}}cNvPr")
    c_nv_pr.set("id", "0")
    c_nv_pr.set("name", image_path.name)
    ET.SubElement(nv_pic, f"{{{PIC_NS}}}cNvPicPr")
    blip_fill = ET.SubElement(pic, f"{{{PIC_NS}}}blipFill")
    blip = ET.SubElement(blip_fill, f"{{{A_NS}}}blip")
    blip.set(f"{{{R_NS}}}embed", relationship_id)
    stretch = ET.SubElement(blip_fill, f"{{{A_NS}}}stretch")
    ET.SubElement(stretch, f"{{{A_NS}}}fillRect")
    sp_pr = ET.SubElement(pic, f"{{{PIC_NS}}}spPr")
    xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    off = ET.SubElement(xfrm, f"{{{A_NS}}}off")
    off.set("x", "0")
    off.set("y", "0")
    ext = ET.SubElement(xfrm, f"{{{A_NS}}}ext")
    ext.set("cx", str(width_emu))
    ext.set("cy", str(height_emu))
    geom = ET.SubElement(sp_pr, f"{{{A_NS}}}prstGeom")
    geom.set("prst", "rect")
    ET.SubElement(geom, f"{{{A_NS}}}avLst")
    _insert_before_sect_pr(body, paragraph)


def _insert_before_sect_pr(body: ET.Element, element: ET.Element) -> None:
    for index, child in enumerate(list(body)):
        if child.tag == f"{{{W_NS}}}sectPr":
            body.insert(index, element)
            return
    body.append(element)


def _add_image_relationship(files: dict[str, bytes], relationships_root: ET.Element, image_path: Path) -> str:
    relationship_id = _next_relationship_id(relationships_root)
    media_index = _next_media_index(files)
    target = f"media/trend_image_{media_index}.png"
    files[f"word/{target}"] = image_path.read_bytes()
    relationship = ET.SubElement(relationships_root, f"{{{PR_NS}}}Relationship")
    relationship.set("Id", relationship_id)
    relationship.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
    )
    relationship.set("Target", target)
    return relationship_id


def _next_relationship_id(root: ET.Element) -> str:
    max_id = 0
    for child in root:
        match = re.match(r"rId(\d+)", child.attrib.get("Id", ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"rId{max_id + 1}"


def _next_media_index(files: dict[str, bytes]) -> int:
    indices = []
    for name in files:
        match = re.search(r"trend_image_(\d+)\.png$", name)
        if match:
            indices.append(int(match.group(1)))
    return max(indices, default=0) + 1


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    content = path.read_bytes()
    if content[:8] != b"\x89PNG\r\n\x1a\n":
        raise ReportAugmentError(f"Not a valid PNG file: {path}")
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    return width, height


def _overall_text(assessment: TrendAssessmentV1) -> str:
    caution_text = _join_statements(assessment.overall.cautions) or "无额外保守提示"
    return (
        f"总体状态：{STATUS_LABELS[assessment.overall.summary_status]}。"
        f"数据质量：{DATA_QUALITY_LABELS[assessment.overall.data_quality]}。"
        f"提示：{caution_text}。"
    )


def _metric_text(metric: TrendMetricAssessment) -> str:
    parts = [
        f"状态={STATUS_LABELS[metric.status]}",
        f"置信度={CONFIDENCE_LABELS[metric.confidence]}",
    ]
    if metric.current_value is not None:
        parts.append(f"当前快照值={metric.current_value:.1f}%")
    if metric.baseline_value is not None and metric.delta is not None:
        parts.append(f"基线值={metric.baseline_value:.1f}%")
        parts.append(f"变化={metric.delta:+.1f} 个百分点")
    if metric.evidence:
        parts.append("依据=" + _join_statements(metric.evidence))
    if metric.event_counts is not None:
        parts.append("事件拆分=" + _render_event_counts(metric.event_counts))
    if metric.fault_chains:
        parts.append("故障链=" + _render_fault_chains(metric.fault_chains))
    return "；".join(parts) + "。"


def _join_statements(statements: list[str]) -> str:
    cleaned = []
    for statement in statements:
        normalized = statement.strip().rstrip("。；;，,")
        if normalized:
            cleaned.append(normalized)
    return "；".join(cleaned)


def _render_event_counts(event_counts: TrendStabilityEventCounts) -> str:
    return (
        f"restart={event_counts.restart_count}，"
        f"panic={event_counts.panic_count}，"
        f"abnormal_exit={event_counts.abnormal_exit_count}，"
        f"unclean_shutdown={event_counts.unclean_shutdown_count}"
    )


def _render_fault_chains(fault_chains: list[TrendFaultChain]) -> str:
    return "；".join(chain.summary for chain in fault_chains[:2])
