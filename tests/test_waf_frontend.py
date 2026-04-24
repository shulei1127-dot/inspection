from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_waf_workbench_page_loads() -> None:
    response = client.get("/waf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "WAF 日志清洗" in response.text
    assert 'href="/console"' in response.text
    assert "开始日志清洗" in response.text
    assert "一键复制" in response.text
    assert "/api/waf/preprocessing" in response.text
    assert "/api/waf/trend-enhancements" not in response.text
    assert "status-analysis" in response.text
    assert "preprocessing-detail-link" in response.text
    assert "augmented-report" not in response.text


def test_homepage_links_to_waf_workbench() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/console"' in response.text
    assert 'href="/waf"' in response.text
    assert "POST /api/waf/preprocessing" in response.text
