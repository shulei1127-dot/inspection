from __future__ import annotations

from json import JSONDecodeError
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.schemas.unified_json import UnifiedJsonV1


PRODUCT_TEMPLATE_FILENAMES = {
    "xray": "xray_inspection_report.docx",
    "unknown": "inspection_report.docx",
}


def normalize_product_type(product_type: str | None) -> str:
    if not product_type:
        return "unknown"

    normalized = product_type.strip().lower()
    if normalized in PRODUCT_TEMPLATE_FILENAMES:
        return normalized
    return "unknown"


def extract_product_type_from_unified_json(unified_json: UnifiedJsonV1) -> str:
    metadata_product_type = unified_json.metadata.get("product_type")
    if isinstance(metadata_product_type, str):
        return normalize_product_type(metadata_product_type)
    return "unknown"


def resolve_report_template_path_for_product_type(
    product_type: str | None,
    *,
    settings: Settings | None = None,
) -> Path:
    resolved_settings = settings or get_settings()
    template_filename = PRODUCT_TEMPLATE_FILENAMES[
        normalize_product_type(product_type)
    ]
    candidate = resolved_settings.templates_dir / template_filename
    if candidate.exists():
        return candidate
    if resolved_settings.default_report_template_path.exists():
        return resolved_settings.default_report_template_path
    return candidate


def resolve_report_template_path_for_unified_json(
    unified_json: UnifiedJsonV1,
    *,
    settings: Settings | None = None,
) -> Path:
    return resolve_report_template_path_for_product_type(
        extract_product_type_from_unified_json(unified_json),
        settings=settings,
    )


def resolve_report_template_path_for_unified_json_file(
    unified_json_path: Path,
    *,
    settings: Settings | None = None,
) -> Path:
    resolved_settings = settings or get_settings()
    try:
        unified_json = UnifiedJsonV1.model_validate_json(
            unified_json_path.read_text(encoding="utf-8")
        )
    except (OSError, JSONDecodeError, ValidationError):
        return resolved_settings.default_report_template_path

    return resolve_report_template_path_for_unified_json(
        unified_json,
        settings=resolved_settings,
    )
