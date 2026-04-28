from pathlib import Path

from app.core.config import get_settings


def test_get_settings_reads_values_from_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_PORT=8011",
                "ANALYZER_MODE=remote",
                "REPORT_RENDERING_ENABLED=true",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", env_file.as_posix())
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("REPORT_RENDERING_ENABLED", raising=False)

    settings = get_settings()

    assert settings.app_port == 8011
    assert settings.report_rendering_enabled is True


def test_shell_env_overrides_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_PORT=8011",
                "REPORT_RENDERING_ENABLED=false",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", env_file.as_posix())
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("REPORT_RENDERING_ENABLED", "true")

    settings = get_settings()

    assert settings.app_port == 9001
    assert settings.report_rendering_enabled is True
