from pathlib import Path

import httpx

from app.services.mermaid_renderer import (
    DisabledMermaidRenderer,
    LocalCliMermaidRenderer,
    RemoteMermaidRenderer,
    build_mermaid_renderer,
)


def test_disabled_mermaid_renderer_skips_rendering(tmp_path: Path) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")

    result = DisabledMermaidRenderer().render(source_path, target_path)

    assert result.success is False
    assert result.output_path is None
    assert result.reason == "disabled"
    assert not target_path.exists()


def test_local_cli_mermaid_renderer_skips_when_cli_is_missing(tmp_path: Path) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")

    result = LocalCliMermaidRenderer(cli_path="definitely-missing-mmdc").render(source_path, target_path)

    assert result.success is False
    assert result.reason == "cli_not_found"
    assert not target_path.exists()


def test_local_cli_mermaid_renderer_uses_available_cli(tmp_path: Path) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    fake_cli = tmp_path / "fake-mmdc"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")
    fake_cli.write_text(
        """#!/usr/bin/env python3
from pathlib import Path
import sys

output = Path(sys.argv[sys.argv.index("-o") + 1])
output.write_bytes(b"fake-png")
""",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    result = LocalCliMermaidRenderer(cli_path=fake_cli.as_posix()).render(source_path, target_path)

    assert result.success is True
    assert result.output_path == target_path
    assert target_path.read_bytes() == b"fake-png"


def test_remote_mermaid_renderer_sends_source_string_and_saves_png(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")
    captured_payload = {}

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/png"}
        content = b"remote-png"

    def fake_post(url, *, json, timeout):
        captured_payload["url"] = url
        captured_payload["json"] = json
        captured_payload["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    result = RemoteMermaidRenderer(
        base_url="http://renderer.local",
        timeout_seconds=5,
    ).render(source_path, target_path)

    assert result.success is True
    assert result.output_path == target_path
    assert target_path.read_bytes() == b"remote-png"
    assert captured_payload == {
        "url": "http://renderer.local/render",
        "json": {"source": "flowchart LR\n  A --> B\n", "format": "png"},
        "timeout": 5,
    }


def test_remote_mermaid_renderer_fails_softly_on_non_200(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")

    class FakeResponse:
        status_code = 500
        headers = {"content-type": "application/json"}
        content = b'{"error":"boom"}'

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())

    result = RemoteMermaidRenderer(base_url="http://renderer.local").render(source_path, target_path)

    assert result.success is False
    assert result.reason == "remote_non_200"
    assert not target_path.exists()


def test_remote_mermaid_renderer_fails_softly_on_unavailable(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "trend_state_graph.mmd"
    target_path = tmp_path / "trend_state_graph.png"
    source_path.write_text("flowchart LR\n  A --> B\n", encoding="utf-8")

    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "post", fake_post)

    result = RemoteMermaidRenderer(base_url="http://renderer.local").render(source_path, target_path)

    assert result.success is False
    assert result.reason == "remote_unavailable"
    assert not target_path.exists()


def test_build_mermaid_renderer_defaults_to_disabled() -> None:
    renderer = build_mermaid_renderer(
        mode="unexpected",
        cli_path="mmdc",
        cli_timeout_seconds=30,
        remote_base_url="http://renderer.local",
        remote_timeout_seconds=30,
    )

    assert isinstance(renderer, DisabledMermaidRenderer)
