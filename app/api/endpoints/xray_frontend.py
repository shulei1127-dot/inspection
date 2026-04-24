from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter()


@router.get("/xray", response_class=HTMLResponse, summary="Minimal xray report generation workbench")
def get_xray_workbench() -> HTMLResponse:
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>xray 巡检报告生成</title>
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
            .button-row {
              display: grid;
              grid-template-columns: 1fr;
              gap: 10px;
              margin-top: 22px;
            }
            .primary-button,
            .secondary-button {
              width: 100%;
              min-height: 48px;
              padding: 13px 18px;
              border-radius: 12px;
              cursor: pointer;
              font: inherit;
              font-weight: 900;
              letter-spacing: 0.02em;
            }
            .primary-button {
              border: 0;
              background: linear-gradient(135deg, var(--primary-dark), var(--primary));
              color: #fff;
              box-shadow: 0 14px 28px rgba(43, 87, 151, 0.18);
            }
            .secondary-button {
              border: 1px solid var(--border-color);
              background: var(--surface-low);
              color: var(--primary-dark);
            }
            button:disabled {
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
              <span class="health-chip">xray 主链路已接入</span>
            </div>

            <section class="hero">
              <div>
                <p class="eyebrow">xray Report Generation v1</p>
                <h1>xray 巡检报告生成</h1>
                <p class="intro">
                  上传 xray 日志包或兼容归档，平台会生成 unified.json、report_payload.json。
                  若报告渲染运行时可用，可继续生成并下载 Word 巡检报告。
                </p>
              </div>
              <aside class="api-card">
                <strong>当前页面调用真实 API</strong>
                <p>
                  上传调用 <code>POST /api/tasks</code>，渲染调用
                  <code>POST /api/tasks/{task_id}/render-report</code>，下载调用
                  <code>GET /api/tasks/{task_id}/report</code>。
                </p>
              </aside>
            </section>

            <div class="flow-strip" aria-label="处理流程">
              <div class="flow-item active">上传日志包</div>
              <div class="flow-item">analyzer 解析</div>
              <div class="flow-item">生成 JSON</div>
              <div class="flow-item">渲染报告</div>
              <div class="flow-item">下载 Word</div>
            </div>

            <section class="layout">
              <form id="xray-form" class="panel">
                <div class="panel-body">
                  <h2>1. 上传输入</h2>
                  <p class="hint">
                    v1 保持最小闭环：选择 xray 日志包，保留默认解析参数即可。报告渲染依赖 Carbone 运行时。
                  </p>

                  <label for="log-file">xray 日志包</label>
                  <input id="log-file" name="file" type="file" required>
                  <span class="field-note">支持当前 `/api/tasks` 已支持的 zip / tar.gz / tgz / minion_report.gz 等归档。</span>

                  <label for="parser-profile">parser_profile</label>
                  <input id="parser-profile" name="parser_profile" type="text" value="default">

                  <label for="report-lang">report_lang</label>
                  <input id="report-lang" name="report_lang" type="text" value="zh-CN">

                  <div class="button-row">
                    <button id="submit-button" class="primary-button" type="submit">上传并生成任务</button>
                    <button id="render-button" class="secondary-button" type="button" disabled>渲染 Word 报告</button>
                  </div>
                  <div id="error-box" class="error-box"></div>

                  <div id="steps" class="steps" aria-live="polite">
                    <div class="step">等待上传 xray 日志包。</div>
                  </div>
                </div>
              </form>

              <article class="panel">
                <div class="panel-body">
                  <span class="status-pill" id="status-pill">未开始</span>
                  <h2>2. 结果与下载</h2>
                  <p class="hint">生成完成后，这里会显示任务状态、摘要计数、产物路径和下载入口。</p>

                  <div class="result-grid">
                    <div class="metric"><span>task_id</span><strong id="task-id">-</strong></div>
                    <div class="metric"><span>status</span><strong id="task-status">-</strong></div>
                    <div class="metric"><span>services / containers</span><strong id="inventory-count">-</strong></div>
                    <div class="metric"><span>issue_count</span><strong id="issue-count">-</strong></div>
                  </div>

                  <nav class="downloads" aria-label="下载产物">
                    <a id="task-detail-link" href="#" aria-disabled="true">任务详情 JSON</a>
                    <a id="report-download-link" href="#" aria-disabled="true">下载 Word 报告</a>
                  </nav>

                  <div class="json-panel">
                    <pre id="result-json">等待生成结果...</pre>
                  </div>
                </div>
              </article>
            </section>
          </main>

          <script>
            const form = document.querySelector("#xray-form");
            const submitButton = document.querySelector("#submit-button");
            const renderButton = document.querySelector("#render-button");
            const errorBox = document.querySelector("#error-box");
            const steps = document.querySelector("#steps");
            const resultJson = document.querySelector("#result-json");
            const statusPill = document.querySelector("#status-pill");
            let currentTaskId = null;
            let latestTaskData = null;

            const fields = {
              taskId: document.querySelector("#task-id"),
              taskStatus: document.querySelector("#task-status"),
              inventoryCount: document.querySelector("#inventory-count"),
              issueCount: document.querySelector("#issue-count"),
              detailLink: document.querySelector("#task-detail-link"),
              reportLink: document.querySelector("#report-download-link"),
            };

            function setBusy(isBusy) {
              submitButton.disabled = isBusy;
              submitButton.textContent = isBusy ? "上传处理中..." : "上传并生成任务";
            }

            function clearLinks() {
              for (const link of [fields.detailLink, fields.reportLink]) {
                link.href = "#";
                link.setAttribute("aria-disabled", "true");
                link.removeAttribute("download");
              }
              renderButton.disabled = true;
            }

            function resetResult() {
              currentTaskId = null;
              latestTaskData = null;
              errorBox.style.display = "none";
              errorBox.textContent = "";
              fields.taskId.textContent = "-";
              fields.taskStatus.textContent = "-";
              fields.inventoryCount.textContent = "-";
              fields.issueCount.textContent = "-";
              statusPill.textContent = "上传中";
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

            function renderTaskResult(taskData) {
              const summary = taskData.summary || {};
              currentTaskId = taskData.task_id;
              latestTaskData = taskData;
              fields.taskId.textContent = taskData.task_id || "-";
              fields.taskStatus.textContent = taskData.status || "-";
              fields.inventoryCount.textContent = `${summary.service_count || 0} / ${summary.container_count || 0}`;
              fields.issueCount.textContent = summary.issue_count ?? 0;
              statusPill.textContent = taskData.status || "已完成";

              if (taskData.task_id) {
                enableLink(fields.detailLink, `/api/tasks/${encodeURIComponent(taskData.task_id)}`);
                renderButton.disabled = false;
              }
              if (taskData.task_id && taskData.report_file_path) {
                enableLink(fields.reportLink, `/api/tasks/${encodeURIComponent(taskData.task_id)}/report`, true);
                renderButton.disabled = true;
              }
            }

            form.addEventListener("submit", async (event) => {
              event.preventDefault();
              resetResult();
              setBusy(true);

              try {
                const logFile = document.querySelector("#log-file").files[0];
                if (!logFile) {
                  throw new Error("请先选择 xray 日志包。");
                }

                addStep("开始上传日志包并创建任务...", "info");
                const formData = new FormData();
                formData.append("file", logFile);
                formData.append("parser_profile", document.querySelector("#parser-profile").value || "default");
                formData.append("report_lang", document.querySelector("#report-lang").value || "zh-CN");

                const taskData = await requestJson("/api/tasks", { method: "POST", body: formData });
                renderTaskResult(taskData);
                resultJson.textContent = JSON.stringify({ task: taskData }, null, 2);
                addStep(`任务生成完成：${taskData.task_id}`, "ok");
                if (taskData.report_file_path) {
                  addStep("Word 报告已生成，可直接下载。", "ok");
                } else {
                  addStep("报告尚未渲染，如 Carbone 可用，可点击“渲染 Word 报告”。", "info");
                }
              } catch (error) {
                resultJson.textContent = "生成失败。请查看左侧错误信息。";
                showError(error);
              } finally {
                setBusy(false);
              }
            });

            renderButton.addEventListener("click", async () => {
              if (!currentTaskId) {
                showError(new Error("没有可渲染的 task_id。"));
                return;
              }
              renderButton.disabled = true;
              try {
                addStep("开始渲染 Word 报告...", "info");
                const renderData = await requestJson(
                  `/api/tasks/${encodeURIComponent(currentTaskId)}/render-report`,
                  { method: "POST" },
                );
                if (latestTaskData) {
                  latestTaskData.status = renderData.status;
                  latestTaskData.report_file_path = renderData.report_file_path;
                  renderTaskResult(latestTaskData);
                }
                resultJson.textContent = JSON.stringify({
                  task: latestTaskData,
                  render: renderData,
                }, null, 2);
                addStep("Word 报告渲染完成，可下载。", "ok");
              } catch (error) {
                showError(error);
                renderButton.disabled = false;
              }
            });
          </script>
        </body>
        </html>
        """
    )
