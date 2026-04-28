from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from app.core.config import get_settings
from app.schemas.report_claims import ReportClaim, ReportClaimsV1
from app.schemas.waf_document_review import (
    WafDocumentAbnormalTopic,
    WafDocumentExceptionAction,
    WafDocumentResourceClaim,
    WafDocumentReviewInputV1,
    WafDocumentReviewResultV1,
    WafMatchedHelpDoc,
)
from app.services.waf_llm_review_service import (
    WafLlmReviewResult,
    WafLlmReviewService,
    build_waf_llm_review_service,
)


DISCLAIMER = "以下建议基于巡检文档内容整理，未结合原始日志做一致性核验。"
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")

TOPIC_KEYWORDS = {
    "cpu_high": ("cpu", "负载", "占用", "高"),
    "memory_high": ("内存", "memory", "占用", "高"),
    "disk_high": ("磁盘", "disk", "空间", "满"),
    "service_failed": ("服务", "failed", "失败", "异常"),
    "container_failed": ("容器", "container", "失败", "异常"),
    "container_unhealthy": ("容器", "健康", "unhealthy", "异常"),
    "restart": ("重启", "restarting", "restart"),
    "oom": ("oom", "内存溢出", "out of memory"),
}


@dataclass(frozen=True)
class _HelpDocCandidate:
    title: str
    content: str
    source_path: str


def build_waf_document_review_input(
    report_claims: ReportClaimsV1,
) -> WafDocumentReviewInputV1:
    resource_claims: list[WafDocumentResourceClaim] = []
    abnormal_topics: list[WafDocumentAbnormalTopic] = []

    for claim in report_claims.claims:
        resource_claim = _resource_claim_from_report_claim(claim)
        if resource_claim is not None:
            resource_claims.append(resource_claim)
            if claim.expected_value in {"high", "critical"}:
                abnormal_topics.append(
                    WafDocumentAbnormalTopic(
                        topic=f"{claim.metric}_high",
                        title=_resource_problem_title(claim.metric or "", resource_claim.reported_percent),
                        evidence=claim.source_text,
                        source_section=claim.source_section,
                    )
                )
            continue

        abnormal_topic = _abnormal_topic_from_report_claim(claim)
        if abnormal_topic is not None:
            abnormal_topics.append(abnormal_topic)

    deduped_topics = _dedupe_topics(abnormal_topics)
    matched_help_docs = _match_help_docs(deduped_topics)

    return WafDocumentReviewInputV1(
        task_id=report_claims.task_id,
        resource_claims=resource_claims,
        abnormal_topics=deduped_topics,
        matched_help_docs=matched_help_docs,
    )


def generate_waf_document_review(
    review_input: WafDocumentReviewInputV1,
    *,
    llm_service: WafLlmReviewService | None = None,
) -> WafDocumentReviewResultV1:
    resolved_service = llm_service or build_waf_llm_review_service()
    llm_result = resolved_service.generate(review_input=review_input)
    if llm_result.success and llm_result.payload is not None:
        return WafDocumentReviewResultV1(
            task_id=review_input.task_id,
            llm_status=llm_result.status,
            llm_model=llm_result.model,
            llm_error=llm_result.error,
            disclaimer=DISCLAIMER,
            exception_actions=llm_result.payload.exception_actions,
            inspection_summary=llm_result.payload.inspection_summary,
        )

    fallback_actions = _build_fallback_actions(review_input)
    return WafDocumentReviewResultV1(
        task_id=review_input.task_id,
        llm_status=llm_result.status,
        llm_model=llm_result.model,
        llm_error=llm_result.error,
        disclaimer=DISCLAIMER,
        exception_actions=fallback_actions,
        inspection_summary=_build_fallback_summary(review_input, fallback_actions),
    )


def render_waf_document_review_markdown(
    result: WafDocumentReviewResultV1,
) -> str:
    lines = [
        "# 雷池 WAF 文档直审意见",
        "",
        result.disclaimer,
        "",
        "## 异常情况及处置操作",
    ]

    if result.exception_actions:
        for index, action in enumerate(result.exception_actions, start=1):
            lines.extend(
                [
                    "",
                    f"问题 {index}：{action.problem}",
                    f"证据：{action.evidence}",
                    f"建议：{action.action}",
                ]
            )
    else:
        lines.extend(
            [
                "",
                "当前文档未识别到明确异常项，建议结合运行日志和现场状态进一步核查。",
            ]
        )

    lines.extend(
        [
            "",
            "## 巡检总结",
            result.inspection_summary,
            "",
        ]
    )
    return "\n".join(lines)


def _resource_claim_from_report_claim(claim: ReportClaim) -> WafDocumentResourceClaim | None:
    if claim.claim_type != "resource_usage_assessment" or claim.metric not in {"cpu", "memory", "disk"}:
        return None
    return WafDocumentResourceClaim(
        metric=claim.metric,
        reported_percent=_extract_percent(claim.source_text),
        report_judgement=claim.expected_value,
        source_text=claim.source_text,
    )


def _abnormal_topic_from_report_claim(claim: ReportClaim) -> WafDocumentAbnormalTopic | None:
    if claim.claim_type == "component_runtime_status" and claim.expected_value != "running":
        return WafDocumentAbnormalTopic(
            topic="container_failed" if "容器" in claim.source_text or "container" in claim.source_text.lower() else "service_failed",
            title=_runtime_problem_title(claim),
            evidence=claim.source_text,
            source_section=claim.source_section,
        )
    if claim.claim_type == "component_health_status" and claim.expected_value == "unhealthy":
        return WafDocumentAbnormalTopic(
            topic="container_unhealthy" if "容器" in claim.source_text or "container" in claim.source_text.lower() else "service_failed",
            title=f"{claim.subject} 健康状态异常",
            evidence=claim.source_text,
            source_section=claim.source_section,
        )
    if claim.claim_type == "exception_presence":
        topic = _topic_from_exception_value(claim.expected_value)
        return WafDocumentAbnormalTopic(
            topic=topic,
            title=_exception_problem_title(claim),
            evidence=claim.source_text,
            source_section=claim.source_section,
        )
    return None


def _runtime_problem_title(claim: ReportClaim) -> str:
    subject = claim.subject or "相关组件"
    status_map = {
        "restarting": "反复重启",
        "failed": "运行失败",
        "stopped": "未运行",
    }
    status_text = status_map.get(claim.expected_value, "运行状态异常")
    return f"{subject} {status_text}"


def _exception_problem_title(claim: ReportClaim) -> str:
    mapping = {
        "restart": "存在重启异常",
        "disk_high": "磁盘使用率偏高",
        "health_fail": "健康检查异常",
        "oom": "存在内存溢出风险",
        "error": "存在异常运行告警",
    }
    return mapping.get(claim.expected_value, claim.source_text)


def _resource_problem_title(metric: str, percent: float | None) -> str:
    label = {
        "cpu": "CPU使用率",
        "memory": "内存使用率",
        "disk": "磁盘使用率",
    }.get(metric, metric)
    if percent is None:
        return f"{label}偏高"
    return f"{label}达到{percent:.0f}%"


def _topic_from_exception_value(value: str) -> str:
    return {
        "restart": "restart",
        "disk_high": "disk_high",
        "health_fail": "service_failed",
        "oom": "oom",
        "error": "service_failed",
    }.get(value, "service_failed")


def _extract_percent(text: str) -> float | None:
    matches = PERCENT_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def _dedupe_topics(topics: list[WafDocumentAbnormalTopic]) -> list[WafDocumentAbnormalTopic]:
    deduped: list[WafDocumentAbnormalTopic] = []
    seen: set[tuple[str, str]] = set()
    for topic in topics:
        key = (topic.topic, topic.title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(topic)
    return deduped


def _match_help_docs(topics: list[WafDocumentAbnormalTopic]) -> list[WafMatchedHelpDoc]:
    settings = get_settings()
    help_docs_dir = settings.waf_help_docs_dir
    if not help_docs_dir.exists():
        return []

    keywords: set[str] = set()
    for topic in topics:
        keywords.update(TOPIC_KEYWORDS.get(topic.topic, ()))
        keywords.update(_tokenize_keywords(topic.title))

    candidates: list[tuple[int, _HelpDocCandidate]] = []
    for path in sorted(help_docs_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        lowered = content.lower()
        score = sum(1 for keyword in keywords if keyword and keyword.lower() in lowered)
        if score <= 0:
            continue
        candidates.append(
            (
                score,
                _HelpDocCandidate(
                    title=path.stem.replace("_", " "),
                    content=content,
                    source_path=path.as_posix(),
                ),
            )
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    matched: list[WafMatchedHelpDoc] = []
    for _, candidate in candidates[:3]:
        matched.append(
            WafMatchedHelpDoc(
                title=candidate.title,
                snippet=_first_help_doc_snippet(candidate.content),
                source_path=candidate.source_path,
            )
        )
    return matched


def _tokenize_keywords(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.split(r"[\s，。；：,.:()（）/-]+", text)
        if len(token.strip()) >= 2
    }


def _first_help_doc_snippet(content: str) -> str:
    for block in re.split(r"\n\s*\n", content):
        normalized = " ".join(block.split())
        if normalized:
            return normalized[:320]
    return content.strip()[:320]


def _build_fallback_actions(
    review_input: WafDocumentReviewInputV1,
) -> list[WafDocumentExceptionAction]:
    help_doc_map = {doc.title: doc for doc in review_input.matched_help_docs}
    actions: list[WafDocumentExceptionAction] = []
    for topic in review_input.abnormal_topics[:3]:
        actions.append(
            WafDocumentExceptionAction(
                problem=topic.title,
                evidence=topic.evidence,
                action=_fallback_action_text(topic, help_doc_map),
            )
        )
    return actions


def _fallback_action_text(
    topic: WafDocumentAbnormalTopic,
    help_doc_map: dict[str, WafMatchedHelpDoc],
) -> str:
    lowered = topic.topic.lower()
    generic = "建议进一步结合运行日志、组件状态和现场环境核查。"
    if lowered == "cpu_high":
        generic = "建议结合 top、容器资源快照和业务流量，核查是否存在持续高负载。"
    elif lowered == "memory_high":
        generic = "建议通过 docker stats 查看容器内存占用，并结合 free -h 核查主机内存整体使用状态。"
    elif lowered == "disk_high":
        generic = "建议优先核查磁盘占用来源，清理无效数据或评估扩容，避免影响业务运行。"
    elif lowered in {"service_failed", "container_failed", "container_unhealthy", "restart"}:
        generic = "建议检查对应服务或容器状态、最近运行日志及依赖组件，确认异常原因并恢复正常运行。"
    elif lowered == "oom":
        generic = "建议结合 OOM 相关日志、容器资源限制和主机内存状态，排查内存溢出原因。"

    if help_doc_map:
        first_doc = next(iter(help_doc_map.values()))
        return f"{generic} 可参考知识片段：{first_doc.snippet[:120]}。"
    return generic


def _build_fallback_summary(
    review_input: WafDocumentReviewInputV1,
    actions: list[WafDocumentExceptionAction],
) -> str:
    if not actions:
        return "根据巡检文档内容，当前未识别到明确异常项，但由于未结合原始日志核验，建议结合运行日志和现场状态进一步确认。"
    titles = "；".join(action.problem for action in actions[:3])
    return (
        f"根据巡检文档内容，当前识别到{len(actions)}项需关注问题，主要包括：{titles}。"
        "上述判断仅基于文档描述，未结合原始日志做一致性核验，建议优先处理已识别异常，并在处置后进一步复核系统运行状态。"
    )
