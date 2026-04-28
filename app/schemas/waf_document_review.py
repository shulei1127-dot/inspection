from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WafDocumentResourceClaim(BaseModel):
    metric: Literal["cpu", "memory", "disk"]
    reported_percent: float | None = None
    report_judgement: str
    source_text: str


class WafDocumentAbnormalTopic(BaseModel):
    topic: str
    title: str
    evidence: str
    source_section: str | None = None


class WafMatchedHelpDoc(BaseModel):
    title: str
    snippet: str
    source_path: str


class WafDocumentReviewInputV1(BaseModel):
    schema_version: Literal["waf-document-review-input/v1"] = "waf-document-review-input/v1"
    task_id: str
    review_mode: Literal["document_only"] = "document_only"
    resource_claims: list[WafDocumentResourceClaim] = Field(default_factory=list)
    abnormal_topics: list[WafDocumentAbnormalTopic] = Field(default_factory=list)
    matched_help_docs: list[WafMatchedHelpDoc] = Field(default_factory=list)


class WafDocumentExceptionAction(BaseModel):
    problem: str
    evidence: str
    action: str


class WafDocumentReviewResultV1(BaseModel):
    schema_version: Literal["waf-document-review/v1"] = "waf-document-review/v1"
    task_id: str
    review_mode: Literal["document_only"] = "document_only"
    llm_status: str
    llm_model: str | None = None
    llm_error: str | None = None
    disclaimer: str
    exception_actions: list[WafDocumentExceptionAction] = Field(default_factory=list)
    inspection_summary: str
