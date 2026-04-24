from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/waf", response_class=HTMLResponse, summary="Minimal WAF preprocessing workbench")
def get_waf_workbench() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>WAF 日志清洗</title>
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
              --success: #2f8f67;
              --warning: #b56a14;
              --error: #b42318;
              --shadow: 0 18px 48px rgba(11, 28, 48, 0.06);
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              min-height: 100vh;
              background:
                radial-gradient(circle at 82% 4%, rgba(170, 199, 255, 0.32), transparent 30%),
                linear-gradient(135deg, #f8f9ff 0%, #f1f5ff 48%, #f7f9ff 100%);
              color: var(--text-main);
              font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }
            svg { width: 20px; height: 20px; fill: currentColor; }
            a { color: inherit; }
            .shell {
              width: min(1180px, calc(100% - 36px));
              margin: 0 auto;
              padding: 28px 0 52px;
            }
            .topline {
              display: flex;
              justify-content: space-between;
              align-items: center;
              gap: 16px;
              margin-bottom: 28px;
            }
            .back-link {
              display: inline-flex;
              align-items: center;
              gap: 8px;
              padding: 10px 13px;
              border: 1px solid var(--border-color);
              border-radius: 999px;
              background: rgba(255, 255, 255, 0.72);
              color: var(--primary-dark);
              font-size: 14px;
              font-weight: 850;
              text-decoration: none;
              box-shadow: 0 8px 24px rgba(11, 28, 48, 0.04);
            }
            .health-chip {
              display: inline-flex;
              align-items: center;
              gap: 8px;
              padding: 10px 14px;
              border: 1px solid var(--border-color);
              border-radius: 999px;
              background: var(--surface-lowest);
              color: var(--text-muted);
              font-size: 12px;
              font-weight: 800;
            }
            .health-chip::before {
              content: "";
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: var(--success);
            }
            .hero {
              display: grid;
              grid-template-columns: minmax(0, 1fr) 330px;
              gap: 28px;
              align-items: end;
              margin-bottom: 28px;
            }
            .eyebrow {
              margin: 0 0 10px;
              color: var(--primary);
              font-size: 12px;
              font-weight: 900;
              letter-spacing: 0.18em;
              text-transform: uppercase;
            }
            h1 {
              margin: 0;
              max-width: 780px;
              color: var(--text-main);
              font-size: clamp(34px, 5vw, 58px);
              line-height: 0.98;
              letter-spacing: -0.055em;
            }
            .intro {
              max-width: 760px;
              margin: 18px 0 0;
              color: var(--text-muted);
              font-size: 16px;
              line-height: 1.8;
            }
            .api-card {
              padding: 22px;
              border: 1px solid var(--border-color);
              border-radius: 18px;
              background: rgba(255, 255, 255, 0.72);
              box-shadow: var(--shadow);
            }
            .api-card strong {
              display: block;
              margin-bottom: 8px;
              color: var(--primary-dark);
              font-size: 14px;
            }
            .api-card p {
              margin: 0;
              color: var(--text-muted);
              font-size: 13px;
              line-height: 1.7;
            }
            code {
              padding: 2px 6px;
              border-radius: 7px;
              background: var(--surface-low);
              color: var(--primary-dark);
            }
            .layout {
              display: grid;
              grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
              gap: 22px;
              align-items: start;
            }
            .panel {
              border: 1px solid var(--border-color);
              border-radius: 18px;
              background: var(--surface-lowest);
              box-shadow: var(--shadow);
              overflow: hidden;
            }
            .panel-body { padding: 24px; }
            .panel h2 {
              margin: 0 0 8px;
              font-size: 22px;
              letter-spacing: -0.03em;
            }
            .hint {
              margin: 0 0 20px;
              color: var(--text-muted);
              font-size: 14px;
              line-height: 1.7;
            }
            label {
              display: block;
              margin: 18px 0 8px;
              font-weight: 850;
            }
            .field-note {
              display: block;
              margin-top: 7px;
              color: var(--text-muted);
              font-size: 12px;
              line-height: 1.5;
            }
            input[type="file"] {
              width: 100%;
              padding: 13px;
              border: 1px dashed rgba(43, 87, 151, 0.45);
              border-radius: 14px;
              background: var(--surface-low);
              color: var(--text-main);
              font: inherit;
            }
            .primary-button {
              width: 100%;
              min-height: 48px;
              margin-top: 22px;
              padding: 13px 18px;
              border: 0;
              border-radius: 12px;
              background: linear-gradient(135deg, var(--primary-dark), var(--primary));
              color: #fff;
              cursor: pointer;
              font: inherit;
              font-weight: 900;
              letter-spacing: 0.02em;
              box-shadow: 0 14px 28px rgba(43, 87, 151, 0.18);
            }
            .primary-button:disabled {
              cursor: not-allowed;
              opacity: 0.62;
            }
            .steps {
              display: grid;
              gap: 10px;
              margin-top: 18px;
            }
            .step {
              position: relative;
              padding: 12px 12px 12px 34px;
              border-radius: 14px;
              background: var(--surface-low);
              color: var(--text-muted);
              font-size: 13px;
              line-height: 1.55;
            }
            .step::before {
              content: "";
              position: absolute;
              left: 14px;
              top: 18px;
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: var(--warning);
            }
            .step.ok::before { background: var(--success); }
            .step.error::before { background: var(--error); }
            .error-box {
              display: none;
              margin-top: 14px;
              padding: 14px;
              border: 1px solid rgba(180, 35, 24, 0.22);
              border-radius: 14px;
              background: #fff1ef;
              color: var(--error);
              font-size: 13px;
              line-height: 1.6;
            }
            .status-pill {
              display: inline-flex;
              align-items: center;
              gap: 8px;
              margin-bottom: 16px;
              padding: 8px 12px;
              border-radius: 999px;
              background: var(--surface-low);
              color: var(--primary-dark);
              font-size: 12px;
              font-weight: 900;
            }
            .status-pill::before {
              content: "";
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: var(--primary);
            }
            .result-grid {
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 14px;
              margin-top: 18px;
            }
            .metric {
              min-height: 98px;
              padding: 16px;
              border: 1px solid var(--border-color);
              border-radius: 16px;
              background: var(--surface-low);
            }
            .metric span {
              display: block;
              margin-bottom: 8px;
              color: var(--text-muted);
              font-size: 12px;
              font-weight: 800;
            }
            .metric strong {
              display: block;
              overflow-wrap: anywhere;
              font-size: 18px;
              line-height: 1.35;
            }
            .metric-actions {
              display: flex;
              gap: 8px;
              margin-top: 12px;
            }
            .copy-button {
              min-height: 34px;
              padding: 7px 11px;
              border: 1px solid rgba(43, 87, 151, 0.22);
              border-radius: 10px;
              background: #fff;
              color: var(--primary-dark);
              cursor: pointer;
              font: inherit;
              font-size: 12px;
              font-weight: 900;
            }
            .copy-button:disabled {
              cursor: not-allowed;
              opacity: 0.48;
            }
            .downloads {
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 10px;
              margin: 20px 0 0;
            }
            .downloads a {
              min-height: 56px;
              display: flex;
              align-items: center;
              justify-content: center;
              padding: 12px;
              border: 1px solid var(--border-color);
              border-radius: 14px;
              background: var(--surface-low);
              color: var(--primary-dark);
              text-align: center;
              text-decoration: none;
              font-size: 13px;
              font-weight: 900;
            }
            .downloads a[aria-disabled="true"] {
              pointer-events: none;
              opacity: 0.45;
              filter: grayscale(1);
            }
            .json-panel {
              margin-top: 22px;
              border-radius: 16px;
              background: #0b1c30;
              color: #eaf1ff;
              overflow: hidden;
            }
            pre {
              max-height: 360px;
              margin: 0;
              padding: 18px;
              overflow: auto;
              font-size: 12px;
              line-height: 1.6;
              white-space: pre-wrap;
              word-break: break-word;
            }
            .flow-strip {
              display: grid;
              grid-template-columns: repeat(5, minmax(0, 1fr));
              gap: 8px;
              margin-bottom: 22px;
            }
            .flow-item {
              padding: 12px;
              border-radius: 14px;
              background: var(--surface-low);
              color: var(--text-muted);
              font-size: 12px;
              font-weight: 850;
              text-align: center;
            }
            .flow-item.active {
              background: var(--primary-dark);
              color: #fff;
            }
            @media (max-width: 900px) {
              .topline,
              .hero,
              .layout {
                grid-template-columns: 1fr;
              }
              .topline {
                align-items: flex-start;
                flex-direction: column;
              }
              .downloads,
              .flow-strip,
              .result-grid {
                grid-template-columns: 1fr;
              }
            }
          </style>
        </head>
        <body>
          <main class="shell">
            <div class="topline">
              <a class="back-link" href="/console">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.42-1.41L7.83 13H20v-2z"></path></svg>
                返回控制台
              </a>
              <span class="health-chip">WAF API 已接入</span>
            </div>

            <section class="hero">
              <div>
                <p class="eyebrow">WAF API Minimal Frontend v1</p>
                <h1>WAF 日志清洗</h1>
                <p class="intro">
                  上传 SafeLine / 雷池 WAF 全量日志包，先做选择性扫描、证据提取和状态分析报告生成。
                  后续报告增强和 Word 附录暂时不在这个页面自动执行。
                </p>
              </div>
              <aside class="api-card">
                <strong>当前页面调用真实 API</strong>
                <p>
                  当前页面只调用 <code>POST /api/waf/preprocessing</code>，
                  用于生成清洗后的结构化产物和状态分析 Markdown。
                </p>
              </aside>
            </section>

            <div class="flow-strip" aria-label="处理流程">
              <div class="flow-item active">上传日志包</div>
              <div class="flow-item">清洗 / 解析</div>
              <div class="flow-item">状态分析</div>
              <div class="flow-item">清洗产物</div>
              <div class="flow-item">下载产物</div>
            </div>

            <section class="layout">
              <form id="waf-form" class="panel">
                <div class="panel-body">
                  <h2>1. 上传输入</h2>
                  <p class="hint">
                    日志包必选。大日志包会需要等待一会儿，页面会显示执行步骤和错误信息。
                  </p>

                  <label for="log-file">WAF 全量日志包</label>
                  <input id="log-file" name="file" type="file" required>
                  <span class="field-note">支持当前 WAF preprocessing API 已支持的归档格式。</span>

                  <button id="submit-button" class="primary-button" type="submit">开始日志清洗</button>
                  <div id="error-box" class="error-box"></div>

                  <div id="steps" class="steps" aria-live="polite">
                    <div class="step">等待上传 WAF 日志包。</div>
                  </div>
                </div>
              </form>

              <article class="panel">
                <div class="panel-body">
                  <span class="status-pill" id="status-pill">未开始</span>
                  <h2>2. 结果与下载</h2>
                  <p class="hint">清洗完成后，这里会显示 preprocessing_id、覆盖情况，以及可下载的状态分析报告。</p>

                  <div class="result-grid">
                    <div class="metric">
                      <span>preprocessing_id</span>
                      <strong id="preprocessing-id">-</strong>
                      <div class="metric-actions">
                        <button id="copy-preprocessing-id" class="copy-button" type="button" disabled>一键复制</button>
                      </div>
                    </div>
                    <div class="metric"><span>coverage_level</span><strong id="coverage-level">-</strong></div>
                    <div class="metric"><span>resource_points</span><strong id="resource-points">-</strong></div>
                    <div class="metric"><span>service_findings</span><strong id="service-findings">-</strong></div>
                  </div>

                  <nav class="downloads" aria-label="下载产物">
                    <a id="status-analysis-link" href="#" aria-disabled="true">状态分析 Markdown</a>
                    <a id="preprocessing-detail-link" href="#" aria-disabled="true">清洗详情 JSON</a>
                  </nav>

                  <div class="json-panel">
                    <pre id="result-json">等待生成结果...</pre>
                  </div>
                </div>
              </article>
            </section>
          </main>

          <script>
            const form = document.querySelector("#waf-form");
            const submitButton = document.querySelector("#submit-button");
            const errorBox = document.querySelector("#error-box");
            const steps = document.querySelector("#steps");
            const resultJson = document.querySelector("#result-json");
            const statusPill = document.querySelector("#status-pill");

            const fields = {
              preprocessingId: document.querySelector("#preprocessing-id"),
              coverageLevel: document.querySelector("#coverage-level"),
              resourcePoints: document.querySelector("#resource-points"),
              serviceFindings: document.querySelector("#service-findings"),
              statusAnalysisLink: document.querySelector("#status-analysis-link"),
              preprocessingDetailLink: document.querySelector("#preprocessing-detail-link"),
              copyPreprocessingIdButton: document.querySelector("#copy-preprocessing-id"),
            };

            function setBusy(isBusy) {
              submitButton.disabled = isBusy;
              submitButton.textContent = isBusy ? "清洗中，请稍候..." : "开始日志清洗";
            }

            function clearLinks() {
              for (const link of [fields.statusAnalysisLink, fields.preprocessingDetailLink]) {
                link.href = "#";
                link.setAttribute("aria-disabled", "true");
                link.removeAttribute("download");
              }
            }

            function resetResult() {
              errorBox.style.display = "none";
              errorBox.textContent = "";
              fields.preprocessingId.textContent = "-";
              fields.coverageLevel.textContent = "-";
              fields.resourcePoints.textContent = "-";
              fields.serviceFindings.textContent = "-";
              fields.copyPreprocessingIdButton.disabled = true;
              statusPill.textContent = "清洗中";
              resultJson.textContent = "等待 API 返回...";
              clearLinks();
              steps.innerHTML = "";
            }

            function addStep(message, type = "info") {
              const step = document.createElement("div");
              step.className = `step ${type}`;
              step.textContent = message;
              steps.appendChild(step);
            }

            function enableDownload(link, href) {
              link.href = href;
              link.removeAttribute("aria-disabled");
              link.setAttribute("download", "");
            }

            function showError(error) {
              errorBox.style.display = "block";
              errorBox.textContent = error.message;
              statusPill.textContent = "失败";
              addStep(error.message, "error");
            }

            function formatApiError(response, payload, fallbackText) {
              if (payload && payload.error) {
                const detailText = payload.error.details && Object.keys(payload.error.details).length
                  ? ` details=${JSON.stringify(payload.error.details)}`
                  : "";
                return `${payload.error.code}: ${payload.error.message}${detailText}`;
              }
              return `HTTP ${response.status}: ${fallbackText || response.statusText}`;
            }

            async function parseResponse(response) {
              const text = await response.text();
              if (!text) {
                return null;
              }
              try {
                return JSON.parse(text);
              } catch {
                return { rawText: text.slice(0, 500) };
              }
            }

            async function postForm(url, formData) {
              const response = await fetch(url, {
                method: "POST",
                body: formData,
              });
              const payload = await parseResponse(response);
              if (!response.ok || !payload || payload.success !== true) {
                const fallbackText = payload && payload.rawText ? payload.rawText : "";
                throw new Error(formatApiError(response, payload, fallbackText));
              }
              return payload.data;
            }

            function renderPreprocessingResult(preprocessingData) {
              const summary = preprocessingData.summary || {};
              const preprocessingId = preprocessingData.preprocessing_id;
              fields.preprocessingId.textContent = preprocessingId || "-";
              fields.coverageLevel.textContent = summary.coverage_level || "-";
              fields.resourcePoints.textContent = String(summary.resource_history_point_count ?? 0);
              fields.serviceFindings.textContent = String(summary.service_finding_count ?? 0);
              if (preprocessingId) {
                fields.copyPreprocessingIdButton.disabled = false;
                enableDownload(
                  fields.statusAnalysisLink,
                  `/api/waf/preprocessing/${encodeURIComponent(preprocessingId)}/status-analysis`,
                );
                enableDownload(
                  fields.preprocessingDetailLink,
                  `/api/waf/preprocessing/${encodeURIComponent(preprocessingId)}`,
                );
              }
            }

            async function copyPreprocessingId() {
              const preprocessingId = fields.preprocessingId.textContent.trim();
              if (!preprocessingId || preprocessingId === "-") {
                return;
              }
              try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  await navigator.clipboard.writeText(preprocessingId);
                } else {
                  const textArea = document.createElement("textarea");
                  textArea.value = preprocessingId;
                  document.body.appendChild(textArea);
                  textArea.select();
                  document.execCommand("copy");
                  document.body.removeChild(textArea);
                }
                addStep(`已复制 preprocessing_id：${preprocessingId}`, "ok");
              } catch {
                addStep("自动复制失败，请手动选中 preprocessing_id 复制。", "error");
              }
            }

            fields.copyPreprocessingIdButton.addEventListener("click", copyPreprocessingId);

            form.addEventListener("submit", async (event) => {
              event.preventDefault();
              resetResult();
              setBusy(true);

              try {
                const logFile = document.querySelector("#log-file").files[0];
                if (!logFile) {
                  throw new Error("请先选择 WAF 全量日志包。");
                }

                addStep("开始上传 WAF 日志包并执行清洗...", "info");
                const preprocessingForm = new FormData();
                preprocessingForm.append("file", logFile);
                const preprocessingData = await postForm("/api/waf/preprocessing", preprocessingForm);
                renderPreprocessingResult(preprocessingData);
                resultJson.textContent = JSON.stringify({
                  preprocessing: preprocessingData,
                }, null, 2);
                statusPill.textContent = "已完成";
                addStep(`日志清洗完成：${preprocessingData.preprocessing_id}`, "ok");
                addStep("状态分析 Markdown 和清洗详情 JSON 已可下载。", "ok");
              } catch (error) {
                resultJson.textContent = "清洗失败。请查看左侧错误信息。";
                showError(error);
              } finally {
                setBusy(false);
              }
            });
          </script>
        </body>
        </html>
        """
    )
