import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_values() -> dict[str, str]:
    env_file = Path(os.getenv("ENV_FILE", ".env"))
    if not env_file.exists() or not env_file.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip()
        if not normalized_key:
            continue
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        values[normalized_key] = normalized_value
    return values


def _get_env(name: str, default: str, dotenv_values: dict[str, str]) -> str:
    value = os.getenv(name)
    if value is not None:
        return value
    return dotenv_values.get(name, default)


def _get_bool_env(name: str, default: bool, dotenv_values: dict[str, str]) -> bool:
    value = os.getenv(name)
    if value is None:
        dotenv_value = dotenv_values.get(name)
        if dotenv_value is None:
            return default
        value = dotenv_value
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
    xray_llm_section_enabled: bool
    xray_llm_section_mode: str
    xray_llm_section_base_url: str
    xray_llm_section_api_key: str | None
    xray_llm_section_model: str
    xray_llm_section_timeout_seconds: float
    xray_llm_section_temperature: float
    waf_llm_review_enabled: bool
    waf_llm_review_mode: str
    waf_llm_review_base_url: str
    waf_llm_review_api_key: str | None
    waf_llm_review_model: str
    waf_llm_review_timeout_seconds: float
    waf_llm_review_temperature: float
    waf_help_docs_dir: Path
    log_preprocessing_copy_source: bool
    log_preprocessing_large_file_bytes: int
    log_preprocessing_max_excerpt_lines: int
    mermaid_renderer_mode: str
    mermaid_renderer_base_url: str
    mermaid_renderer_timeout_seconds: float
    mermaid_cli_path: str
    mermaid_cli_timeout_seconds: float


def get_settings() -> Settings:
    dotenv_values = _load_dotenv_values()
    templates_dir = Path(_get_env("TEMPLATES_DIR", "templates", dotenv_values))

    return Settings(
        app_name=_get_env("APP_NAME", "inspection-report-platform", dotenv_values),
        app_env=_get_env("APP_ENV", "dev", dotenv_values),
        app_host=_get_env("APP_HOST", "0.0.0.0", dotenv_values),
        app_port=int(_get_env("APP_PORT", "8000", dotenv_values)),
        analyzer_mode=_get_env("ANALYZER_MODE", "remote", dotenv_values).strip().lower(),
        analyzer_base_url=_get_env("ANALYZER_BASE_URL", "http://127.0.0.1:8090", dotenv_values),
        analyzer_timeout_seconds=float(_get_env("ANALYZER_TIMEOUT_SECONDS", "30", dotenv_values)),
        analyzer_retry_count=int(_get_env("ANALYZER_RETRY_COUNT", "0", dotenv_values)),
        tasks_db_path=Path(_get_env("TASKS_DB_PATH", "tasks.sqlite3", dotenv_values)),
        uploads_dir=Path(_get_env("UPLOADS_DIR", "uploads", dotenv_values)),
        workdir_dir=Path(_get_env("WORKDIR_DIR", "workdir", dotenv_values)),
        outputs_dir=Path(_get_env("OUTPUTS_DIR", "outputs", dotenv_values)),
        templates_dir=templates_dir,
        default_report_template_path=Path(
            _get_env(
                "DEFAULT_REPORT_TEMPLATE_PATH",
                (templates_dir / "inspection_report.docx").as_posix(),
                dotenv_values,
            )
        ),
        report_rendering_enabled=_get_bool_env("REPORT_RENDERING_ENABLED", False, dotenv_values),
        carbone_base_url=_get_env("CARBONE_BASE_URL", "http://127.0.0.1:4000", dotenv_values),
        carbone_api_token=_get_env("CARBONE_API_TOKEN", "", dotenv_values) or None,
        carbone_api_timeout_seconds=float(_get_env("CARBONE_API_TIMEOUT_SECONDS", "30", dotenv_values)),
        carbone_version=_get_env("CARBONE_VERSION", "5", dotenv_values),
        xray_trend_enhancement_enabled=_get_bool_env("XRAY_TREND_ENHANCEMENT_ENABLED", True, dotenv_values),
        xray_llm_section_enabled=_get_bool_env("XRAY_LLM_SECTION_ENABLED", False, dotenv_values),
        xray_llm_section_mode=_get_env("XRAY_LLM_SECTION_MODE", "disabled", dotenv_values).strip().lower(),
        xray_llm_section_base_url=_get_env("XRAY_LLM_SECTION_BASE_URL", "", dotenv_values).strip(),
        xray_llm_section_api_key=_get_env("XRAY_LLM_SECTION_API_KEY", "", dotenv_values) or None,
        xray_llm_section_model=_get_env("XRAY_LLM_SECTION_MODEL", "", dotenv_values).strip(),
        xray_llm_section_timeout_seconds=float(
            _get_env("XRAY_LLM_SECTION_TIMEOUT_SECONDS", "30", dotenv_values)
        ),
        xray_llm_section_temperature=float(
            _get_env("XRAY_LLM_SECTION_TEMPERATURE", "0.2", dotenv_values)
        ),
        waf_llm_review_enabled=_get_bool_env("WAF_LLM_REVIEW_ENABLED", False, dotenv_values),
        waf_llm_review_mode=_get_env("WAF_LLM_REVIEW_MODE", "disabled", dotenv_values).strip().lower(),
        waf_llm_review_base_url=_get_env("WAF_LLM_REVIEW_BASE_URL", "", dotenv_values).strip(),
        waf_llm_review_api_key=_get_env("WAF_LLM_REVIEW_API_KEY", "", dotenv_values) or None,
        waf_llm_review_model=_get_env("WAF_LLM_REVIEW_MODEL", "", dotenv_values).strip(),
        waf_llm_review_timeout_seconds=float(
            _get_env("WAF_LLM_REVIEW_TIMEOUT_SECONDS", "30", dotenv_values)
        ),
        waf_llm_review_temperature=float(
            _get_env("WAF_LLM_REVIEW_TEMPERATURE", "0.2", dotenv_values)
        ),
        waf_help_docs_dir=Path(_get_env("WAF_HELP_DOCS_DIR", "docs/help_docs/waf", dotenv_values)),
        log_preprocessing_copy_source=_get_bool_env("LOG_PREPROCESSING_COPY_SOURCE", False, dotenv_values),
        log_preprocessing_large_file_bytes=int(
            _get_env("LOG_PREPROCESSING_LARGE_FILE_BYTES", str(50 * 1024 * 1024), dotenv_values)
        ),
        log_preprocessing_max_excerpt_lines=int(
            _get_env("LOG_PREPROCESSING_MAX_EXCERPT_LINES", "200", dotenv_values)
        ),
        mermaid_renderer_mode=_get_env("MERMAID_RENDERER_MODE", "disabled", dotenv_values).strip().lower(),
        mermaid_renderer_base_url=_get_env("MERMAID_RENDERER_BASE_URL", "http://127.0.0.1:8091", dotenv_values),
        mermaid_renderer_timeout_seconds=float(_get_env("MERMAID_RENDERER_TIMEOUT_SECONDS", "30", dotenv_values)),
        mermaid_cli_path=_get_env("MERMAID_CLI_PATH", "mmdc", dotenv_values),
        mermaid_cli_timeout_seconds=float(_get_env("MERMAID_CLI_TIMEOUT_SECONDS", "30", dotenv_values)),
    )
