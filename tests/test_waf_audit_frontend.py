from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_waf_audit_workbench_page_loads() -> None:
    response = client.get("/waf-audits/ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "WAF 报告审计" in response.text
    assert 'href="/console"' in response.text
    assert "生成审计结果" in response.text
    assert "preprocessing_id" in response.text
    assert 'href="/waf"' in response.text
    assert "log_file" not in response.text
    assert "/api/waf-audits" in response.text
    assert "claims" in response.text
    assert "audit-result" in response.text
    assert "audit-opinion" in response.text
    assert "augmented-report" in response.text
    assert "下载回填版 Word" in response.text
    assert "conflict_count" in response.text


def test_homepage_links_to_waf_audit_workbench() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/waf-audits/ui"' in response.text
