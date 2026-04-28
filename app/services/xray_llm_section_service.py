from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.report_payload import ReportPayloadV1
from app.schemas.unified_json import UnifiedJsonV1


class XrayExceptionAction(BaseModel):
    problem: str
    action: str


class XrayLlmSectionPayload(BaseModel):
    inspection_summary: str
    exception_summary: str
    exception_actions: list[XrayExceptionAction]


@dataclass(frozen=True)
class XrayLlmSectionResult:
    success: bool
    status: str
    model: str | None = None
    error: str | None = None
    payload: XrayLlmSectionPayload | None = None


class XrayLlmSectionService(Protocol):
    def generate(
        self,
        *,
        unified_json: UnifiedJsonV1,
        report_payload: ReportPayloadV1,
    ) -> XrayLlmSectionResult: ...


@dataclass(frozen=True)
class DisabledXrayLlmSectionService:
    def generate(
        self,
        *,
        unified_json: UnifiedJsonV1,  # noqa: ARG002
        report_payload: ReportPayloadV1,  # noqa: ARG002
    ) -> XrayLlmSectionResult:
        return XrayLlmSectionResult(success=False, status="disabled")


@dataclass(frozen=True)
class RemoteXrayLlmSectionService:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    temperature: float
    transport: httpx.BaseTransport | None = None

    def generate(
        self,
        *,
        unified_json: UnifiedJsonV1,
        report_payload: ReportPayloadV1,
    ) -> XrayLlmSectionResult:
        if not _is_xray_product(unified_json):
            return XrayLlmSectionResult(success=False, status="not_xray", model=self.model)

        request_payload = _build_xray_llm_input(
            unified_json=unified_json,
            report_payload=report_payload,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是中文正式巡检报告撰写助手。"
                    "你只能基于输入事实生成内容，不得虚构版本号、IP、机器码、健康状态、资源百分比、容器状态或服务状态。"
                    "你不得修改事实，只能组织为正式巡检报告语言。"
                    "如果证据不足，必须明确写“需进一步核查”。"
                    "输出必须是严格 JSON，不要附加解释、代码块或多余文本。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请基于以下 x-ray 巡检事实生成两类内容：\n"
                    "1. inspection_summary：用于报告最后的巡检总结，120到220字。\n"
                    "2. exception_summary：用于异常情况总述，80到180字。\n"
                    "3. exception_actions：最多3项，每项包含 problem 和 action。\n"
                    "要求：\n"
                    "- 使用正式、克制、可交付的中文巡检报告语气。\n"
                    "- problem 应直接概括异常情况，不要写成命令。\n"
                    "- action 应写成建议处置操作，可以包含 docker logs、docker stats、free -h、minion 日志等具体排查动作，但只能围绕输入事实。\n"
                    "- 不要输出表格。\n"
                    "- 不要出现“我认为”“推测”“模型”等字样。\n"
                    "- 如果输入异常不足3项，只输出实际需要的项。\n\n"
                    f"输入事实 JSON：\n{json.dumps(request_payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ]

        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        timeout = httpx.Timeout(self.timeout_seconds)

        try:
            with httpx.Client(timeout=timeout, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.TimeoutException:
            return XrayLlmSectionResult(
                success=False,
                status="timeout",
                model=self.model,
                error="xray_llm_timeout",
            )
        except httpx.HTTPError:
            return XrayLlmSectionResult(
                success=False,
                status="unavailable",
                model=self.model,
                error="xray_llm_unavailable",
            )

        if response.status_code != 200:
            return XrayLlmSectionResult(
                success=False,
                status="provider_error",
                model=self.model,
                error=f"xray_llm_http_{response.status_code}",
            )

        try:
            response_json = response.json()
            content = _extract_chat_content(response_json)
            decoded = _decode_model_json(content)
            payload = XrayLlmSectionPayload.model_validate(decoded)
        except (ValueError, TypeError, ValidationError):
            return XrayLlmSectionResult(
                success=False,
                status="invalid_output",
                model=self.model,
                error="xray_llm_invalid_output",
            )

        return XrayLlmSectionResult(
            success=True,
            status="ok",
            model=self.model,
            payload=payload,
        )


def maybe_apply_xray_llm_sections(
    report_payload: ReportPayloadV1,
    *,
    unified_json: UnifiedJsonV1,
    service: XrayLlmSectionService | None = None,
) -> XrayLlmSectionResult:
    _ensure_xray_llm_defaults(report_payload)

    if not _is_xray_product(unified_json):
        return XrayLlmSectionResult(success=False, status="not_xray")

    resolved_service = service or build_xray_llm_section_service()
    result = resolved_service.generate(unified_json=unified_json, report_payload=report_payload)
    appendix = report_payload.appendix
    appendix["xray_llm_status"] = result.status
    appendix["xray_llm_model"] = result.model or "-"
    appendix["xray_llm_error"] = result.error or "-"

    if not result.success or result.payload is None:
        _sync_exception_display_lines(report_payload)
        return result

    payload = result.payload
    appendix["xray_llm_inspection_summary"] = payload.inspection_summary
    appendix["xray_llm_exception_summary"] = payload.exception_summary
    appendix["xray_llm_disposal_advice"] = "\n".join(
        f"{index + 1}. {action.problem}：{action.action}"
        for index, action in enumerate(payload.exception_actions)
    ) or "-"
    appendix["xray_result_conclusion"] = payload.inspection_summary

    for index, action in enumerate(payload.exception_actions[:3], start=1):
        appendix[f"xray_issue_{index}_problem"] = action.problem
        appendix[f"xray_issue_{index}_recommendation"] = action.action

    _sync_exception_display_lines(report_payload)
    return result


def build_xray_llm_section_service(
    *,
    transport: httpx.BaseTransport | None = None,
) -> XrayLlmSectionService:
    settings = get_settings()
    if (
        not settings.xray_llm_section_enabled
        or settings.xray_llm_section_mode != "remote_api"
        or not settings.xray_llm_section_base_url
        or not settings.xray_llm_section_api_key
        or not settings.xray_llm_section_model
    ):
        return DisabledXrayLlmSectionService()

    return RemoteXrayLlmSectionService(
        base_url=settings.xray_llm_section_base_url,
        api_key=settings.xray_llm_section_api_key,
        model=settings.xray_llm_section_model,
        timeout_seconds=settings.xray_llm_section_timeout_seconds,
        temperature=settings.xray_llm_section_temperature,
        transport=transport,
    )


def _ensure_xray_llm_defaults(report_payload: ReportPayloadV1) -> None:
    appendix = report_payload.appendix
    appendix.setdefault("xray_llm_inspection_summary", str(appendix.get("xray_result_conclusion") or "-"))
    appendix.setdefault("xray_llm_exception_summary", str(appendix.get("xray_key_alerts") or "-"))
    default_disposal_advice = "\n".join(
        f"{index + 1}. {appendix.get(f'xray_issue_{index + 1}_problem') or '-'}："
        f"{appendix.get(f'xray_issue_{index + 1}_recommendation') or '-'}"
        for index in range(3)
        if appendix.get(f"xray_issue_{index + 1}_problem")
        and appendix.get(f"xray_issue_{index + 1}_problem") != "-"
    )
    appendix.setdefault("xray_llm_disposal_advice", default_disposal_advice or "-")
    appendix.setdefault("xray_llm_status", "disabled")
    appendix.setdefault("xray_llm_model", "-")
    appendix.setdefault("xray_llm_error", "-")
    _sync_exception_display_lines(report_payload)


def _sync_exception_display_lines(report_payload: ReportPayloadV1) -> None:
    appendix = report_payload.appendix
    for index in range(1, 4):
        problem = str(appendix.get(f"xray_issue_{index}_problem") or "").strip()
        evidence = str(appendix.get(f"xray_issue_{index}_evidence") or "").strip()
        action = str(appendix.get(f"xray_issue_{index}_recommendation") or "").strip()
        appendix[f"xray_display_issue_{index}_problem_line"] = (
            f"问题 {index}：{problem}" if problem and problem != "-" else ""
        )
        appendix[f"xray_display_issue_{index}_evidence_line"] = (
            f"证据：{evidence if evidence and evidence != '-' else '-'}"
            if problem and problem != "-"
            else ""
        )
        appendix[f"xray_display_issue_{index}_action_line"] = (
            f"建议：{action}" if action and action != "-" else ""
        )


def _build_xray_llm_input(
    *,
    unified_json: UnifiedJsonV1,
    report_payload: ReportPayloadV1,
) -> dict[str, object]:
    appendix = report_payload.appendix
    return {
        "product_type": "xray",
        "overall_status": report_payload.summary.overall_status_label,
        "executive_status": appendix.get("xray_executive_status"),
        "primary_problem": appendix.get("xray_primary_problem"),
        "key_alerts": [
            value
            for value in [
                appendix.get("xray_key_alerts"),
                appendix.get("xray_runtime_status_note"),
            ]
            if isinstance(value, str) and value and value != "-"
        ],
        "resource_signals": {
            "mgmt_cpu": appendix.get("xray_mgmt_cpu"),
            "mgmt_memory": appendix.get("xray_mgmt_memory"),
            "mgmt_disk": appendix.get("xray_mgmt_disk"),
            "engine_cpu": appendix.get("xray_engine_cpu"),
            "engine_memory": appendix.get("xray_engine_memory"),
            "engine_disk": appendix.get("xray_engine_disk"),
        },
        "health_checks": {
            "mgmt": {
                "result": appendix.get("xray_mgmt_health_result"),
                "note": appendix.get("xray_mgmt_health_note"),
            },
            "engine": {
                "result": appendix.get("xray_engine_health_result"),
                "note": appendix.get("xray_engine_health_note"),
            },
        },
        "top_issue_rows": [
            {
                "title": issue.title,
                "description": issue.description,
                "suggestion": issue.suggestion,
            }
            for issue in report_payload.issue_rows[:3]
        ],
        "container_rows": [
            {
                "name": row.name,
                "status": row.status_label,
                "cpu_percent": row.cpu_percent,
                "memory_percent": row.memory_percent,
                "notes": row.notes,
            }
            for row in report_payload.container_rows[:5]
        ],
        "service_rows": [
            {
                "name": row.name,
                "status": row.status_label,
                "notes": row.notes,
            }
            for row in report_payload.service_rows[:5]
        ],
        "rule_based_recommendations": report_payload.recommendations[:5],
        "host_info": {
            "hostname": unified_json.host_info.hostname,
            "ip": unified_json.host_info.ip,
        },
    }


def _extract_chat_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    message = choices[0]
    if not isinstance(message, dict):
        raise ValueError("invalid choice")
    message_payload = message.get("message")
    if not isinstance(message_payload, dict):
        raise ValueError("missing message")
    content = message_payload.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
        if texts:
            return "\n".join(texts).strip()
    raise ValueError("missing content")


def _decode_model_json(content: str) -> dict[str, object]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("invalid json") from None
        decoded = json.loads(text[start : end + 1])

    if not isinstance(decoded, dict):
        raise ValueError("json root must be object")
    return decoded


def _is_xray_product(unified_json: UnifiedJsonV1) -> bool:
    return str(unified_json.metadata.get("product_type")).strip().lower() == "xray"
