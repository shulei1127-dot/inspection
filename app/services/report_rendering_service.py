import base64
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.report_payload import ReportPayloadV1
from app.services.report_template_selector import (
    resolve_report_template_path_for_unified_json_file,
)
from app.services.xray_trend_service import maybe_run_xray_trend_enhancement


class ReportRenderingError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ReportRenderResult:
    attempted: bool
    success: bool
    output_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None
    details: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    renderer: str | None = None


class ReportRendererAdapter(Protocol):
    def render(
        self,
        *,
        template_path: Path,
        report_payload: ReportPayloadV1,
        output_path: Path,
    ) -> None: ...


class HttpCarboneAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        carbone_version: str,
        api_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.carbone_version = carbone_version
        self.api_token = api_token

    def render(
        self,
        *,
        template_path: Path,
        report_payload: ReportPayloadV1,
        output_path: Path,
    ) -> None:
        headers = {
            "content-type": "application/json",
            "carbone-version": self.carbone_version,
        }
        if self.api_token:
            headers["authorization"] = f"Bearer {self.api_token}"

        timeout = httpx.Timeout(self.timeout_seconds)

        try:
            with httpx.Client(timeout=timeout) as client:
                status_response = client.get(
                    f"{self.base_url}/status",
                    headers=_status_headers(headers),
                )
        except httpx.HTTPError as exc:
            raise ReportRenderingError(
                code="carbone_unreachable",
                message="Failed to reach the Carbone runtime.",
                details={"carbone_base_url": self.base_url},
            ) from exc

        if status_response.status_code != 200:
            raise ReportRenderingError(
                code="carbone_status_failed",
                message="Carbone runtime health check failed.",
                details={
                    "carbone_base_url": self.base_url,
                    "status_code": status_response.status_code,
                },
            )

        request_body = {
            "data": report_payload.model_dump(mode="json"),
            "template": base64.b64encode(template_path.read_bytes()).decode("ascii"),
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                render_response = client.post(
                    f"{self.base_url}/render/template?download=true",
                    headers=headers,
                    json=request_body,
                )
        except httpx.HTTPError as exc:
            raise ReportRenderingError(
                code="carbone_unreachable",
                message="Failed to reach the Carbone runtime during render.",
                details={"carbone_base_url": self.base_url},
            ) from exc

        if render_response.status_code != 200:
            raise ReportRenderingError(
                code="carbone_render_failed",
                message="Carbone render request failed.",
                details={
                    "carbone_base_url": self.base_url,
                    "status_code": render_response.status_code,
                    "response_excerpt": render_response.text[:300] or None,
                },
            )

        if not render_response.content:
            raise ReportRenderingError(
                code="carbone_render_failed",
                message="Carbone returned an empty rendered document.",
                details={"carbone_base_url": self.base_url},
            )

        output_path.write_bytes(render_response.content)


def maybe_render_report_from_payload_file(
    task_id: str,
    report_payload_path: Path,
    *,
    enabled: bool | None = None,
    template_path: Path | None = None,
    output_path: Path | None = None,
    adapter: ReportRendererAdapter | None = None,
) -> ReportRenderResult:
    settings = get_settings()
    render_enabled = settings.report_rendering_enabled if enabled is None else enabled

    if not render_enabled:
        return ReportRenderResult(attempted=False, success=False)

    resolved_adapter = adapter or build_report_renderer_adapter()

    try:
        rendered_output_path = render_report_from_payload_file(
            task_id,
            report_payload_path,
            template_path=template_path,
            output_path=output_path,
            adapter=resolved_adapter,
        )
    except ReportRenderingError as exc:
        return ReportRenderResult(
            attempted=True,
            success=False,
            error_code=exc.code,
            error_message=exc.message,
            details=exc.details,
            renderer=type(resolved_adapter).__name__,
        )

    details: dict[str, str | int | float | bool | None] = {}
    try:
        xray_trend_artifacts = maybe_run_xray_trend_enhancement(
            task_id,
            base_report_docx_path=rendered_output_path,
        )
    except Exception as exc:  # pragma: no cover - non-blocking post-render guard
        details["xray_trend_status"] = "skipped_after_error"
        details["xray_trend_error"] = str(exc)
    else:
        if xray_trend_artifacts is not None:
            details.update(
                {
                    "xray_trend_status": (
                        "augmented"
                        if xray_trend_artifacts.augmented_report_path is not None
                        else "artifacts_only"
                    ),
                    "xray_trend_input_path": xray_trend_artifacts.trend_input_path,
                    "xray_trend_assessment_path": xray_trend_artifacts.trend_assessment_path,
                    "xray_trend_summary_path": xray_trend_artifacts.trend_summary_path,
                    "xray_trend_resource_history_path": xray_trend_artifacts.resource_history_path,
                    "xray_trend_chart_count": len(xray_trend_artifacts.chart_paths),
                    "xray_trend_augmented_report_path": xray_trend_artifacts.augmented_report_path,
                }
            )

    return ReportRenderResult(
        attempted=True,
        success=True,
        output_path=rendered_output_path,
        details=details,
        renderer=type(resolved_adapter).__name__,
    )


def render_report_from_payload_file(
    task_id: str,
    report_payload_path: Path,
    *,
    template_path: Path | None = None,
    output_path: Path | None = None,
    adapter: ReportRendererAdapter | None = None,
) -> Path:
    report_payload = _load_report_payload(report_payload_path)

    settings = get_settings()
    resolved_template_path = template_path or settings.default_report_template_path
    if not resolved_template_path.exists():
        raise ReportRenderingError(
            code="template_missing",
            message="Report template file does not exist.",
            details={"template_path": resolved_template_path.as_posix()},
        )

    resolved_output_path = output_path or settings.outputs_dir / task_id / "report.docx"
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_adapter = adapter or build_report_renderer_adapter()
    resolved_adapter.render(
        template_path=resolved_template_path,
        report_payload=report_payload,
        output_path=resolved_output_path,
    )

    return resolved_output_path


def build_report_renderer_adapter() -> ReportRendererAdapter:
    settings = get_settings()
    return HttpCarboneAdapter(
        base_url=settings.carbone_base_url,
        timeout_seconds=settings.carbone_api_timeout_seconds,
        carbone_version=settings.carbone_version,
        api_token=settings.carbone_api_token,
    )


def render_task_report(task_id: str) -> ReportRenderResult:
    settings = get_settings()
    report_payload_path = settings.workdir_dir / task_id / "report_payload.json"
    unified_json_path = settings.workdir_dir / task_id / "unified.json"

    return maybe_render_report_from_payload_file(
        task_id,
        report_payload_path,
        enabled=True,
        template_path=resolve_report_template_path_for_unified_json_file(unified_json_path),
        output_path=settings.outputs_dir / task_id / "report.docx",
    )


def _load_report_payload(report_payload_path: Path) -> ReportPayloadV1:
    if not report_payload_path.exists():
        raise ReportRenderingError(
            code="report_payload_missing",
            message="Report payload file does not exist.",
            details={"report_payload_path": report_payload_path.as_posix()},
        )

    try:
        return ReportPayloadV1.model_validate_json(
            report_payload_path.read_text(encoding="utf-8")
        )
    except (OSError, JSONDecodeError, ValidationError) as exc:
        raise ReportRenderingError(
            code="invalid_report_payload",
            message="Report payload file is invalid or cannot be parsed.",
            details={"report_payload_path": report_payload_path.as_posix()},
        ) from exc


def _status_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key != "content-type"}
