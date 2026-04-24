from pathlib import Path

from app.schemas.unified_json import UnifiedJsonV1
from app.services.report_template_selector import (
    extract_product_type_from_unified_json,
    resolve_report_template_path_for_product_type,
    resolve_report_template_path_for_unified_json_file,
)


def test_template_selector_resolves_xray_and_unknown_to_current_product_templates() -> None:
    xray_template = resolve_report_template_path_for_product_type("xray")
    unknown_template = resolve_report_template_path_for_product_type("unknown")

    assert xray_template == Path("templates/xray_inspection_report.docx")
    assert unknown_template == Path("templates/inspection_report.docx")


def test_template_selector_reads_product_type_from_unified_json_file(tmp_path: Path) -> None:
    unified_json = UnifiedJsonV1.model_validate(
        {
            "schema_version": "unified-json/v1",
            "task_id": "tsk_template_selector_001",
            "generated_at": "2026-04-14T06:00:00Z",
            "source": {
                "archive_name": "xray.tar.gz",
                "archive_size_bytes": 123,
                "collected_at": None,
            },
            "parser": {"name": "xray-collector-parser", "version": "0.1.0"},
            "host_info": {"hostname": "host-a"},
            "summary": {
                "overall_status": "healthy",
                "service_count": 0,
                "service_running_count": 0,
                "container_count": 0,
                "container_running_count": 0,
                "issue_count": 0,
                "issue_by_severity": {
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "info": 0,
                },
            },
            "services": [],
            "containers": [],
            "issues": [],
            "warnings": [],
            "metadata": {
                "product_type": "xray",
            },
        }
    )
    unified_json_path = tmp_path / "unified.json"
    unified_json_path.write_text(
        unified_json.model_dump_json(indent=2),
        encoding="utf-8",
    )

    assert extract_product_type_from_unified_json(unified_json) == "xray"
    assert resolve_report_template_path_for_unified_json_file(unified_json_path) == Path(
        "templates/xray_inspection_report.docx"
    )


def test_template_selector_falls_back_to_unknown_for_missing_or_invalid_product_type(
    tmp_path: Path,
) -> None:
    unified_json_path = tmp_path / "invalid.json"
    unified_json_path.write_text("{not-json", encoding="utf-8")

    assert resolve_report_template_path_for_unified_json_file(unified_json_path) == Path(
        "templates/inspection_report.docx"
    )
