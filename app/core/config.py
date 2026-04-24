import os
from dataclasses import dataclass
from pathlib import Path


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_host: str
    app_port: int
    analyzer_mode: str
    analyzer_base_url: str
    analyzer_timeout_seconds: float
    analyzer_retry_count: int
    tasks_db_path: Path
    uploads_dir: Path
    workdir_dir: Path
    outputs_dir: Path
    templates_dir: Path
    default_report_template_path: Path
    report_rendering_enabled: bool
    carbone_base_url: str
    carbone_api_token: str | None
    carbone_api_timeout_seconds: float
    carbone_version: str
    xray_trend_enhancement_enabled: bool
    log_preprocessing_copy_source: bool
    log_preprocessing_large_file_bytes: int
    log_preprocessing_max_excerpt_lines: int
    mermaid_renderer_mode: str
    mermaid_renderer_base_url: str
    mermaid_renderer_timeout_seconds: float
    mermaid_cli_path: str
    mermaid_cli_timeout_seconds: float


def get_settings() -> Settings:
    templates_dir = Path(os.getenv("TEMPLATES_DIR", "templates"))

    return Settings(
        app_name=os.getenv("APP_NAME", "inspection-report-platform"),
        app_env=os.getenv("APP_ENV", "dev"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        analyzer_mode=os.getenv("ANALYZER_MODE", "remote").strip().lower(),
        analyzer_base_url=os.getenv("ANALYZER_BASE_URL", "http://127.0.0.1:8090"),
        analyzer_timeout_seconds=float(os.getenv("ANALYZER_TIMEOUT_SECONDS", "30")),
        analyzer_retry_count=int(os.getenv("ANALYZER_RETRY_COUNT", "0")),
        tasks_db_path=Path(os.getenv("TASKS_DB_PATH", "tasks.sqlite3")),
        uploads_dir=Path(os.getenv("UPLOADS_DIR", "uploads")),
        workdir_dir=Path(os.getenv("WORKDIR_DIR", "workdir")),
        outputs_dir=Path(os.getenv("OUTPUTS_DIR", "outputs")),
        templates_dir=templates_dir,
        default_report_template_path=Path(
            os.getenv(
                "DEFAULT_REPORT_TEMPLATE_PATH",
                (templates_dir / "inspection_report.docx").as_posix(),
            )
        ),
        report_rendering_enabled=_get_bool_env("REPORT_RENDERING_ENABLED", False),
        carbone_base_url=os.getenv("CARBONE_BASE_URL", "http://127.0.0.1:4000"),
        carbone_api_token=os.getenv("CARBONE_API_TOKEN") or None,
        carbone_api_timeout_seconds=float(os.getenv("CARBONE_API_TIMEOUT_SECONDS", "30")),
        carbone_version=os.getenv("CARBONE_VERSION", "5"),
        xray_trend_enhancement_enabled=_get_bool_env("XRAY_TREND_ENHANCEMENT_ENABLED", True),
        log_preprocessing_copy_source=_get_bool_env("LOG_PREPROCESSING_COPY_SOURCE", False),
        log_preprocessing_large_file_bytes=int(os.getenv("LOG_PREPROCESSING_LARGE_FILE_BYTES", str(50 * 1024 * 1024))),
        log_preprocessing_max_excerpt_lines=int(os.getenv("LOG_PREPROCESSING_MAX_EXCERPT_LINES", "200")),
        mermaid_renderer_mode=os.getenv("MERMAID_RENDERER_MODE", "disabled").strip().lower(),
        mermaid_renderer_base_url=os.getenv("MERMAID_RENDERER_BASE_URL", "http://127.0.0.1:8091"),
        mermaid_renderer_timeout_seconds=float(os.getenv("MERMAID_RENDERER_TIMEOUT_SECONDS", "30")),
        mermaid_cli_path=os.getenv("MERMAID_CLI_PATH", "mmdc"),
        mermaid_cli_timeout_seconds=float(os.getenv("MERMAID_CLI_TIMEOUT_SECONDS", "30")),
    )
