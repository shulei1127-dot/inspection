from __future__ import annotations

from itertools import count
import re

from app.schemas.report_claims import ReportClaim, ReportClaimsV1
from app.services.claim_review_policy import build_claim_review_policy
from app.services.manual_report_parser import ParsedManualReport


VERSION_RE = re.compile(r"\b(?:v)?\d+(?:\.\d+){1,4}(?:[-_a-zA-Z0-9]+)?\b")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
COMPONENT_KEYWORDS = [
    "redis",
    "nginx",
    "postgres",
    "mysql",
    "api",
    "gateway",
    "engine",
    "waf",
]
INSTRUCTIONAL_TEXT_MARKERS = (
    "检查结果分为",
    "-正常：",
    "-异常：",
    "给出异常描述和处理建议",
)
NO_EXCEPTION_PATTERNS = (
    "0个异常",
    "无异常",
    "无异常日志",
    "未发现异常",
    "0个风险",
    "无风险",
)
HEALTHY_SUMMARY_MARKERS = (
    "运行状态良好",
    "系统当前良好",
    "系统当前运行状态良好",
    "核心功能正常",
    "节点健康检查都正常",
    "容器状态均正常",
    "满足安全巡检要求",
)
WARNING_SUMMARY_MARKERS = (
    "可改进点",
    "建议关注",
    "需要关注",
)
ABNORMAL_SUMMARY_MARKERS = (
    "存在异常",
    "发现异常",
    "存在风险",
    "发现风险",
    "存在告警",
    "发现告警",
)
MANUAL_ONLY_MARKERS = (
    "物理状态",
    "防护报告",
    "日报",
    "周报",
    "月报",
    "站点防护",
    "防护配置",
    "策略配置",
    "页面访问",
    "登录功能",
)


def normalize_report_claims(
    parsed_report: ParsedManualReport,
    *,
    task_id: str,
) -> ReportClaimsV1:
    claims: list[ReportClaim] = []
    claim_counter = count(1)

    for table in parsed_report.tables:
        header = [cell.lower() for cell in table.rows[0]] if table.rows else []
        for row in table.rows[1:] if len(table.rows) > 1 else []:
            row_text = " | ".join(row)
            key = row[0] if row else ""
            value = " ".join(cell for cell in row[1:] if cell).strip() or row_text
            lowered = f"{key} {value}".lower()

            if "版本" in key or "version" in lowered:
                # Version/device metadata is treated as report-sourced in v1.
                continue

            if any(token in lowered for token in ("运行状态", "服务状态", "容器状态")):
                normalized_status = _normalize_runtime_status(value)
                if normalized_status is None:
                    continue
                claims.append(
                    _build_claim(
                        next(claim_counter),
                        claim_type="component_runtime_status",
                        source_section=table.section,
                        source_text=row_text,
                        subject=_extract_subject(key, value),
                        metric=None,
                        assertion="status",
                        expected_value=normalized_status,
                        auditability="direct",
                    )
                )
                continue

            if "健康" in lowered:
                normalized_health = _normalize_health_status(value)
                if normalized_health is None:
                    continue
                claims.append(
                    _build_claim(
                        next(claim_counter),
                        claim_type="component_health_status",
                        source_section=table.section,
                        source_text=row_text,
                        subject=_extract_subject(key, value),
                        metric=None,
                        assertion="health",
                        expected_value=normalized_health,
                        auditability="direct",
                    )
                )
                continue

            resource_claim = _resource_claim_from_row(
                row,
                table.section,
                claim_id=next(claim_counter),
            )
            if resource_claim is not None:
                claims.append(resource_claim)
                continue

            resource_claim = _resource_claim_from_text(row_text, table.section, claim_id=next(claim_counter))
            if resource_claim is not None:
                claims.append(resource_claim)
                continue

            manual_only_claim = _manual_only_claim_from_row(
                row,
                row_text=row_text,
                section=table.section,
                claim_id=next(claim_counter),
            )
            if manual_only_claim is not None:
                claims.append(manual_only_claim)

    for paragraph in parsed_report.paragraphs:
        resource_claim = _resource_claim_from_text(
            paragraph.text,
            paragraph.section,
            claim_id=next(claim_counter),
        )
        if resource_claim is not None:
            claims.append(resource_claim)
            continue

        exception_claim = _exception_claim_from_text(
            paragraph.text,
            paragraph.section,
            claim_id=next(claim_counter),
        )
        if exception_claim is not None:
            claims.append(exception_claim)
            continue

        conclusion_claim = _conclusion_claim_from_text(
            paragraph.text,
            paragraph.section,
            claim_id=next(claim_counter),
        )
        if conclusion_claim is not None:
            claims.append(conclusion_claim)

    return ReportClaimsV1(task_id=task_id, claims=_dedupe_claims(claims))


def _build_claim(
    claim_id_num: int,
    *,
    claim_type: str,
    source_section: str | None,
    source_text: str,
    subject: str,
    metric: str | None,
    assertion: str,
    expected_value: str,
    auditability: str,
) -> ReportClaim:
    policy = build_claim_review_policy(
        claim_type=claim_type,
        expected_value=expected_value,
    )
    return ReportClaim(
        claim_id=f"clm_{claim_id_num:03d}",
        claim_type=claim_type,
        source_section=source_section,
        source_text=source_text,
        subject=subject,
        metric=metric,
        assertion=assertion,
        expected_value=expected_value,
        auditability=auditability,
        priority="manual_only" if auditability == "manual_only" else policy.priority,
        evidence_targets=[] if auditability == "manual_only" else list(policy.evidence_targets),
    )


def _resource_claim_from_text(
    text: str,
    section: str | None,
    *,
    claim_id: int,
) -> ReportClaim | None:
    lowered = text.lower()
    metric = None
    if "cpu" in lowered:
        metric = "cpu"
    elif "内存" in text or "memory" in lowered:
        metric = "memory"
    elif "磁盘" in text or "disk" in lowered:
        metric = "disk"
    if metric is None:
        return None

    level = _normalize_resource_level(text, metric=metric)
    if level is None:
        return None

    return _build_claim(
        claim_id,
        claim_type="resource_usage_assessment",
        source_section=section,
        source_text=text,
        subject="host",
        metric=metric,
        assertion="level",
        expected_value=level,
        auditability="direct",
    )


def _resource_claim_from_row(
    row: list[str],
    section: str | None,
    *,
    claim_id: int,
) -> ReportClaim | None:
    if len(row) < 2:
        return None
    row_text = " | ".join(row)
    metric_text = " ".join(cell for cell in row[:2] if cell)
    detail_text = " ".join(cell for cell in row[2:] if cell).strip() or row_text
    metric = _resource_metric_from_text(metric_text)
    if metric is None:
        metric = _resource_metric_from_text(detail_text)
    if metric is None:
        return None

    level = _normalize_resource_level(detail_text, metric=metric)
    if level is None:
        return None

    return _build_claim(
        claim_id,
        claim_type="resource_usage_assessment",
        source_section=section,
        source_text=row_text,
        subject="host",
        metric=metric,
        assertion="level",
        expected_value=level,
        auditability="direct",
    )


def _exception_claim_from_text(
    text: str,
    section: str | None,
    *,
    claim_id: int,
) -> ReportClaim | None:
    if _is_instructional_text(text, section) or _describes_no_exception(text):
        return None

    lowered = text.lower()
    subject = _extract_subject(text, text)
    if any(keyword in text for keyword in ("重启", "失败", "异常", "告警")):
        exception_value = _normalize_exception_value(text)
        if exception_value is not None:
            return _build_claim(
                claim_id,
                claim_type="exception_presence",
                source_section=section,
                source_text=text,
                subject=subject,
                metric=None,
                assertion="exception_present",
                expected_value=exception_value,
                auditability="direct",
            )
    if "原因" in text or "由于" in text or "because" in lowered:
        cause_value = _normalize_cause_value(text)
        return _build_claim(
            claim_id,
            claim_type="exception_cause",
            source_section=section,
            source_text=text,
            subject=subject,
            metric=None,
            assertion="cause",
            expected_value=cause_value,
            auditability="partial",
        )
    return None


def _manual_only_claim_from_row(
    row: list[str],
    *,
    row_text: str,
    section: str | None,
    claim_id: int,
) -> ReportClaim | None:
    if not row:
        return None
    if not any(marker in row_text for marker in MANUAL_ONLY_MARKERS):
        return None

    expected_value = _normalize_manual_result(" ".join(row))
    if expected_value is None:
        return None

    subject = row[1] if len(row) > 1 and row[1].strip() else row[0]
    return _build_claim(
        claim_id,
        claim_type="manual_inspection_assertion",
        source_section=section,
        source_text=row_text,
        subject=subject.strip().lower(),
        metric=None,
        assertion="manual_check",
        expected_value=expected_value,
        auditability="manual_only",
    )


def _conclusion_claim_from_text(
    text: str,
    section: str | None,
    *,
    claim_id: int,
) -> ReportClaim | None:
    target_text = f"{section or ''} {text}"
    if (
        "结论" not in target_text
        and "整体" not in text
        and not _looks_like_summary_conclusion(text)
    ):
        return None

    expected_value = _normalize_overall_conclusion(text)
    if expected_value is None:
        return None
    return _build_claim(
        claim_id,
        claim_type="overall_inspection_conclusion",
        source_section=section,
        source_text=text,
        subject="system",
        metric=None,
        assertion="overall_state",
        expected_value=expected_value,
        auditability="partial",
    )


def _extract_subject(left_text: str, right_text: str) -> str:
    combined = f"{left_text} {right_text}".lower()
    if "产品" in left_text or "waf" in combined and "版本" in combined:
        return "waf"
    if "引擎" in left_text or "引擎" in right_text:
        return "engine"
    if any(token in left_text for token in ("服务状态", "容器状态")):
        return "service"
    if "健康检查" in left_text:
        return "service"
    for keyword in COMPONENT_KEYWORDS:
        if keyword in combined:
            return keyword
    normalized = re.sub(r"(版本|运行状态|服务状态|容器状态|健康检查|健康|状态)", "", left_text)
    normalized = normalized.strip(" ：:-")
    if normalized:
        return normalized.lower()
    return "host"


def _first_version(text: str) -> str | None:
    match = VERSION_RE.search(text)
    if match is None:
        return None
    return match.group(0).lstrip("v")


def _normalize_runtime_status(text: str) -> str | None:
    lowered = text.lower()
    if "重启" in text or "restarting" in lowered:
        return "restarting"
    if "失败" in text or "异常" in text or "failed" in lowered:
        return "failed"
    if "停止" in text or "stopped" in lowered:
        return "stopped"
    if "正常" in text or "运行" in text or "running" in lowered:
        return "running"
    return None


def _normalize_health_status(text: str) -> str | None:
    lowered = text.lower()
    if "异常" in text or "失败" in text or "告警" in text or "unhealthy" in lowered:
        return "unhealthy"
    if "正常" in text or "healthy" in lowered:
        return "healthy"
    return None


def _resource_metric_from_text(text: str) -> str | None:
    lowered = text.lower()
    if "cpu" in lowered:
        return "cpu"
    if "内存" in text or "memory" in lowered:
        return "memory"
    if "磁盘" in text or "disk" in lowered or "硬盘" in text:
        return "disk"
    return None


def _normalize_resource_level(text: str, *, metric: str | None = None) -> str | None:
    lowered = text.lower()
    percent = _extract_resource_percent(text)

    # Prefer obvious numeric overload first so the document's own data can drive review.
    if percent is not None and metric is not None:
        numeric_level = _resource_level_from_percent(metric, percent)
        if numeric_level in {"high", "critical"}:
            return numeric_level

    if any(marker in text for marker in ("无异常", "无异常值", "未见异常", "未发现异常")):
        return "normal"
    if any(marker in text for marker in ("稳定", "平稳", "空间充足", "符合预期", "正常生成")):
        return "normal"
    if "严重" in text or "critical" in lowered:
        return "critical"
    if "偏高" in text or "较高" in text or "高" in text or "异常" in text:
        return "high"
    if "正常" in text or "稳定" in text:
        return "normal"
    if percent is not None and metric is not None:
        return _resource_level_from_percent(metric, percent)
    return None


def _extract_resource_percent(text: str) -> float | None:
    matches = PERCENT_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def _resource_level_from_percent(metric: str, percent: float) -> str:
    thresholds = {
        "cpu": (95.0, 85.0),
        "memory": (90.0, 80.0),
        "disk": (90.0, 80.0),
    }
    critical_threshold, high_threshold = thresholds.get(metric, (95.0, 85.0))
    if percent >= critical_threshold:
        return "critical"
    if percent >= high_threshold:
        return "high"
    return "normal"


def _normalize_exception_value(text: str) -> str | None:
    lowered = text.lower()
    if _describes_no_exception(text):
        return None
    if "重启" in text or "restarting" in lowered:
        return "restart"
    if "磁盘" in text and ("高" in text or "满" in text):
        return "disk_high"
    if "健康" in text and ("失败" in text or "异常" in text):
        return "health_fail"
    if "oom" in lowered or "内存溢出" in text:
        return "oom"
    if "错误" in text or "error" in lowered or "异常" in text:
        return "error"
    return None


def _normalize_cause_value(text: str) -> str:
    lowered = text.lower()
    if "磁盘" in text and ("高" in text or "满" in text):
        return "disk_high"
    if "oom" in lowered or "内存" in text:
        return "oom"
    if "依赖" in text or "connection refused" in lowered:
        return "dependency_fail"
    if "配置" in text:
        return "config_issue"
    return "unknown"


def _normalize_overall_conclusion(text: str) -> str | None:
    lowered = text.lower()
    if _describes_no_exception(text) or any(marker in text for marker in HEALTHY_SUMMARY_MARKERS):
        return "healthy"
    if any(marker in text for marker in WARNING_SUMMARY_MARKERS) or "warning" in lowered:
        return "warning"
    if any(marker in text for marker in ABNORMAL_SUMMARY_MARKERS) or "abnormal" in lowered:
        return "abnormal"
    if "异常" in text or "风险" in text or "告警" in text:
        return "abnormal"
    if "正常" in text or "稳定" in text or "healthy" in lowered:
        return "healthy"
    return None


def _normalize_manual_result(text: str) -> str | None:
    if "正常" in text:
        return "normal"
    if "异常" in text:
        return "abnormal"
    if "未涉及" in text:
        return "not_applicable"
    return None


def _is_instructional_text(text: str, section: str | None) -> bool:
    target = f"{section or ''} {text}"
    return any(marker in target for marker in INSTRUCTIONAL_TEXT_MARKERS)


def _describes_no_exception(text: str) -> bool:
    return any(marker in text for marker in NO_EXCEPTION_PATTERNS)


def _looks_like_summary_conclusion(text: str) -> bool:
    return _describes_no_exception(text) or any(marker in text for marker in HEALTHY_SUMMARY_MARKERS + WARNING_SUMMARY_MARKERS + ABNORMAL_SUMMARY_MARKERS)


def _dedupe_claims(claims: list[ReportClaim]) -> list[ReportClaim]:
    deduped: list[ReportClaim] = []
    seen_keys: set[tuple[str, str, str | None, str]] = set()
    for claim in claims:
        key = (claim.claim_type, claim.subject, claim.metric, claim.expected_value)
        if key in seen_keys:
            continue
        deduped.append(claim)
        seen_keys.add(key)
    return deduped
