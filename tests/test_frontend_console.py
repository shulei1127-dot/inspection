from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_console_page_loads_with_real_module_links() -> None:
    response = client.get("/console")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "巡检报告平台" in response.text
    assert "处理模块" in response.text
    assert 'href="/xray"' in response.text
    assert 'href="/waf"' in response.text
    assert 'href="/waf-audits/ui"' in response.text
    assert 'href="/docs"' in response.text
    assert "页面待接入" not in response.text
    assert "进入 xray 报告生成" in response.text
    assert "进入 WAF 日志清洗" in response.text
    assert "进入 WAF 报告审计" in response.text
    assert "暂无统一最近任务列表" in response.text


def test_console_health_status_does_not_claim_unchecked_services_are_healthy() -> None:
    response = client.get("/console")

    assert response.status_code == 200
    assert "PLAT" in response.text
    assert "ANALYZ 待接入" in response.text
    assert "CARB 待接入" in response.text
    assert "MERM 待接入" in response.text
