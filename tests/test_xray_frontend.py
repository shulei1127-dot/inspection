from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_xray_workbench_page_loads() -> None:
    response = client.get("/xray")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "xray 巡检报告生成" in response.text
    assert 'href="/console"' in response.text
    assert "上传并生成任务" in response.text
    assert "/api/tasks" in response.text
    assert "render-report" in response.text
    assert "/report" in response.text
    assert "task_id" in response.text
    assert "issue_count" in response.text


def test_homepage_links_to_xray_workbench() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/xray"' in response.text
