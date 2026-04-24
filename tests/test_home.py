from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_homepage() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "inspection-report-platform" in response.text
    assert 'href="/docs"' in response.text
    assert 'href="/console"' in response.text
    assert 'href="/xray"' in response.text
    assert 'href="/waf"' in response.text
    assert 'href="/waf-audits/ui"' in response.text
    assert 'href="/health"' in response.text
    assert 'href="/api/tasks"' in response.text
    assert "POST /api/tasks" in response.text
