from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/console", response_class=HTMLResponse, summary="Minimal platform console")
def get_console() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>巡检报告平台控制台</title>
          <style>
            :root {
              --primary: #2b5797;
              --primary-dark: #073f7e;
              --surface: #f8f9ff;
              --surface-low: #eff4ff;
              --surface-lowest: #ffffff;
              --surface-high: #dce9ff;
              --text-main: #0b1c30;
              --text-muted: #515f7a;
              --border-color: rgba(195, 198, 210, 0.34);
              --shadow: 0 18px 48px rgba(11, 28, 48, 0.06);
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              min-height: 100vh;
              display: flex;
              overflow-x: hidden;
              background:
                radial-gradient(circle at 78% 4%, rgba(170, 199, 255, 0.32), transparent 28%),
                linear-gradient(135deg, #f8f9ff 0%, #f1f5ff 48%, #f7f9ff 100%);
              color: var(--text-main);
              font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            svg { width: 20px; height: 20px; fill: currentColor; }
            .sidebar {
              position: fixed;
              inset: 0 auto 0 0;
              z-index: 40;
              width: 256px;
              height: 100vh;
              padding: 20px;
              display: flex;
              flex-direction: column;
              gap: 10px;
              background: var(--surface-low);
              border-right: 1px solid var(--border-color);
            }
            .brand { margin-bottom: 26px; }
            .brand-title {
              display: block;
              color: var(--primary-dark);
              font-size: 20px;
              font-weight: 900;
              letter-spacing: 0.06em;
            }
            .brand-subtitle {
              display: block;
              margin-top: 6px;
              color: rgba(7, 63, 126, 0.62);
              font-size: 12px;
              font-weight: 700;
              letter-spacing: 0.18em;
            }
            .btn-new,
            .nav-item,
            .btn-action,
            .bento-card {
              text-decoration: none;
            }
            .btn-new {
              display: flex;
              align-items: center;
              justify-content: center;
              gap: 10px;
              margin-bottom: 20px;
              padding: 13px 16px;
              border-radius: 10px;
              background: linear-gradient(135deg, var(--primary-dark), var(--primary));
              color: #fff;
              font-weight: 800;
              box-shadow: 0 12px 28px rgba(43, 87, 151, 0.18);
            }
            .nav-items {
              display: flex;
              flex: 1;
              flex-direction: column;
              gap: 6px;
            }
            .nav-item {
              display: flex;
              align-items: center;
              gap: 12px;
              padding: 11px 12px;
              border-radius: 10px;
              color: rgba(11, 28, 48, 0.72);
              font-size: 14px;
              font-weight: 650;
            }
            .nav-item.active {
              background: #fff;
              color: var(--primary-dark);
              box-shadow: 0 1px 2px rgba(11, 28, 48, 0.05);
            }
            .nav-item:hover:not(.active) {
              background: rgba(255, 255, 255, 0.58);
            }
            .main-wrapper {
              min-height: 100vh;
              flex: 1;
              margin-left: 256px;
            }
            .topbar {
              position: sticky;
              top: 0;
              z-index: 30;
              height: 66px;
              padding: 0 32px;
              display: flex;
              align-items: center;
              gap: 24px;
              background: rgba(248, 249, 255, 0.86);
              backdrop-filter: blur(14px);
              border-bottom: 1px solid var(--border-color);
            }
            .topbar h1 {
              margin: 0;
              color: var(--primary-dark);
              font-size: 21px;
              line-height: 1;
              letter-spacing: 0.1em;
            }
            .health-status {
              display: flex;
              align-items: center;
              gap: 14px;
              padding: 8px 16px;
              border: 1px solid var(--border-color);
              border-radius: 999px;
              background: var(--surface-lowest);
              box-shadow: 0 6px 18px rgba(11, 28, 48, 0.04);
            }
            .health-label {
              font-size: 12px;
              font-weight: 900;
              letter-spacing: 0.08em;
            }
            .health-item {
              display: flex;
              align-items: center;
              gap: 6px;
              color: var(--text-muted);
              font-size: 11px;
              font-weight: 800;
              text-transform: uppercase;
            }
            .dot {
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: #9e9e9e;
            }
            .dot.ok { background: #2f8f67; }
            .content {
              width: min(1200px, calc(100% - 48px));
              margin: 0 auto;
              padding: 42px 0 54px;
            }
            .grid-container {
              display: grid;
              grid-template-columns: minmax(0, 1fr) 340px;
              gap: 32px;
              align-items: start;
            }
            .section-header { margin-bottom: 20px; }
            .section-title {
              margin: 0 0 10px;
              font-size: 28px;
              line-height: 1.1;
              letter-spacing: -0.03em;
            }
            .section-desc {
              margin: 0;
              color: var(--text-muted);
              line-height: 1.7;
            }
            .cards-grid {
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 18px;
            }
            .card,
            .bento-card,
            .flow-card,
            .tasks-card {
              border: 1px solid var(--border-color);
              border-radius: 16px;
              background: var(--surface-lowest);
              box-shadow: var(--shadow);
            }
            .card {
              position: relative;
              min-height: 260px;
              padding: 26px;
              overflow: hidden;
              display: flex;
              flex-direction: column;
            }
            .card-accent {
              position: absolute;
              inset: 0 auto 0 0;
              width: 4px;
            }
            .card-accent.xray { background: var(--primary-dark); }
            .card-accent.waf { background: var(--primary); }
            .card-accent.audit { background: var(--text-muted); }
            .card-icon {
              width: 42px;
              height: 42px;
              margin-bottom: 22px;
              display: flex;
              align-items: center;
              justify-content: center;
              border-radius: 12px;
              background: var(--surface-low);
              color: var(--primary-dark);
            }
            .card-title {
              margin: 0 0 10px;
              font-size: 18px;
              letter-spacing: -0.02em;
            }
            .card-desc {
              flex: 1;
              margin: 0 0 22px;
              color: var(--text-muted);
              font-size: 14px;
              line-height: 1.75;
            }
            .chip {
              display: inline-flex;
              width: fit-content;
              margin-bottom: 14px;
              padding: 5px 9px;
              border-radius: 999px;
              background: var(--surface-low);
              color: var(--text-muted);
              font-size: 11px;
              font-weight: 900;
            }
            .btn-action {
              display: inline-flex;
              align-items: center;
              justify-content: center;
              min-height: 42px;
              padding: 9px 12px;
              border: 1px solid var(--border-color);
              border-radius: 10px;
              background: var(--surface-low);
              color: var(--text-main);
              font-size: 14px;
              font-weight: 850;
              text-align: center;
            }
            .btn-action.primary {
              border: 0;
              color: #fff;
              background: linear-gradient(135deg, var(--primary-dark), var(--primary));
            }
            .bento-card {
              min-height: 96px;
              padding: 22px;
              display: flex;
              align-items: center;
              justify-content: space-between;
              color: inherit;
            }
            .bento-card h3 {
              margin: 0 0 5px;
              font-size: 16px;
            }
            .bento-card p {
              margin: 0;
              color: var(--text-muted);
              font-size: 13px;
            }
            .flow-card {
              padding: 24px;
              background: var(--surface-low);
            }
            .flow-card h3 {
              margin: 0 0 24px;
              font-size: 18px;
            }
            .flow-step {
              position: relative;
              display: flex;
              gap: 14px;
              margin-bottom: 24px;
            }
            .flow-step::before {
              content: "";
              position: absolute;
              left: 11px;
              top: 24px;
              bottom: -24px;
              width: 2px;
              background: rgba(115, 119, 129, 0.26);
            }
            .flow-step:last-child::before { display: none; }
            .flow-icon {
              position: relative;
              z-index: 1;
              width: 24px;
              height: 24px;
              display: flex;
              align-items: center;
              justify-content: center;
              border: 2px solid rgba(115, 119, 129, 0.42);
              border-radius: 50%;
              background: var(--surface-lowest);
            }
            .flow-icon.active {
              border-color: var(--surface-low);
              background: var(--primary-dark);
            }
            .flow-icon.active::after {
              content: "";
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: #fff;
            }
            .flow-title {
              margin: 0 0 5px;
              font-size: 14px;
              font-weight: 850;
            }
            .flow-desc {
              margin: 0;
              color: var(--text-muted);
              font-size: 12px;
            }
            .tasks-section { margin-top: 34px; }
            .tasks-card {
              min-height: 150px;
              padding: 32px;
              display: flex;
              align-items: center;
              justify-content: center;
              color: var(--text-muted);
              text-align: center;
              line-height: 1.7;
            }
            @media (max-width: 900px) {
              .sidebar { display: none; }
              .main-wrapper { margin-left: 0; }
              .topbar {
                height: auto;
                padding: 18px;
                align-items: flex-start;
                flex-direction: column;
              }
              .health-status {
                width: 100%;
                overflow-x: auto;
              }
              .content {
                width: min(100% - 28px, 720px);
                padding-top: 28px;
              }
              .grid-container,
              .cards-grid {
                grid-template-columns: 1fr;
              }
            }
          </style>
        </head>
        <body>
          <aside class="sidebar">
            <div class="brand">
              <span class="brand-title">巡检中心</span>
              <span class="brand-subtitle">企业级哨兵</span>
            </div>
            <a class="btn-new" href="#modules">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"></path></svg>
              发起新巡检
            </a>
            <nav class="nav-items" aria-label="主导航">
              <a class="nav-item active" href="/console">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"></path></svg>
                控制台
              </a>
              <a class="nav-item" href="/waf">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-1 15-4-4 1.41-1.41L11 13.17l5.59-5.59L18 9l-7 7z"></path></svg>
                WAF 日志清洗
              </a>
              <a class="nav-item" href="/docs">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3h13v2H8V3zm0 8h13v2H8v-2zm0 8h13v2H8v-2zM3 3h3v2H3V3zm0 8h3v2H3v-2zm0 8h3v2H3v-2z"></path></svg>
                API 文档
              </a>
            </nav>
          </aside>

          <main class="main-wrapper">
            <header class="topbar">
              <h1>巡检报告平台</h1>
              <div class="health-status" aria-label="服务健康状态">
                <span class="health-label">服务健康状态</span>
                <span class="health-item" title="可通过 /health 检查"><span class="dot ok"></span>PLAT</span>
                <span class="health-item" title="待后端聚合"><span class="dot"></span>ANALYZ 待接入</span>
                <span class="health-item" title="待后端聚合"><span class="dot"></span>CARB 待接入</span>
                <span class="health-item" title="待后端聚合"><span class="dot"></span>MERM 待接入</span>
              </div>
            </header>

            <section class="content">
              <div class="grid-container">
                <div>
                  <div class="section-header" id="modules">
                    <h2 class="section-title">处理模块</h2>
                    <p class="section-desc">执行核心安全数据流水线。上传原始日志，生成结构化数据、状态分析和交付报告。</p>
                  </div>
                  <div class="cards-grid">
                    <article class="card">
                      <span class="card-accent xray"></span>
                      <div class="card-icon">
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14zM7 10h2v7H7zm4-3h2v10h-2zm4 6h2v4h-2z"></path></svg>
                      </div>
                      <span class="chip">已接入</span>
                      <h3 class="card-title">xray 巡检报告生成</h3>
                      <p class="card-desc">上传 xray 日志包，生成 unified.json、report_payload.json 和格式化 Word 报告。</p>
                      <a class="btn-action primary" href="/xray">进入 xray 报告生成</a>
                    </article>

                    <article class="card">
                      <span class="card-accent waf"></span>
                      <div class="card-icon">
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.36 2.72 20.78 4.14 15.06 9.85c1.07 1.54 1.22 3.39.32 4.59L9.06 8.12c1.2-.9 3.05-.75 4.59.32l5.71-5.72zM5.93 17.57c-2.01-2.01-3.24-4.41-3.58-6.65l4.88 4.88-1.3 1.77zm7.15 4.08c-2.24-.34-4.64-1.57-6.65-3.58l1.77-1.3 4.88 4.88z"></path></svg>
                      </div>
                      <span class="chip">已接入</span>
                      <h3 class="card-title">WAF 日志清洗</h3>
                      <p class="card-desc">上传 SafeLine / 雷池 WAF 全量日志包，生成清洗后的结构化产物和状态分析报告。</p>
                      <a class="btn-action primary" href="/waf">进入 WAF 日志清洗</a>
                    </article>

                    <article class="card">
                      <span class="card-accent audit"></span>
                      <div class="card-icon">
                        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-9 14-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path></svg>
                      </div>
                      <span class="chip">已接入</span>
                      <h3 class="card-title">WAF 报告审计</h3>
                      <p class="card-desc">上传人工巡检报告并填写 preprocessing_id，复用已清洗日志证据检查报告内容。</p>
                      <a class="btn-action primary" href="/waf-audits/ui">进入 WAF 报告审计</a>
                    </article>

                    <a class="bento-card" href="/docs">
                      <div>
                        <h3>API 文档</h3>
                        <p>进入 Swagger，查看和调试全部接口。</p>
                      </div>
                      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4 10.59 5.41 16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"></path></svg>
                    </a>
                  </div>
                </div>

                <aside class="flow-card">
                  <h3>标准处理流程</h3>
                  <div class="flow-step">
                    <span class="flow-icon active"></span>
                    <div><p class="flow-title">上传日志包</p><p class="flow-desc">Ingest system logs</p></div>
                  </div>
                  <div class="flow-step">
                    <span class="flow-icon"></span>
                    <div><p class="flow-title">清洗 / 解析</p><p class="flow-desc">Extract signal and evidence</p></div>
                  </div>
                  <div class="flow-step">
                    <span class="flow-icon"></span>
                    <div><p class="flow-title">结构化数据</p><p class="flow-desc">Build JSON artifacts</p></div>
                  </div>
                  <div class="flow-step">
                    <span class="flow-icon"></span>
                    <div><p class="flow-title">后续分析</p><p class="flow-desc">Audit or report enrichment</p></div>
                  </div>
                  <div class="flow-step">
                    <span class="flow-icon"></span>
                    <div><p class="flow-title">生成 Word 报告</p><p class="flow-desc">Deliver report artifacts</p></div>
                  </div>
                </aside>
              </div>

              <section class="tasks-section">
                <h2 class="section-title" style="font-size: 20px;">最近任务活动</h2>
                <div class="tasks-card">
                  暂无统一最近任务列表。上传日志并生成报告后，xray 任务可从 <a href="/api/tasks">/api/tasks</a> 查看；WAF 产物当前通过生成结果中的 ID 下载。
                </div>
              </section>
            </section>
          </main>
        </body>
        </html>
        """
    )
