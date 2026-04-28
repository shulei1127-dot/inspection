from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.waf_document_review import (
    WafDocumentExceptionAction,
    WafDocumentReviewInputV1,
)


class WafLlmReviewPayload(BaseModel):
    exception_actions: list[WafDocumentExceptionAction]
    inspection_summary: str


@dataclass(frozen=True)
class WafLlmReviewResult:
    success: bool
    status: str
    model: str | None = None
    error: str | None = None
    payload: WafLlmReviewPayload | None = None


class WafLlmReviewService(Protocol):
    def generate(self, *, review_input: WafDocumentReviewInputV1) -> WafLlmReviewResult: ...


@dataclass(frozen=True)
class DisabledWafLlmReviewService:
    def generate(self, *, review_input: WafDocumentReviewInputV1) -> WafLlmReviewResult:  # noqa: ARG002
        return WafLlmReviewResult(success=False, status="disabled")


@dataclass(frozen=True)
class RemoteWafLlmReviewService:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    temperature: float
    transport: httpx.BaseTransport | None = None

    def generate(self, *, review_input: WafDocumentReviewInputV1) -> WafLlmReviewResult:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是雷池WAF巡检报告的中文文档直审助手。"
                    "你不是日志解析器，也不能宣称已经做了日志核验。"
                    "你只能基于输入事实与命中的知识片段输出结果。"
                    "不得虚构百分比、容器名、服务状态、根因、命令或日志结论。"
                    "如果证据不足，必须明确写“需进一步核查”。"
                    "输出必须是严格 JSON，不要包含解释、代码块或额外文本。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请基于以下 WAF 巡检文档事实，生成：\n"
                    "1. exception_actions：最多3项，每项包含 problem、evidence、action。\n"
                    "2. inspection_summary：120到220字。\n"
                    "要求：\n"
                    "- 当前是 document_only 模式，不能写“经日志核验”“日志显示”。\n"
                    "- 建议优先参考知识片段中的处置思路，若片段不足则给出保守建议。\n"
                    "- 使用正式、克制、可交付的中文巡检报告语气。\n"
                    "- 不要输出表格。\n"
                    "- 如果异常项不足3个，只输出实际需要的项。\n\n"
                    f"输入 JSON：\n{json.dumps(review_input.model_dump(mode='json'), ensure_ascii=False, indent=2)}"
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
            return WafLlmReviewResult(
                success=False,
                status="timeout",
                model=self.model,
                error="waf_llm_timeout",
            )
        except httpx.HTTPError:
            return WafLlmReviewResult(
                success=False,
                status="unavailable",
                model=self.model,
                error="waf_llm_unavailable",
            )

        if response.status_code != 200:
            return WafLlmReviewResult(
                success=False,
                status="provider_error",
                model=self.model,
                error=f"waf_llm_http_{response.status_code}",
            )

        try:
            response_json = response.json()
            content = _extract_chat_content(response_json)
            decoded = _decode_model_json(content)
            payload = WafLlmReviewPayload.model_validate(decoded)
        except (ValueError, TypeError, ValidationError):
            return WafLlmReviewResult(
                success=False,
                status="invalid_output",
                model=self.model,
                error="waf_llm_invalid_output",
            )

        return WafLlmReviewResult(
            success=True,
            status="ok",
            model=self.model,
            payload=payload,
        )


def build_waf_llm_review_service(
    *,
    transport: httpx.BaseTransport | None = None,
) -> WafLlmReviewService:
    settings = get_settings()
    if (
        not settings.waf_llm_review_enabled
        or settings.waf_llm_review_mode != "remote_api"
        or not settings.waf_llm_review_base_url
        or not settings.waf_llm_review_api_key
        or not settings.waf_llm_review_model
    ):
        return DisabledWafLlmReviewService()

    return RemoteWafLlmReviewService(
        base_url=settings.waf_llm_review_base_url,
        api_key=settings.waf_llm_review_api_key,
        model=settings.waf_llm_review_model,
        timeout_seconds=settings.waf_llm_review_timeout_seconds,
        temperature=settings.waf_llm_review_temperature,
        transport=transport,
    )


def _extract_chat_content(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("invalid choice")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("invalid message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("missing content")
    return content.strip()


def _decode_model_json(content: str) -> dict[str, object]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("json object not found")
    return json.loads(raw[start : end + 1])
