from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import httpx


@dataclass(frozen=True)
class MermaidRenderResult:
    success: bool
    output_path: Path | None = None
    reason: str | None = None


class MermaidRenderer:
    def render(self, source_path: Path, target_path: Path) -> MermaidRenderResult:
        raise NotImplementedError


class DisabledMermaidRenderer(MermaidRenderer):
    def render(self, source_path: Path, target_path: Path) -> MermaidRenderResult:
        return MermaidRenderResult(success=False, reason="disabled")


class LocalCliMermaidRenderer(MermaidRenderer):
    def __init__(self, *, cli_path: str = "mmdc", timeout_seconds: float = 30) -> None:
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds

    def render(self, source_path: Path, target_path: Path) -> MermaidRenderResult:
        if not source_path.exists():
            return MermaidRenderResult(success=False, reason="source_not_found")

        executable = _resolve_cli(self.cli_path)
        if executable is None:
            return MermaidRenderResult(success=False, reason="cli_not_found")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [
                    executable,
                    "-i",
                    source_path.as_posix(),
                    "-o",
                    target_path.as_posix(),
                    "-b",
                    "white",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return MermaidRenderResult(success=False, reason="cli_timeout")
        except OSError:
            return MermaidRenderResult(success=False, reason="cli_execution_failed")

        if result.returncode != 0:
            return MermaidRenderResult(success=False, reason="cli_non_zero_exit")
        if not target_path.exists():
            return MermaidRenderResult(success=False, reason="output_missing")
        return MermaidRenderResult(success=True, output_path=target_path)


class RemoteMermaidRenderer(MermaidRenderer):
    def __init__(self, *, base_url: str, timeout_seconds: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def render(self, source_path: Path, target_path: Path) -> MermaidRenderResult:
        if not source_path.exists():
            return MermaidRenderResult(success=False, reason="source_not_found")

        source = source_path.read_text(encoding="utf-8")
        try:
            response = httpx.post(
                f"{self.base_url}/render",
                json={"source": source, "format": "png"},
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException:
            return MermaidRenderResult(success=False, reason="remote_timeout")
        except httpx.RequestError:
            return MermaidRenderResult(success=False, reason="remote_unavailable")

        if response.status_code != 200:
            return MermaidRenderResult(success=False, reason="remote_non_200")

        content_type = response.headers.get("content-type", "").lower()
        if "image/png" not in content_type:
            return MermaidRenderResult(success=False, reason="remote_invalid_content_type")
        if not response.content:
            return MermaidRenderResult(success=False, reason="remote_empty_response")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(response.content)
        return MermaidRenderResult(success=True, output_path=target_path)


def build_mermaid_renderer(
    *,
    mode: str,
    cli_path: str,
    cli_timeout_seconds: float,
    remote_base_url: str,
    remote_timeout_seconds: float,
) -> MermaidRenderer:
    normalized = mode.strip().lower()
    if normalized == "local_cli":
        return LocalCliMermaidRenderer(cli_path=cli_path, timeout_seconds=cli_timeout_seconds)
    if normalized == "remote":
        return RemoteMermaidRenderer(base_url=remote_base_url, timeout_seconds=remote_timeout_seconds)
    return DisabledMermaidRenderer()


def _resolve_cli(cli_path: str) -> str | None:
    candidate = cli_path.strip()
    if not candidate:
        return None
    if "/" in candidate:
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path.as_posix()
        return None
    return shutil.which(candidate)
