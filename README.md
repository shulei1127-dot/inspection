# Inspection Report Platform

`inspection-report-platform` is a FastAPI-based backend for log package ingestion, parsing, and inspection report generation.

This repository currently contains the MVP bootstrap:
- FastAPI backend skeleton
- `GET /health` health check
- Project conventions and baseline documentation

The upload task flow (`POST /api/tasks`) now accepts supported log archives and drives the current MVP pipeline.

## Project Structure

```text
app/
  api/
  core/
  schemas/
  services/
  utils/
docs/
examples/
outputs/
plans/
tests/
uploads/
workdir/
```

## Quick Start

1. Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

4. Verify the health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"inspection-report-platform"}
```

The running service also exposes a minimal homepage:

```bash
http://127.0.0.1:8000/
```

A lightweight platform console is available at:

```bash
http://127.0.0.1:8000/console
```

The console is a no-build, FastAPI-served static page that links the current
modules together. It uses real entry points for implemented flows and marks
module pages that are still pending as `页面待接入`.

For xray report generation, a minimal built-in workbench is available at:

```bash
http://127.0.0.1:8000/xray
```

The page uploads an xray-compatible log archive through `POST /api/tasks`,
shows the returned task summary, and can trigger `POST
/api/tasks/{task_id}/render-report` before downloading the generated DOCX
through `GET /api/tasks/{task_id}/report`.

The xray report path now also has a minimal trend-integration seam:

- if the task workdir contains a canonical `resource_history.csv`, the render
  path writes xray trend artifacts under `workdir/{task_id}/trend/`
- rendered chart images and the optional Mermaid state-graph image are written
  under `outputs/{task_id}/trend/`
- when chart images are available, the final xray `report.docx` is augmented in
  place with a trend appendix
- when history data is missing or has fewer than 2 points, the main DOCX render
  still succeeds and the xray trend step degrades conservatively instead of
  fabricating charts

This seam is enabled by default through:

```bash
XRAY_TREND_ENHANCEMENT_ENABLED=true
```

It remains non-blocking for report generation.

For the WAF preprocessing API flow, a minimal built-in workbench is available at:

```bash
http://127.0.0.1:8000/waf
```

The page uploads a WAF full-log archive, calls `POST /api/waf/preprocessing`,
and exposes download links for the generated status-analysis markdown and
preprocessing detail JSON. Trend/report enhancement remains available through
the API, but it is no longer automatically triggered by this frontend page.

For WAF report auditing, a minimal built-in workbench is available at:

```bash
http://127.0.0.1:8000/waf-audits/ui
```

The page uploads one manual inspection report DOCX and reuses an existing WAF
`preprocessing_id` through `POST /api/waf-audits`. It shows claim / confirmed /
conflict counts and links to task metadata, normalized claims, structured audit
results, and the generated markdown audit opinion. The old direct `log_file`
upload path is kept as a compatibility API path, but the browser flow no longer
asks users to upload the full WAF log archive twice.

The WAF path now also supports a document-only review mode for cases where the
manual inspection DOCX exists but the original full-log package is not
available:

- `POST /api/waf-audits/document-only`
- `GET /api/waf-audits/{task_id}/document-review-input`
- `GET /api/waf-audits/{task_id}/document-review`

In this mode the platform:

- parses the DOCX into normalized claims
- extracts actionable abnormal topics from the document itself
- optionally grounds LLM advice against local help-doc snippets under
  `docs/help_docs/waf/`
- generates `异常情况及处置操作` and `巡检总结`
- appends a clearly labeled `文档直审意见` appendix to a new DOCX

Document-only mode is intentionally conservative:

- it may say `根据巡检文档内容`
- it must not claim `经日志核验`
- when evidence is weak it falls back to `需进一步核查`

Minimal local persistence now uses SQLite through Python's standard library:

```bash
TASKS_DB_PATH=tasks.sqlite3
```

If unset, task records are stored in `./tasks.sqlite3`.

The platform now also reads a local `.env` file automatically. Priority is:

- shell `export` / process env
- `.env`
- built-in defaults

So for day-to-day development you can usually just copy:

```bash
cp .env.example .env
```

Then edit `.env` and start the service normally. If you need a different file,
you can override it with:

```bash
ENV_FILE=/path/to/custom.env uvicorn app.main:app --host 0.0.0.0 --port 8011 --reload
```

The upload flow now resolves log parsing through an internal analyzer abstraction:

```bash
ANALYZER_MODE=remote
ANALYZER_BASE_URL=http://127.0.0.1:8090
ANALYZER_TIMEOUT_SECONDS=30
ANALYZER_RETRY_COUNT=0
```

Current modes:

- `remote`: default mode, call the standalone analyzer service over HTTP
- `local`: explicit development/test override using the in-process analyzer implementation

If you want the old single-process behavior locally, set:

```bash
ANALYZER_MODE=local
```

The standalone analyzer-service API boundary is documented in:

- `docs/log_analyzer_api_v1.md`
- `docs/xray_collector_input_spec_v1.md`

The repository now also includes a minimal future-service scaffold in:

- `log-analyzer-service/`

The analyzer side now also includes a minimal `xray-collector v1` adapter that can
recognize one real collector layout and normalize it into the existing canonical
inputs before producing `unified-json/v1`.

That same xray adapter now also supports the built-in `./minion collect` bundle
shape (`minion_report.gz`) by recognizing its `info/config/logs` layout and
extracting the first high-value fields from:

- host summary
- minion health
- Docker info / ps / images
- CPU / memory / disk summaries

These values are surfaced through `unified.json.metadata` and then into the xray
report appendix so the current xray DOCX template can render them without changing
the platform main flow.

The repository now also includes a minimal multi-product integration skeleton:

- analyzer-side `product_type` recognition
- analyzer-side parser routing
- platform-side product-to-template mapping

Current v1 product routing:

- `xray` -> `XrayCollectorParser`
- `unknown` -> `LinuxDefaultParser`

Current v1 template mapping:

- `xray` -> `templates/xray_inspection_report.docx`
- `unknown` -> `templates/inspection_report.docx`

The xray path now uses a dedicated DOCX template derived from the provided
inspection template. Fields that are not yet produced by the current logs stay
blank or `-`, while the currently parsed xray host/service/container/issue data
is rendered into that template through existing `report_payload.json` +
Carbone flow.

The xray path can now also enable an optional LLM summary-section layer without
changing the fact payload. In this mode:

- analyzer facts still populate versions, IPs, health checks, resource values,
  service rows, container rows, and evidence text
- the LLM only generates:
  - exception summary
  - exception/action items for the top issue slots
  - final inspection summary
- malformed or failed model responses fall back to the current rule-based text
  and do not block DOCX rendering

Recommended optional env vars for this xray-only section generation path:

```bash
XRAY_LLM_SECTION_ENABLED=false
XRAY_LLM_SECTION_MODE=disabled
XRAY_LLM_SECTION_BASE_URL=
XRAY_LLM_SECTION_API_KEY=
XRAY_LLM_SECTION_MODEL=
XRAY_LLM_SECTION_TIMEOUT_SECONDS=30
XRAY_LLM_SECTION_TEMPERATURE=0.2
WAF_LLM_REVIEW_ENABLED=false
WAF_LLM_REVIEW_MODE=disabled
WAF_LLM_REVIEW_BASE_URL=
WAF_LLM_REVIEW_API_KEY=
WAF_LLM_REVIEW_MODEL=
WAF_LLM_REVIEW_TIMEOUT_SECONDS=30
WAF_LLM_REVIEW_TEMPERATURE=0.2
WAF_HELP_DOCS_DIR=docs/help_docs/waf
```

See:

- [product_integration_skeleton_v1.md](/Users/shulei/Downloads/AI/codex/inspection-report-platform/docs/product_integration_skeleton_v1.md)

## Remote Analyzer Integration

The platform can now run against the standalone analyzer service in remote mode.

1. Start `log-analyzer-service`:

```bash
cd log-analyzer-service
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
```

2. Start the platform in remote analyzer mode:

```bash
ANALYZER_MODE=remote \
ANALYZER_BASE_URL=http://127.0.0.1:8090 \
ANALYZER_TIMEOUT_SECONDS=30 \
REPORT_RENDERING_ENABLED=false \
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8013
```

3. Verify both health endpoints:

```bash
curl -s http://127.0.0.1:8090/health
curl -s http://127.0.0.1:8013/health
```

4. Upload an input bundle v1 archive through the platform:

```bash
curl -X POST http://127.0.0.1:8013/api/tasks \
  -F file=@spec-v1.zip \
  -F parser_profile=default \
  -F report_lang=zh-CN
```

Expected remote-flow result:

- analyzer receives `POST /analyze`
- platform persists `workdir/{task_id}/unified.json`
- platform persists `workdir/{task_id}/report_payload.json`
- task status becomes `completed` or `rendered`
- analyzer non-200 JSON errors are now preserved as analyzer-native `code` / `message` / `details` in platform failure responses and task records

If Carbone is available, the rendered report flow remains unchanged:

```bash
curl -X POST http://127.0.0.1:8013/api/tasks/<task_id>/render-report
```

## Repeatable Remote Analyzer Verification

The repository now includes a repeatable acceptance script for the remote analyzer path:

```bash
./scripts/verify_remote_analyzer_integration.sh
```

The script:

- starts `log-analyzer-service` on configurable local ports
- starts the platform in `ANALYZER_MODE=remote`
- builds a sample archive from `tests/fixtures/input_bundle_spec_v1`
- uploads that archive through `POST /api/tasks`
- validates `workdir/{task_id}/unified.json`
- validates `workdir/{task_id}/report_payload.json`
- checks `schema_version` and `payload_version`
- optionally verifies `report.docx` if Carbone is reachable

Useful environment overrides:

```bash
APP_PORT=8013
ANALYZER_PORT=8090
VERIFY_RENDER=auto
CARBONE_BASE_URL=http://127.0.0.1:4000
```

If you want to force the render check:

```bash
VERIFY_RENDER=true ./scripts/verify_remote_analyzer_integration.sh
```

The repository also includes a repeatable failure-mode verification script for the remote analyzer path:

```bash
./scripts/verify_remote_analyzer_failure_modes.sh
```

This script verifies:

- analyzer network failure path
- structured analyzer error: `unsupported_source_type`
- structured analyzer error: `source_not_found`
- non-JSON analyzer `500`

For each scenario it checks:

- platform upload response stability
- task status becomes `analyze_failed`
- task detail preserves `error.code`, `error.message`, and key `error.details`

## CI Smoke Lane Draft

The repository now includes a minimal GitHub Actions draft for remote analyzer regression:

- [remote-analyzer-smoke.yml](/Users/shulei/Downloads/AI/codex/inspection-report-platform/.github/workflows/remote-analyzer-smoke.yml)

It currently runs:

- root platform tests
- analyzer subtree tests
- remote analyzer success smoke
- remote analyzer failure smoke

Carbone render validation is intentionally not part of the required CI path yet.

See also:

- [ci_smoke_lane.md](/Users/shulei/Downloads/AI/codex/inspection-report-platform/docs/ci_smoke_lane.md)

Supported upload archive formats:

- `.zip`
- `.tar.gz`
- `.tgz`
- native xray `minion_report.gz`

## Carbone Runtime

The repository now includes a real HTTP-based Carbone adapter and a dedicated render endpoint:

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`
- `POST /api/tasks/cleanup`
- `POST /api/tasks/{task_id}/render-report`
- `GET /api/tasks/{task_id}/report`

The current MVP keeps one fixed template:

- `templates/inspection_report.docx`

The preferred local reproduction path is Docker-based Carbone On-Premise:

```bash
docker run -t -i --rm --platform linux/amd64 -p 4000:4000 carbone/carbone-ee
```

On this repository's current macOS Apple Silicon environment, a cached `linux/arm64`
`carbone/carbone-ee:latest` image also runs successfully with:

```bash
docker run -d --rm --name inspection-carbone -p 4000:4000 carbone/carbone-ee:latest
curl http://127.0.0.1:4000/status
```

Recommended environment variables:

```bash
CARBONE_BASE_URL=http://127.0.0.1:4000
CARBONE_API_TOKEN=
CARBONE_API_TIMEOUT_SECONDS=30
CARBONE_VERSION=5
REPORT_RENDERING_ENABLED=false
```

Notes:

- The backend only renders from `report_payload.json`; it does not render directly from unified JSON.
- Task detail and task list now prefer SQLite-backed task records, with a narrow filesystem fallback for older local artifacts created before the database layer existed.
- Manual batch cleanup is now available through `POST /api/tasks/cleanup` with the minimal retention filters `keep_latest` and `older_than_days`.
- For Carbone On-Premise, authentication is disabled by default unless you explicitly enable it.
- Carbone supports direct DOCX-to-DOCX generation without LibreOffice. LibreOffice is required when you need format conversion such as DOCX-to-PDF.
- Official Docker variants include `slim` for minimal runtime and `latest/full` for LibreOffice-enabled runtime.
- The current shell still cannot directly open raw TCP 443 connections to `registry-1.docker.io`, but Docker Desktop is configured with its own proxy path and `docker pull carbone/carbone-ee:latest` succeeds on this machine.
- If the Carbone image cannot be pulled or the runtime cannot be reached, the backend returns structured render errors and does not fake `report.docx` generation.

## Real Render Verification

The repository now includes a minimal verification script for the real render path:

```bash
./scripts/verify_carbone_render.sh
```

The script:

- starts a local Carbone container from the cached official image
- waits for `GET /status`
- starts the FastAPI app on a temporary port
- uploads a small archive through `POST /api/tasks`
- calls `POST /api/tasks/{task_id}/render-report`
- verifies that `outputs/{task_id}/report.docx` exists and is a valid DOCX

If you prefer to verify manually:

```bash
docker run -d --rm --name inspection-carbone -p 4000:4000 carbone/carbone-ee:latest
curl http://127.0.0.1:4000/status

APP_HOST=127.0.0.1 APP_PORT=8012 CARBONE_BASE_URL=http://127.0.0.1:4000 \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8012
```

Then:

1. upload a supported archive with `POST /api/tasks`
2. confirm `workdir/{task_id}/report_payload.json` exists
3. call `POST /api/tasks/{task_id}/render-report`
4. confirm `outputs/{task_id}/report.docx` exists and opens as a DOCX file

## Input Bundle V1

The current parser support is now formalized in:

- `docs/input_bundle_spec_v1.md`

Recommended archive layout after extraction:

```text
<bundle-root>/
  system/
    system_info
    systemctl_status
  containers/
    docker_ps
```

The current parser prefers these canonical v1 paths first and only keeps a
narrow legacy fallback for older local fixtures.

## Trend Enhancement Subchain

The repository now also includes an independent trend-enhancement subchain for
cleaned status-analysis markdown reports. This subchain is intentionally kept
separate from `/api/tasks`, the xray main flow, and the `waf_audits` flow.

Current phase-1 scope:

- read one cleaned status-analysis `.md` report
- build `trend_input.json`
- build `trend_assessment.json`
- build `trend_summary.md`
- generate up to 3 PNG static charts for metrics with at least 2 history points
- generate a Mermaid state graph source file for status / risk-direction explanation
- optionally append a trend appendix to a provided base `docx` report and write
  `augmented_report.docx`

Current phase-1 boundaries:

- no OCR
- no LLM numeric prediction
- no complex time-series model
- no full report rewrite
- single-point snapshots remain conservative and do not generate trend charts
- Mermaid PNG rendering is optional and defaults to disabled unless explicitly configured

Current round2 hardening highlights:

- snapshot metric tables such as `指标 | 数值 | 状态` are recognized more reliably
- event timeline tables such as `日期 | 事件 | 恢复方式` are recognized and folded into stability evidence
- predictive or recommendation sections are ignored so the builder does not treat future-looking narrative as history
- docx appendix text is generated directly from `trend_assessment.json` instead of rendering markdown
- the offline script now inserts the repo root into `sys.path`, so it can run without manually setting `PYTHONPATH`

Current round3 hardening highlights:

- stability evidence is no longer treated as one flat total and now splits into:
  - `restart_count`
  - `panic_count`
  - `abnormal_exit_count`
  - `unclean_shutdown_count`
- nearby events are grouped into lightweight fault chains so the stability section reads like an incident chain instead of a loose hit list
- second-batch regression fixtures now cover:
  - low-risk stability samples
  - disk-judgeable samples
  - noisy text without false event promotion
- the markdown summary and optional DOCX appendix now surface event-split and fault-chain text directly from `trend_assessment.json`

Current round4 adaptation highlights:

- the trend input builder now adapts a real SafeLine / WAF report shape that uses:
  - `> **采集时间**: ...`
  - snapshot tables shaped like `指标 | 采集快照值 | 备注`
  - local uptime tables shaped like `指标 | 值`
  - incident tables that mix time, severity, component, and detail columns
- single-point CPU / memory / disk snapshots are now extracted from this WAF report family, even when values are embedded in:
  - `us + sy` CPU rows
  - memory percentage remarks such as `84.6% 偏高-告警`
  - disk rows such as `使用率 | ~11%`
- `uptime` can now be extracted from section-local runtime tables instead of relying only on top-level metadata
- stability noise filtering is tighter for this report family:
  - recommendation bullets
  - impact/explanation prose
  - explicit negative statements such as `无 OOM / panic`
  - numbered headings and ID cells no longer become fake event subjects
- one real local WAF status-analysis markdown sample now replays through the trend subchain with:
  - CPU / memory / disk snapshots extracted
  - uptime extracted
  - stability still conservatively marked `pressure_high`
  - resource dimensions still remaining `unknown` when only one snapshot point exists

Current Mermaid text v1 output:

- `trend_state_graph.mmd` is generated from `trend_assessment.json`
- the graph focuses on the current highest-risk metric so the visual summary does not dilute the main signal
- the same Mermaid source is written to:
  - `workdir/trd_*/trend_state_graph.mmd`
  - `outputs/trd_*/trend_state_graph.mmd`
- `trend_summary.md` embeds the Mermaid block with an explicit note that it is a state / risk-direction graph, not a precise numeric forecast chart
- no Mermaid CLI, Node.js, Chromium, PNG rendering, or Word insertion is required for the text path

Current optional Mermaid image rendering:

- platform-side rendering is routed through `MERMAID_RENDERER_MODE`
- supported modes:
  - `disabled`: default, keep `.mmd` only
  - `local_cli`: render through local `mmdc`
  - `remote`: send only the Mermaid source string to a future renderer service and save returned PNG bytes
- when rendering succeeds, `outputs/trd_*/trend_state_graph.png` is rendered from `outputs/trd_*/trend_state_graph.mmd`
- when rendering is disabled, unavailable, times out, or fails, the trend run still succeeds and keeps the `.mmd` source
- if a base DOCX is provided and Mermaid PNG rendering succeeds, the PNG is appended through the existing trend appendix image path
- configuration:
  - `MERMAID_RENDERER_MODE=disabled`
  - `MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091`
  - `MERMAID_RENDERER_TIMEOUT_SECONDS=30`
  - `MERMAID_CLI_PATH=mmdc`
  - `MERMAID_CLI_TIMEOUT_SECONDS=30`
- Mermaid CLI installation is intentionally not managed by this Python project

Recommended local development values:

```env
MERMAID_RENDERER_MODE=local_cli
MERMAID_CLI_PATH=mmdc
```

Recommended future service deployment values:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://mermaid-renderer-service:8091
```

## Mermaid Renderer Service

The repository now includes a lightweight `mermaid-renderer-service/` subproject.
It encapsulates Node.js, Mermaid CLI, Chromium, and fonts behind a small HTTP API
so the Python platform does not need to install Mermaid CLI directly.

Service API:

- `GET /health`
- `POST /render`

`POST /render` accepts Mermaid source text only:

```json
{
  "source": "flowchart LR\nA --> B",
  "format": "png",
  "theme": "default",
  "background": "white"
}
```

Successful responses return PNG bytes with:

```text
Content-Type: image/png
Cache-Control: no-store
```

Run service tests:

```bash
cd mermaid-renderer-service
npm test
```

Build the Docker image:

```bash
cd mermaid-renderer-service
docker build -t mermaid-renderer-service:0.1.0 .
```

The Docker image pins Mermaid CLI through `package.json` and installs Chromium /
CJK fonts inside the image so server deployment does not rely on host-level
`mmdc` installation.

Remote integration validation:

```bash
docker run --rm -p 8091:8091 mermaid-renderer-service:0.1.0

curl http://127.0.0.1:8091/health

MERMAID_RENDERER_MODE=remote \
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8091 \
.venv/bin/python scripts/run_trend_enhancement.py tests/fixtures/trend_reports/multi_point_status_analysis.md
```

Expected result:

- `outputs/trd_*/trend_state_graph.mmd`
- `outputs/trd_*/trend_state_graph.png`
- normal metric charts such as `cpu_trend.png`

If `8091` is already used locally, map a different host port, for example:

```bash
docker run --rm -p 8092:8091 mermaid-renderer-service:0.1.0
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8092
```

For local demos and repeated report generation, prefer the helper scripts:

```bash
./scripts/start_mermaid_renderer.sh
./scripts/verify_mermaid_renderer.sh --platform
./scripts/stop_mermaid_renderer.sh
```

Default script convention:

- container name: `mermaid-renderer-service`
- image: `mermaid-renderer-service:0.1.0`
- restart policy: `unless-stopped`
- host port: `8092`
- container port: `8091`

The start script keeps the renderer running as a local service. Use this platform
config while it is running:

```env
MERMAID_RENDERER_MODE=remote
MERMAID_RENDERER_BASE_URL=http://127.0.0.1:8092
```

Run it locally with:

```bash
.venv/bin/python scripts/run_trend_enhancement.py path/to/status_analysis.md --docx path/to/base_report.docx
```

The command writes intermediate artifacts under `workdir/trd_*` and final chart /
Mermaid / augmented DOCX outputs under `outputs/trd_*`.

## Log Preprocessing Layer

The repository now also includes a new offline-first preprocessing seam for
SafeLine / WAF full-log directories:

```text
full-log directory
  -> status_analysis_evidence.json
  -> status_analysis_summary.json
  -> 状态分析报告.md
  -> existing trend-enhancement subchain
```

Current round1 scope:

- one extracted SafeLine / WAF full-log directory as input
- fixed recent-window filtering for the latest 30 days
- selective scan is the default mode, so the full source directory is not copied
  into `workdir/prep_*/source_logs`
- full-copy debug mode is still available with `LOG_PREPROCESSING_COPY_SOURCE=true`
- explicit reference-time precedence:
  - extracted collection time
  - collection epoch suffix in names such as `minion-command-collect-...-1765356785`
  - caller-provided reference time
  - current system time
- stable markdown rendering that is intentionally friendly to the current
  `trend_input_builder`

Current round1 source priority is intentionally fixed:

- CPU:
  - `system/top.txt`
  - `resources/resource_summary.txt`
- memory:
  - `system/free.txt`
  - `resources/resource_summary.txt`
  - `system/top.txt` as a narrow fallback for `MiB Mem` snapshots
- disk:
  - `system/df.txt`
  - `resources/resource_summary.txt`
- uptime:
  - `system/uptime.txt`
  - `system/top.txt` as a narrow fallback for `top - ... up ...`
  - collection metadata fallback

Run it locally with:

```bash
.venv/bin/python scripts/run_log_preprocessing.py path/to/full_log_directory
```

This command writes:

- `workdir/prep_*/resources/resource_history.csv`
- `workdir/prep_*/status_analysis_evidence.json`
- `workdir/prep_*/status_analysis_summary.json`
- `workdir/prep_*/status_analysis.md`

In selective mode, `status_analysis_evidence.json` includes `scan_coverage`
metadata with:

- `coverage_level`: `full`, `partial`, or `minimal`
- scanned files
- skipped files
- skipped/limited reasons

`status_analysis_summary.json` also carries a short delivery-friendly scan
summary:

- `coverage_level`
- `scan_limitations`
- `major_skipped_sources`
- `coverage_warnings`

Current round2 content-quality improvements:

- repeated same-component / same-time-window service errors are aggregated into
  one event-chain style finding in `status_analysis_summary.json` and
  `状态分析报告.md`
- raw service evidence remains in `status_analysis_evidence.json`
- disk extraction now accepts additional low-ambiguity df-like files such as
  `system/disk.txt`, `system/filesystem.txt`, and `system/filesystems.txt`
- disk remains `unknown` when only vague disk job logs or Docker block-I/O
  counters are available

Current round3 resource-history support:

- explicit resource history files can populate `resource_time_series` in both
  `status_analysis_evidence.json` and `status_analysis_summary.json`
- supported v1 sources are intentionally narrow:
  - `resources/resource_history.csv`
  - `resources/resource_timeseries.csv`
  - `resources/resource_history.txt`
  - `system/resource_history.csv`
  - `system/resource_history.txt`
- supported columns can use English or Chinese labels for timestamp, CPU,
  memory, and disk; values can be plain numbers or percentages
- generated `状态分析报告.md` now includes a `资源历史样本` table that the existing
  trend subchain can parse directly
- dense or uneven resource history is normalized to one 12-hour point using
  per-metric averages, so charts use a stable cadence instead of raw noisy rows
- ambiguous app-internal counters are not treated as system CPU / memory / disk
  history; if no explicit resource history source exists, trend output remains
  conservative and may skip charts for single-point snapshots

Current resource-history generator v1:

- each preprocessing run materializes a canonical
  `workdir/prep_*/resources/resource_history.csv`
- when an explicit history source exists, the generated CSV is normalized to one
  12-hour point using per-metric averages
- when no explicit history source exists, the generator writes at most one
  current snapshot point from low-ambiguity CPU / memory / disk sources
- when no reliable resource source exists, the generator writes a header-only
  CSV so downstream behavior remains explicit and conservative
- the generator does not interpolate missing windows, synthesize future points,
  or treat ambiguous application counters as host resource history
- trend input building now collapses duplicate same-collection metric points
  when a generated `resources/resource_history.csv` single point and a current
  snapshot describe the same 12-hour bucket and value, so single snapshots do
  not accidentally become fake two-point trends

The current round1 regression also validates the direct handoff:

```text
full-log directory -> 状态分析报告.md -> trend_input.json -> trend_assessment.json
```

without manually rewriting the generated markdown.

API readiness draft:

- [waf_api_v1_draft.md](/Users/shulei/Downloads/AI/codex/inspection-report-platform/docs/waf_api_v1_draft.md)
- `POST /api/waf/preprocessing` is now implemented as the first minimal API
  wrapper around the offline preprocessing service
- `POST /api/waf/trend-enhancements` is now implemented for the
  `preprocessing_id` handoff path, with optional Word appendix augmentation
- read/download endpoints are implemented for preprocessing metadata,
  status-analysis markdown, trend metadata, trend-summary markdown, and optional
  augmented DOCX report
- `GET /waf` provides a minimal browser workbench over the preprocessing API flow only; trend/report enhancement stays as a separate API handoff for now

Create a WAF preprocessing task through the API:

```bash
curl -X POST http://127.0.0.1:8011/api/waf/preprocessing \
  -F "file=@path/to/waf-full-log.tar.gz"
```

The response includes:

- `resource_history_csv_path`
- `status_analysis_evidence_path`
- `status_analysis_summary_path`
- `status_analysis_md_path`

Retrieve WAF preprocessing artifacts:

```bash
curl http://127.0.0.1:8011/api/waf/preprocessing/prep_20260418_120000_abcd1234
curl -OJ http://127.0.0.1:8011/api/waf/preprocessing/prep_20260418_120000_abcd1234/status-analysis
```

Create a WAF trend-enhancement task from a preprocessing result:

```bash
curl -X POST http://127.0.0.1:8011/api/waf/trend-enhancements \
  -F "preprocessing_id=prep_20260418_120000_abcd1234"
```

Optionally append the trend appendix into a Word report:

```bash
curl -X POST http://127.0.0.1:8011/api/waf/trend-enhancements \
  -F "preprocessing_id=prep_20260418_120000_abcd1234" \
  -F "base_report_docx=@path/to/base_report.docx"
```

The response includes:

- `trend_input_path`
- `trend_assessment_path`
- `trend_summary_path`
- `trend_state_graph_path`
- `output_trend_state_graph_path`
- `chart_paths`
- optional `augmented_report_path`

Retrieve WAF trend artifacts:

```bash
curl http://127.0.0.1:8011/api/waf/trend-enhancements/trd_20260418_120500_abcd1234
curl -OJ http://127.0.0.1:8011/api/waf/trend-enhancements/trd_20260418_120500_abcd1234/summary
curl -OJ http://127.0.0.1:8011/api/waf/trend-enhancements/trd_20260418_120500_abcd1234/augmented-report
```

## Development Rules

- Every new feature, bugfix, or scoped change must start with a plan file under `plans/`.
- Plan naming format: `YYYY-MM-DD-short-name.md`
- Code changes should stay within a single clear small loop.
- After each independent requirement:
  - verify locally
  - commit changes
  - push to GitHub
- Update `docs/project_status.md` every time a scoped requirement is completed.

## Current Scope

Completed:
- project bootstrap
- FastAPI skeleton
- health check endpoint

Planned next:
- `POST /api/tasks`
- zip upload to `uploads/`
- auto-extract to `workdir/{task_id}/`
- task metadata response
- unified JSON output contract for future parsers
