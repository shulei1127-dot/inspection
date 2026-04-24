from __future__ import annotations

import json
from json import JSONDecodeError
from datetime import UTC, datetime
from pathlib import Path
import re
import shutil
import tarfile
import uuid
import zipfile

import httpx
from fastapi import UploadFile
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.audit_result import AuditResultV1
from app.schemas.log_evidence import LogEvidenceV1
from app.schemas.log_evidence import (
    DerivedSummary,
    LogFinding,
    ResourceSignal,
    RuntimeComponentEvidence,
)
from app.schemas.report_claims import ReportClaimsV1
from app.schemas.status_analysis import (
    StatusAnalysisEvidenceV1,
    StatusAnalysisKeyFinding,
    StatusAnalysisMetricSnapshot,
    StatusAnalysisStabilityEvent,
    StatusAnalysisSummaryV1,
)
from app.schemas.waf_audits import (
    WafAuditCreateData,
    WafAuditError,
    WafAuditResultData,
    WafAuditSummary,
)
from app.services.audit_opinion_renderer import render_audit_opinion_markdown
from app.services.audit_review_service import review_report_claims
from app.services.manual_report_parser import ManualReportParseError, parse_manual_report
from app.services.report_augmenter import (
    ReportAugmentError,
    augment_report_with_audit_appendix,
)
from app.services.report_claim_normalizer import normalize_report_claims
from app.services.waf_preprocessing_task_service import (
    WafPreprocessingTaskError,
    get_waf_preprocessing_result,
)
from app.services.waf_audit_repository import (
    WafAuditTaskRecord,
    create_waf_audit_task_record,
    get_waf_audit_task_record,
    list_waf_audit_task_records,
    update_waf_audit_task_record,
)


SUPPORTED_LOG_ARCHIVE_MESSAGE = "Only .zip, .tar.gz, .tgz, and .gz log archives are accepted."
WAF_AUDIT_TASK_ID_PREFIX = "waf_audit"
DOCKER_STATS_LINE_RE = re.compile(
    r"^(?P<container_id>\S+)\s+"
    r"(?P<name>\S+)\s+"
    r"(?P<cpu>\d+(?:\.\d+)?)%\s+"
    r"(?P<mem_usage>\S+)\s*/\s*(?P<mem_limit>\S+)\s+"
    r"(?P<mem_pct>\d+(?:\.\d+)?)%"
)


class WafAuditTaskError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class WafAuditLookupError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}

    def to_error(self) -> WafAuditError:
        return WafAuditError(
            code=self.code,
            message=self.message,
            details=self.details,
        )


def create_waf_audit_from_upload(
    report_upload: UploadFile | None,
    log_upload: UploadFile | None,
    *,
    report_lang: str = "zh-CN",
) -> WafAuditCreateData:
    del report_lang  # phase 1 keeps one fixed markdown output language

    if report_upload is None or not (report_upload.filename or ""):
        raise WafAuditTaskError(
            status_code=400,
            code="missing_file",
            message="No manual report file was provided.",
        )
    if log_upload is None or not (log_upload.filename or ""):
        raise WafAuditTaskError(
            status_code=400,
            code="missing_file",
            message="No log archive file was provided.",
        )

    log_suffix = _detect_log_archive_suffix(log_upload.filename or "")
    if log_suffix is None:
        raise WafAuditTaskError(
            status_code=415,
            code="unsupported_media_type",
            message=SUPPORTED_LOG_ARCHIVE_MESSAGE,
            details={"filename": log_upload.filename or ""},
        )

    settings = get_settings()
    task_id = _generate_waf_audit_task_id()
    report_upload_path = settings.uploads_dir / f"{task_id}_report.docx"
    log_archive_path = settings.uploads_dir / f"{task_id}_logs{log_suffix}"
    task_workdir = settings.workdir_dir / task_id
    extracted_dir = task_workdir / "extracted"
    report_claims_path = task_workdir / "report_claims.json"
    log_evidence_path = task_workdir / "log_evidence.json"
    audit_result_path = task_workdir / "audit_result.json"
    audit_opinion_path = settings.outputs_dir / task_id / "audit_opinion.md"
    audit_augmented_report_path = settings.outputs_dir / task_id / "audit_augmented_report.docx"

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    create_waf_audit_task_record(
        task_id=task_id,
        status="parsing_report",
        report_upload_path=report_upload_path.as_posix(),
        log_archive_path=log_archive_path.as_posix(),
        workdir_path=task_workdir.as_posix(),
    )

    try:
        _save_upload(report_upload, report_upload_path)
        _save_upload(log_upload, log_archive_path)
        _validate_docx_file(report_upload_path, report_upload.filename or "")
        _validate_archive_file(log_archive_path, log_upload.filename or "", archive_suffix=log_suffix)
        _extract_archive(log_archive_path, extracted_dir, log_upload.filename or "", archive_suffix=log_suffix)

        parsed_report = parse_manual_report(report_upload_path)
        report_claims = normalize_report_claims(parsed_report, task_id=task_id)
        _persist_model(report_claims, report_claims_path)

        update_waf_audit_task_record(task_id, status="extracting_evidence")
        log_evidence = extract_waf_log_evidence(
            task_id=task_id,
            extracted_dir=extracted_dir,
            archive_name=log_upload.filename or None,
            archive_size_bytes=log_archive_path.stat().st_size,
        )
        _persist_model(log_evidence, log_evidence_path)

        update_waf_audit_task_record(task_id, status="reviewing")
        audit_result = review_report_claims(report_claims, log_evidence)
        _persist_model(audit_result, audit_result_path)

        audit_opinion_path.parent.mkdir(parents=True, exist_ok=True)
        audit_opinion_path.write_text(
            render_audit_opinion_markdown(audit_result, log_evidence=log_evidence),
            encoding="utf-8",
        )
        augment_report_with_audit_appendix(
            report_upload_path,
            audit_result=audit_result,
            log_evidence=log_evidence,
            output_path=audit_augmented_report_path,
        )

        update_waf_audit_task_record(
            task_id,
            status="completed",
            audit_opinion_path=audit_opinion_path.as_posix(),
            error_code=None,
            error_message=None,
            error_details=None,
        )
    except WafAuditTaskError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code=exc.code,
            error_message=exc.message,
            error_details=json.dumps(exc.details, ensure_ascii=False),
        )
        raise
    except ManualReportParseError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code="report_parse_failed",
            error_message=str(exc),
            error_details=json.dumps({"task_id": task_id}, ensure_ascii=False),
        )
        raise WafAuditTaskError(
            status_code=400,
            code="report_parse_failed",
            message=str(exc),
            details={"task_id": task_id},
        ) from exc
    except ReportAugmentError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code="report_augment_failed",
            error_message=str(exc),
            error_details=json.dumps({"task_id": task_id}, ensure_ascii=False),
        )
        raise WafAuditTaskError(
            status_code=500,
            code="report_augment_failed",
            message=str(exc),
            details={"task_id": task_id},
        ) from exc

    summary = _summary_from_audit_result(audit_result)
    return WafAuditCreateData(
        task_id=task_id,
        status="completed",
        report_file_path=report_upload_path.as_posix(),
        log_file_path=log_archive_path.as_posix(),
        preprocessing_id=None,
        report_claims_path=report_claims_path.as_posix(),
        log_evidence_path=log_evidence_path.as_posix(),
        audit_result_path=audit_result_path.as_posix(),
        audit_opinion_path=audit_opinion_path.as_posix(),
        audit_augmented_report_path=audit_augmented_report_path.as_posix(),
        summary=summary,
    )


def create_waf_audit_from_preprocessing(
    report_upload: UploadFile | None,
    preprocessing_id: str,
    *,
    report_lang: str = "zh-CN",
) -> WafAuditCreateData:
    del report_lang  # phase 1 keeps one fixed markdown output language

    if report_upload is None or not (report_upload.filename or ""):
        raise WafAuditTaskError(
            status_code=400,
            code="missing_file",
            message="No manual report file was provided.",
        )
    if not preprocessing_id.strip():
        raise WafAuditTaskError(
            status_code=400,
            code="missing_preprocessing_id",
            message="No WAF preprocessing_id was provided.",
        )

    try:
        preprocessing_result = get_waf_preprocessing_result(preprocessing_id)
    except WafPreprocessingTaskError as exc:
        raise WafAuditTaskError(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ) from exc

    settings = get_settings()
    task_id = _generate_waf_audit_task_id()
    report_upload_path = settings.uploads_dir / f"{task_id}_report.docx"
    task_workdir = settings.workdir_dir / task_id
    report_claims_path = task_workdir / "report_claims.json"
    log_evidence_path = task_workdir / "log_evidence.json"
    audit_result_path = task_workdir / "audit_result.json"
    audit_opinion_path = settings.outputs_dir / task_id / "audit_opinion.md"
    audit_augmented_report_path = settings.outputs_dir / task_id / "audit_augmented_report.docx"

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    task_workdir.mkdir(parents=True, exist_ok=True)
    create_waf_audit_task_record(
        task_id=task_id,
        status="parsing_report",
        report_upload_path=report_upload_path.as_posix(),
        log_archive_path=None,
        preprocessing_id=preprocessing_result.preprocessing_id,
        workdir_path=task_workdir.as_posix(),
    )

    try:
        _save_upload(report_upload, report_upload_path)
        _validate_docx_file(report_upload_path, report_upload.filename or "")

        parsed_report = parse_manual_report(report_upload_path)
        report_claims = normalize_report_claims(parsed_report, task_id=task_id)
        _persist_model(report_claims, report_claims_path)

        update_waf_audit_task_record(task_id, status="extracting_evidence")
        log_evidence = _build_log_evidence_from_preprocessing(
            task_id=task_id,
            preprocessing_id=preprocessing_result.preprocessing_id,
            summary_path=Path(preprocessing_result.status_analysis_summary_path),
            evidence_path=Path(preprocessing_result.status_analysis_evidence_path),
            source_directory_path=Path(preprocessing_result.source_directory_path),
        )
        _persist_model(log_evidence, log_evidence_path)

        update_waf_audit_task_record(task_id, status="reviewing")
        audit_result = review_report_claims(report_claims, log_evidence)
        _persist_model(audit_result, audit_result_path)

        audit_opinion_path.parent.mkdir(parents=True, exist_ok=True)
        audit_opinion_path.write_text(
            render_audit_opinion_markdown(audit_result, log_evidence=log_evidence),
            encoding="utf-8",
        )
        augment_report_with_audit_appendix(
            report_upload_path,
            audit_result=audit_result,
            log_evidence=log_evidence,
            output_path=audit_augmented_report_path,
        )

        update_waf_audit_task_record(
            task_id,
            status="completed",
            audit_opinion_path=audit_opinion_path.as_posix(),
            error_code=None,
            error_message=None,
            error_details=None,
        )
    except WafAuditTaskError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code=exc.code,
            error_message=exc.message,
            error_details=json.dumps(exc.details, ensure_ascii=False),
        )
        raise
    except ManualReportParseError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code="report_parse_failed",
            error_message=str(exc),
            error_details=json.dumps({"task_id": task_id}, ensure_ascii=False),
        )
        raise WafAuditTaskError(
            status_code=400,
            code="report_parse_failed",
            message=str(exc),
            details={"task_id": task_id},
        ) from exc
    except ReportAugmentError as exc:
        update_waf_audit_task_record(
            task_id,
            status="failed",
            error_code="report_augment_failed",
            error_message=str(exc),
            error_details=json.dumps({"task_id": task_id}, ensure_ascii=False),
        )
        raise WafAuditTaskError(
            status_code=500,
            code="report_augment_failed",
            message=str(exc),
            details={"task_id": task_id},
        ) from exc

    summary = _summary_from_audit_result(audit_result)
    return WafAuditCreateData(
        task_id=task_id,
        status="completed",
        report_file_path=report_upload_path.as_posix(),
        log_file_path=None,
        preprocessing_id=preprocessing_result.preprocessing_id,
        report_claims_path=report_claims_path.as_posix(),
        log_evidence_path=log_evidence_path.as_posix(),
        audit_result_path=audit_result_path.as_posix(),
        audit_opinion_path=audit_opinion_path.as_posix(),
        audit_augmented_report_path=audit_augmented_report_path.as_posix(),
        summary=summary,
    )


def list_waf_audit_results() -> list[WafAuditResultData]:
    return [_record_to_result(record) for record in list_waf_audit_task_records()]


def get_waf_audit_result(task_id: str) -> WafAuditResultData:
    record = get_waf_audit_task_record(task_id)
    if record is None:
        raise WafAuditLookupError(
            status_code=404,
            code="task_not_found",
            message="WAF audit task does not exist.",
            details={"task_id": task_id},
        )
    return _record_to_result(record)


def get_waf_report_claims(task_id: str) -> ReportClaimsV1:
    paths = _resolve_paths(task_id)
    try:
        return ReportClaimsV1.model_validate_json(paths["report_claims_path"].read_text(encoding="utf-8"))
    except OSError as exc:
        raise WafAuditLookupError(
            status_code=404,
            code="claims_not_found",
            message="Report claims artifact does not exist.",
            details={"task_id": task_id},
        ) from exc


def get_waf_audit_structured_result(task_id: str) -> AuditResultV1:
    paths = _resolve_paths(task_id)
    try:
        return AuditResultV1.model_validate_json(paths["audit_result_path"].read_text(encoding="utf-8"))
    except OSError as exc:
        raise WafAuditLookupError(
            status_code=404,
            code="audit_result_not_found",
            message="Structured audit result does not exist.",
            details={"task_id": task_id},
        ) from exc


def get_waf_audit_opinion_path(task_id: str) -> Path:
    paths = _resolve_paths(task_id)
    if not paths["audit_opinion_path"].exists():
        raise WafAuditLookupError(
            status_code=404,
            code="audit_opinion_not_found",
            message="Audit opinion file does not exist.",
            details={"task_id": task_id},
        )
    return paths["audit_opinion_path"]


def get_waf_audit_augmented_report_path(task_id: str) -> Path:
    paths = _resolve_paths(task_id)
    if not paths["audit_augmented_report_path"].exists():
        raise WafAuditLookupError(
            status_code=404,
            code="audit_augmented_report_not_found",
            message="Audit augmented report file does not exist.",
            details={"task_id": task_id},
        )
    return paths["audit_augmented_report_path"]


def extract_waf_log_evidence(
    *,
    task_id: str,
    extracted_dir: Path,
    archive_name: str | None,
    archive_size_bytes: int | None,
) -> LogEvidenceV1:
    settings = get_settings()
    request_body = {
        "request_version": "waf-evidence-request/v1",
        "task_id": task_id,
        "source": {
            "type": "directory",
            "path": extracted_dir.resolve().as_posix(),
        },
        "archive_name": archive_name,
        "archive_size_bytes": archive_size_bytes,
    }
    timeout = httpx.Timeout(settings.analyzer_timeout_seconds)
    base_url = settings.analyzer_base_url.rstrip("/")

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/waf-evidence", json=request_body)
    except httpx.HTTPError as exc:
        raise WafAuditTaskError(
            status_code=503,
            code="log_extract_failed",
            message="Failed to reach the WAF evidence extractor service.",
            details={"analyzer_base_url": settings.analyzer_base_url},
        ) from exc

    if response.status_code != 200:
        raise _waf_evidence_error_from_response(response, base_url=base_url)

    try:
        payload = response.json()
    except ValueError as exc:
        raise WafAuditTaskError(
            status_code=503,
            code="log_extract_failed",
            message="WAF evidence extractor returned an invalid response.",
            details={"analyzer_base_url": settings.analyzer_base_url},
        ) from exc

    try:
        return LogEvidenceV1.model_validate(payload["result"])
    except (KeyError, ValidationError) as exc:
        raise WafAuditTaskError(
            status_code=503,
            code="log_extract_failed",
            message="WAF evidence extractor response did not match the expected contract.",
            details={"analyzer_base_url": settings.analyzer_base_url},
        ) from exc


def _build_log_evidence_from_preprocessing(
    *,
    task_id: str,
    preprocessing_id: str,
    summary_path: Path,
    evidence_path: Path,
    source_directory_path: Path | None = None,
) -> LogEvidenceV1:
    try:
        summary = StatusAnalysisSummaryV1.model_validate_json(summary_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WafAuditTaskError(
            status_code=404,
            code="preprocessing_artifact_not_found",
            message="WAF preprocessing summary artifact does not exist.",
            details={"preprocessing_id": preprocessing_id, "path": summary_path.as_posix()},
        ) from exc
    except (JSONDecodeError, ValidationError) as exc:
        raise WafAuditTaskError(
            status_code=400,
            code="invalid_preprocessing_artifact",
            message="WAF preprocessing summary artifact is invalid.",
            details={"preprocessing_id": preprocessing_id, "path": summary_path.as_posix()},
        ) from exc

    evidence = _load_status_analysis_evidence(evidence_path)
    resource_signals = [
        _resource_signal_from_snapshot(snapshot)
        for snapshot in [summary.cpu_snapshot, summary.memory_snapshot, summary.disk_snapshot]
        if snapshot is not None
    ]
    key_findings = summary.service_findings + summary.container_findings + summary.system_findings
    runtime_components = [
        _runtime_component_from_key_finding(finding)
        for finding in key_findings
        if finding.component
    ]
    log_findings = [
        _log_finding_from_key_finding(index, finding)
        for index, finding in enumerate(key_findings, start=1)
    ]
    log_findings.extend(
        _log_finding_from_stability_event(index, event)
        for index, event in enumerate(summary.recent_stability_events, start=len(log_findings) + 1)
    )
    if source_directory_path is not None:
        container_components, container_signals, container_findings = _extract_container_stats_evidence(
            source_directory_path
        )
        runtime_components = container_components + runtime_components
        resource_signals.extend(container_signals)
        log_findings.extend(container_findings)

    high_resource_items = [
        f"{signal.subject}:{signal.metric}:{signal.level}"
        for signal in resource_signals
        if signal.level in {"high", "critical"}
    ]
    abnormal_component_count = sum(
        component.status in {"failed", "restarting", "stopped"} or component.health == "unhealthy"
        for component in runtime_components
    )
    key_risks = [finding.summary for finding in log_findings if finding.severity in {"high", "medium"}][:5]
    coverage_warnings = list(summary.coverage_warnings) + list(summary.warnings)
    if evidence is not None:
        coverage_warnings.extend(evidence.warnings)
        coverage_warnings.extend(evidence.scan_coverage.warnings)

    if key_risks or high_resource_items or abnormal_component_count:
        overall_runtime_state = "abnormal"
    elif summary.coverage_level == "minimal":
        overall_runtime_state = "unknown"
    else:
        overall_runtime_state = "normal"

    if coverage_warnings:
        log_findings.append(
            LogFinding(
                finding_id="prep_coverage_001",
                finding_type="error_log",
                subject="preprocessing_coverage",
                severity="medium",
                summary="清洗覆盖存在限制，部分报告结论可能只能给出证据不足。",
                evidence_text="; ".join(dict.fromkeys(coverage_warnings))[:800],
                source_refs=[summary_path.as_posix()],
            )
        )

    return LogEvidenceV1(
        task_id=task_id,
        product_version=summary.metadata.product_version,
        host_hostname=summary.metadata.host_hostname,
        runtime_components=runtime_components,
        resource_signals=resource_signals,
        log_findings=log_findings,
        derived_summary=DerivedSummary(
            overall_runtime_state=overall_runtime_state,
            abnormal_component_count=abnormal_component_count,
            high_resource_items=high_resource_items,
            key_risks=key_risks,
        ),
    )


def _extract_container_stats_evidence(
    source_directory_path: Path,
) -> tuple[list[RuntimeComponentEvidence], list[ResourceSignal], list[LogFinding]]:
    stats_path = source_directory_path / "container" / "docker_stats.txt"
    if not stats_path.exists():
        return [], [], []

    try:
        lines = stats_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return [], [], []

    components: list[RuntimeComponentEvidence] = []
    signals: list[ResourceSignal] = []
    findings: list[LogFinding] = []
    for index, line in enumerate(lines, start=1):
        match = DOCKER_STATS_LINE_RE.match(line.strip())
        if match is None:
            continue
        name = match.group("name")
        cpu_value = float(match.group("cpu"))
        mem_value = float(match.group("mem_pct"))
        mem_usage = match.group("mem_usage")
        mem_limit = match.group("mem_limit")
        source_ref = "container/docker_stats.txt"
        evidence_text = (
            f"CPU {cpu_value:.1f}% ; 内存 {mem_value:.1f}% "
            f"({mem_usage} / {mem_limit})"
        )
        components.append(
            RuntimeComponentEvidence(
                component_name=name,
                source_type="container",
                status="running",
                health="unknown",
                restart_signal=False,
                evidence_text=evidence_text,
                source_refs=[source_ref],
            )
        )
        signals.extend(
            [
                ResourceSignal(
                    scope="container",
                    subject=name,
                    metric="cpu",
                    observed_value=cpu_value,
                    unit="percent",
                    level=_resource_level("cpu", cpu_value),
                    threshold_hit=cpu_value >= 85.0,
                    raw_text=line.strip(),
                    source_refs=[source_ref],
                ),
                ResourceSignal(
                    scope="container",
                    subject=name,
                    metric="memory",
                    observed_value=mem_value,
                    unit="percent",
                    level=_resource_level("memory", mem_value),
                    threshold_hit=mem_value >= 80.0,
                    raw_text=line.strip(),
                    source_refs=[source_ref],
                ),
            ]
        )
        if cpu_value >= 85.0:
            findings.append(
                LogFinding(
                    finding_id=f"prep_container_cpu_{index:03d}",
                    finding_type="error_log",
                    subject=name,
                    severity="high" if cpu_value >= 95.0 else "medium",
                    summary=f"容器 {name} CPU 使用率偏高（{cpu_value:.1f}%）",
                    evidence_text=line.strip(),
                    source_refs=[source_ref],
                )
            )
        if mem_value >= 80.0:
            findings.append(
                LogFinding(
                    finding_id=f"prep_container_mem_{index:03d}",
                    finding_type="error_log",
                    subject=name,
                    severity="high" if mem_value >= 90.0 else "medium",
                    summary=f"容器 {name} 内存使用率偏高（{mem_value:.1f}%）",
                    evidence_text=line.strip(),
                    source_refs=[source_ref],
                )
            )
    return components, signals, findings


def _load_status_analysis_evidence(evidence_path: Path) -> StatusAnalysisEvidenceV1 | None:
    try:
        return StatusAnalysisEvidenceV1.model_validate_json(evidence_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValidationError):
        return None


def _resource_signal_from_snapshot(snapshot: StatusAnalysisMetricSnapshot) -> ResourceSignal:
    level = _resource_level(snapshot.metric, snapshot.current_value)
    return ResourceSignal(
        scope="host",
        subject="host",
        metric=snapshot.metric,  # type: ignore[arg-type]
        observed_value=snapshot.current_value,
        unit=snapshot.unit,
        level=level,
        threshold_hit=level in {"high", "critical"},
        raw_text=snapshot.source_excerpt or snapshot.note or f"{snapshot.metric}={snapshot.current_value}{snapshot.unit}",
        source_refs=[snapshot.source_ref] if snapshot.source_ref else [],
    )


def _resource_level(metric: str, value: float | None) -> str:
    if value is None:
        return "unknown"
    critical_threshold = 95.0 if metric == "cpu" else 90.0
    high_threshold = 85.0 if metric == "cpu" else 80.0
    if value >= critical_threshold:
        return "critical"
    if value >= high_threshold:
        return "high"
    return "normal"


def _runtime_component_from_key_finding(finding: StatusAnalysisKeyFinding) -> RuntimeComponentEvidence:
    status = "failed" if finding.severity == "high" else "unknown"
    health = "unhealthy" if finding.severity in {"high", "medium"} else "unknown"
    return RuntimeComponentEvidence(
        component_name=finding.component or finding.category,
        source_type=finding.category,
        status=status,  # type: ignore[arg-type]
        health=health,  # type: ignore[arg-type]
        restart_signal="重启" in finding.summary or "restart" in finding.summary.lower(),
        evidence_text=finding.summary,
        source_refs=[finding.source_ref],
    )


def _log_finding_from_key_finding(index: int, finding: StatusAnalysisKeyFinding) -> LogFinding:
    return LogFinding(
        finding_id=f"prep_finding_{index:03d}",
        finding_type=_finding_type_from_text(finding.summary),
        subject=finding.component or finding.category,
        severity=finding.severity,
        summary=finding.summary,
        evidence_text=finding.summary,
        source_refs=[finding.source_ref],
    )


def _log_finding_from_stability_event(index: int, event: StatusAnalysisStabilityEvent) -> LogFinding:
    finding_type = "restart" if event.event_type == "restart" else "error_log"
    return LogFinding(
        finding_id=f"prep_stability_{index:03d}",
        finding_type=finding_type,  # type: ignore[arg-type]
        subject=event.component or event.event_type,
        severity=event.severity,
        summary=event.summary,
        evidence_text=event.summary,
        source_refs=[event.source_ref],
    )


def _finding_type_from_text(text: str) -> str:
    lowered = text.lower()
    if "oom" in lowered:
        return "oom"
    if "restart" in lowered or "重启" in text:
        return "restart"
    if "disk" in lowered or "磁盘" in text:
        return "disk_high"
    return "error_log"


def _waf_evidence_error_from_response(
    response: httpx.Response,
    *,
    base_url: str,
) -> WafAuditTaskError:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        return WafAuditTaskError(
            status_code=503,
            code=str(error.get("code") or "log_extract_failed"),
            message=str(error.get("message") or "WAF evidence extraction failed."),
            details={
                **dict(error.get("details") or {}),
                "analyzer_base_url": base_url,
            },
        )

    return WafAuditTaskError(
        status_code=503,
        code="log_extract_failed",
        message="WAF evidence extractor returned a non-success response.",
        details={
            "analyzer_base_url": base_url,
            "status_code": response.status_code,
        },
    )


def _record_to_result(record: WafAuditTaskRecord) -> WafAuditResultData:
    paths = _resolve_paths(record.task_id, record=record)
    return WafAuditResultData(
        task_id=record.task_id,
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,
        report_file_path=paths["report_upload_path"].as_posix() if paths["report_upload_path"].exists() else None,
        log_file_path=paths["log_archive_path"].as_posix() if paths["log_archive_path"].exists() else None,
        preprocessing_id=record.preprocessing_id,
        report_claims_path=paths["report_claims_path"].as_posix() if paths["report_claims_path"].exists() else None,
        log_evidence_path=paths["log_evidence_path"].as_posix() if paths["log_evidence_path"].exists() else None,
        audit_result_path=paths["audit_result_path"].as_posix() if paths["audit_result_path"].exists() else None,
        audit_opinion_path=paths["audit_opinion_path"].as_posix() if paths["audit_opinion_path"].exists() else None,
        audit_augmented_report_path=(
            paths["audit_augmented_report_path"].as_posix()
            if paths["audit_augmented_report_path"].exists()
            else None
        ),
        summary=_load_waf_audit_summary(paths["audit_result_path"]),
        error=(
            WafAuditError(
                code=record.error_code or "failed",
                message=record.error_message or "WAF audit task failed.",
                details=_deserialize_error_details(record.error_details),
            )
            if record.status == "failed"
            else None
        ),
    )


def _load_waf_audit_summary(audit_result_path: Path) -> WafAuditSummary:
    if not audit_result_path.exists():
        return WafAuditSummary()
    try:
        audit_result = AuditResultV1.model_validate_json(audit_result_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, ValidationError):
        return WafAuditSummary()
    return _summary_from_audit_result(audit_result)


def _summary_from_audit_result(audit_result: AuditResultV1) -> WafAuditSummary:
    return WafAuditSummary(
        claim_count=len(audit_result.claim_results),
        confirmed_count=audit_result.summary.confirmed_count,
        conflict_count=audit_result.summary.conflict_count,
    )


def _resolve_paths(
    task_id: str,
    *,
    record: WafAuditTaskRecord | None = None,
) -> dict[str, Path]:
    settings = get_settings()
    workdir_path = Path(record.workdir_path) if record and record.workdir_path else settings.workdir_dir / task_id
    report_upload_path = Path(record.report_upload_path) if record and record.report_upload_path else settings.uploads_dir / f"{task_id}_report.docx"
    log_archive_path = Path(record.log_archive_path) if record and record.log_archive_path else _find_log_archive_path(task_id)
    audit_opinion_path = Path(record.audit_opinion_path) if record and record.audit_opinion_path else settings.outputs_dir / task_id / "audit_opinion.md"
    audit_augmented_report_path = settings.outputs_dir / task_id / "audit_augmented_report.docx"
    return {
        "report_upload_path": report_upload_path,
        "log_archive_path": log_archive_path,
        "workdir_path": workdir_path,
        "report_claims_path": workdir_path / "report_claims.json",
        "log_evidence_path": workdir_path / "log_evidence.json",
        "audit_result_path": workdir_path / "audit_result.json",
        "audit_opinion_path": audit_opinion_path,
        "audit_augmented_report_path": audit_augmented_report_path,
    }


def _find_log_archive_path(task_id: str) -> Path:
    settings = get_settings()
    for suffix in [".tar.gz", ".tgz", ".zip", ".gz"]:
        candidate = settings.uploads_dir / f"{task_id}_logs{suffix}"
        if candidate.exists():
            return candidate
    return settings.uploads_dir / f"{task_id}_logs.tar.gz"


def _detect_log_archive_suffix(filename: str) -> str | None:
    lowered = filename.lower()
    for suffix in (".tar.gz", ".tgz", ".zip", ".gz"):
        if lowered.endswith(suffix):
            return suffix
    return None


def _generate_waf_audit_task_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{WAF_AUDIT_TASK_ID_PREFIX}_{timestamp}_{suffix}"


def _save_upload(upload: UploadFile, target_path: Path) -> None:
    upload.file.seek(0)
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    upload.file.seek(0)


def _validate_docx_file(report_path: Path, filename: str) -> None:
    if report_path.suffix.lower() != ".docx" or not zipfile.is_zipfile(report_path):
        raise WafAuditTaskError(
            status_code=400,
            code="invalid_report_file",
            message="The uploaded report file is not a valid .docx document.",
            details={"filename": filename},
        )


def _validate_archive_file(
    archive_path: Path,
    filename: str,
    *,
    archive_suffix: str,
) -> None:
    if archive_suffix == ".zip":
        if not zipfile.is_zipfile(archive_path):
            raise WafAuditTaskError(
                status_code=400,
                code="invalid_archive",
                message="The uploaded log archive is not valid.",
                details={"filename": filename},
            )
        return
    if not tarfile.is_tarfile(archive_path):
        raise WafAuditTaskError(
            status_code=400,
            code="invalid_archive",
            message="The uploaded log archive is not valid.",
            details={"filename": filename},
        )


def _extract_archive(
    archive_path: Path,
    target_dir: Path,
    filename: str,
    *,
    archive_suffix: str,
) -> None:
    root = target_dir.resolve()
    try:
        if archive_suffix == ".zip":
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    destination = (target_dir / member.filename).resolve()
                    if destination != root and root not in destination.parents:
                        raise WafAuditTaskError(
                            status_code=500,
                            code="extract_failed",
                            message="Failed to extract the uploaded log archive.",
                            details={"filename": filename, "reason": "unsafe_archive_path"},
                        )
                archive.extractall(target_dir)
            return

        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                destination = (target_dir / member.name).resolve()
                if destination != root and root not in destination.parents:
                    raise WafAuditTaskError(
                        status_code=500,
                        code="extract_failed",
                        message="Failed to extract the uploaded log archive.",
                        details={"filename": filename, "reason": "unsafe_archive_path"},
                    )
            archive.extractall(target_dir, filter="data")
    except WafAuditTaskError:
        raise
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        raise WafAuditTaskError(
            status_code=500,
            code="extract_failed",
            message="Failed to extract the uploaded log archive.",
            details={"filename": filename, "reason": str(exc)},
        ) from exc


def _persist_model(model, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def _deserialize_error_details(raw_details: str | None) -> dict[str, str | int | float | bool | None]:
    if not raw_details:
        return {}
    try:
        payload = json.loads(raw_details)
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload
