from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/waf-audits/ui", response_class=HTMLResponse, summary="Minimal WAF audit workbench")
def get_waf_audit_workbench() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>WAF 报告审计</title>
          <style>
            :root {
              --primary: #2b5797;
              --primary-dark: #073f7e;
              --surface: #f8f9ff;
              --surface-low: #eff4ff;
              --surface-lowest: #ffffff;
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
            .back-link,
            .health-chip {
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
            .api-card,
            .panel {
              border: 1px solid var(--border-color);
              border-radius: 18px;
              background: rgba(255, 255, 255, 0.78);
              box-shadow: var(--shadow);
            }
            .api-card { padding: 22px; }
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
            .panel { overflow: hidden; }
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
            input[type="file"],
            input[type="text"] {
              width: 100%;
              padding: 13px;
              border: 1px solid var(--border-color);
              border-radius: 14px;
              background: var(--surface-low);
              color: var(--text-main);
              font: inherit;
            }
            input[type="file"] {
              border-style: dashed;
              border-color: rgba(43, 87, 151, 0.45);
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
              opacity: 0.52;
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
              min-height: 96px;
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
              <span class="health-chip">WAF 审计 API 已接入</span>
            </div>

            <section class="hero">
              <div>
                <p class="eyebrow">WAF Audit v1</p>
                <h1>WAF 报告审计</h1>
                <p class="intro">
                  上传一份人工巡检报告 DOCX，并填写 WAF 日志清洗生成的 preprocessing_id。
                  平台会复用清洗后的证据，生成结构化审计结果与 Markdown 审核意见。
                </p>
              </div>
              <aside class="api-card">
                <strong>当前页面调用真实 API</strong>
                <p>
                  创建审计调用 <code>POST /api/waf-audits</code>，产物通过
                  <code>GET /api/waf-audits/{task_id}/...</code> 读取。
                </p>
              </aside>
            </section>

            <div class="flow-strip" aria-label="处理流程">
              <div class="flow-item active">上传报告</div>
              <div class="flow-item">填写清洗 ID</div>
              <div class="flow-item">抽取声明</div>
              <div class="flow-item">比对证据</div>
              <div class="flow-item">下载意见</div>
            </div>

            <section class="layout">
              <form id="waf-audit-form" class="panel">
                <div class="panel-body">
                  <h2>1. 上传输入</h2>
                  <p class="hint">
                    先在 <a href="/waf">WAF 日志清洗</a> 上传全量日志包，复制 preprocessing_id 后填到这里。当前输出是结构化 JSON 和 Markdown 意见单。
                  </p>

                  <label for="report-file">人工巡检报告 DOCX</label>
                  <input id="report-file" name="report_file" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required>
                  <span class="field-note">用于抽取报告声明、版本、组件状态和结论。</span>

                  <label for="preprocessing-id">preprocessing_id</label>
                  <input id="preprocessing-id" name="preprocessing_id" type="text" placeholder="prep_20260418_120000_abcd1234" required>
                  <span class="field-note">来自 /waf 日志清洗结果，用于复用已清洗的状态分析和证据产物。</span>

                  <label for="report-lang">report_lang</label>
                  <input id="report-lang" name="report_lang" type="text" value="zh-CN">

                  <button id="submit-button" class="primary-button" type="submit">生成审计结果</button>
                  <div id="error-box" class="error-box"></div>

                  <div id="steps" class="steps" aria-live="polite">
                    <div class="step">等待上传人工报告并填写 preprocessing_id。</div>
                  </div>
                </div>
              </form>

              <article class="panel">
                <div class="panel-body">
                  <span class="status-pill" id="status-pill">未开始</span>
                  <h2>2. 结果与下载</h2>
                  <p class="hint">完成后，这里会显示审计任务摘要，并开放 claims、audit-result、audit-opinion 和回填版 Word 入口。</p>

                  <div class="result-grid">
                    <div class="metric"><span>task_id</span><strong id="task-id">-</strong></div>
                    <div class="metric"><span>status</span><strong id="task-status">-</strong></div>
                    <div class="metric"><span>claim / confirmed</span><strong id="claim-count">-</strong></div>
                    <div class="metric"><span>conflict_count</span><strong id="conflict-count">-</strong></div>
                  </div>

                  <nav class="downloads" aria-label="审计产物">
                    <a id="detail-link" href="#" aria-disabled="true">审计任务 JSON</a>
                    <a id="claims-link" href="#" aria-disabled="true">报告声明 JSON</a>
                    <a id="audit-result-link" href="#" aria-disabled="true">审计结果 JSON</a>
                    <a id="audit-opinion-link" href="#" aria-disabled="true">下载审核意见</a>
                    <a id="augmented-report-link" href="#" aria-disabled="true">下载回填版 Word</a>
                  </nav>

                  <div class="json-panel">
                    <pre id="result-json">等待生成结果...</pre>
                  </div>
                </div>
              </article>
            </section>
          </main>

          <script>
            const form = document.querySelector("#waf-audit-form");
            const submitButton = document.querySelector("#submit-button");
            const errorBox = document.querySelector("#error-box");
            const steps = document.querySelector("#steps");
            const resultJson = document.querySelector("#result-json");
            const statusPill = document.querySelector("#status-pill");

            const fields = {
              taskId: document.querySelector("#task-id"),
              taskStatus: document.querySelector("#task-status"),
              claimCount: document.querySelector("#claim-count"),
              conflictCount: document.querySelector("#conflict-count"),
              detailLink: document.querySelector("#detail-link"),
              claimsLink: document.querySelector("#claims-link"),
              auditResultLink: document.querySelector("#audit-result-link"),
              auditOpinionLink: document.querySelector("#audit-opinion-link"),
              augmentedReportLink: document.querySelector("#augmented-report-link"),
            };

            function setBusy(isBusy) {
              submitButton.disabled = isBusy;
              submitButton.textContent = isBusy ? "审计处理中..." : "生成审计结果";
            }

            function clearLinks() {
              for (const link of [fields.detailLink, fields.claimsLink, fields.auditResultLink, fields.auditOpinionLink, fields.augmentedReportLink]) {
                link.href = "#";
                link.setAttribute("aria-disabled", "true");
                link.removeAttribute("download");
              }
            }

            function resetResult() {
              errorBox.style.display = "none";
              errorBox.textContent = "";
              fields.taskId.textContent = "-";
              fields.taskStatus.textContent = "-";
              fields.claimCount.textContent = "-";
              fields.conflictCount.textContent = "-";
              statusPill.textContent = "审计中";
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

            function enableLink(link, href, download = false) {
              link.href = href;
              link.removeAttribute("aria-disabled");
              if (download) {
                link.setAttribute("download", "");
              } else {
                link.removeAttribute("download");
              }
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

            async function requestJson(url, options) {
              const response = await fetch(url, options);
              const payload = await parseResponse(response);
              if (!response.ok || !payload || payload.success !== true) {
                const fallbackText = payload && payload.rawText ? payload.rawText : "";
                throw new Error(formatApiError(response, payload, fallbackText));
              }
              return payload.data;
            }

            function renderAuditResult(auditData) {
              const summary = auditData.summary || {};
              fields.taskId.textContent = auditData.task_id || "-";
              fields.taskStatus.textContent = auditData.status || "-";
              fields.claimCount.textContent = `${summary.claim_count || 0} / ${summary.confirmed_count || 0}`;
              fields.conflictCount.textContent = summary.conflict_count ?? 0;
              statusPill.textContent = auditData.status || "已完成";

              if (auditData.task_id) {
                const taskId = encodeURIComponent(auditData.task_id);
                enableLink(fields.detailLink, `/api/waf-audits/${taskId}`);
                enableLink(fields.claimsLink, `/api/waf-audits/${taskId}/claims`);
                enableLink(fields.auditResultLink, `/api/waf-audits/${taskId}/audit-result`);
                enableLink(fields.auditOpinionLink, `/api/waf-audits/${taskId}/audit-opinion`, true);
                if (auditData.audit_augmented_report_path) {
                  enableLink(fields.augmentedReportLink, `/api/waf-audits/${taskId}/augmented-report`, true);
                }
              }
            }

            form.addEventListener("submit", async (event) => {
              event.preventDefault();
              resetResult();
              setBusy(true);

              try {
                const reportFile = document.querySelector("#report-file").files[0];
                const preprocessingId = document.querySelector("#preprocessing-id").value.trim();
                if (!reportFile) {
                  throw new Error("请先选择人工巡检报告 DOCX。");
                }
                if (!preprocessingId) {
                  throw new Error("请先填写 WAF 日志清洗生成的 preprocessing_id。");
                }

                addStep("开始上传报告并读取清洗产物...", "info");
                const formData = new FormData();
                formData.append("report_file", reportFile);
                formData.append("preprocessing_id", preprocessingId);
                formData.append("report_lang", document.querySelector("#report-lang").value || "zh-CN");

                const auditData = await requestJson("/api/waf-audits", { method: "POST", body: formData });
                renderAuditResult(auditData);
                resultJson.textContent = JSON.stringify({ waf_audit: auditData }, null, 2);
                addStep(`审计完成：${auditData.task_id}`, "ok");
                addStep(`已复用清洗结果：${auditData.preprocessing_id || preprocessingId}`, "ok");
                addStep("审核意见已生成，可下载 Markdown。", "ok");
              } catch (error) {
                resultJson.textContent = "审计失败。请查看左侧错误信息。";
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
