# WAF preprocessing and trend API v1 draft

This document tracks the API boundary for the offline WAF preprocessing and
trend-enhancement chain. `POST /api/waf/preprocessing` and
`POST /api/waf/trend-enhancements` are implemented in v1; artifact
read/download endpoints for preprocessing and trend outputs are also implemented.

## Goals

- Expose the current offline-first WAF full-log preprocessing chain through a stable API boundary.
- Expose the current trend-enhancement chain through a stable API boundary.
- Keep generated artifacts addressable and diagnosable.
- Avoid mixing this flow into `/api/tasks`, xray report generation, or `waf_audits`.

## Current Offline Chain

```text
full-log archive / directory
  -> run_log_preprocessing()
  -> resources/resource_history.csv
  -> status_analysis_evidence.json
  -> status_analysis_summary.json
  -> status_analysis.md
  -> run_trend_enhancement()
  -> trend_input.json
  -> trend_assessment.json
  -> trend_summary.md
  -> optional trend images
  -> optional augmented_report.docx
```

## Proposed Endpoints

### POST /api/waf/preprocessing

Create a WAF preprocessing task from a SafeLine / WAF full-log archive upload.

Status: implemented.

#### Request

`multipart/form-data`

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `file` | binary | yes | WAF log archive. v1 should support `.zip`, `.tar.gz`, `.tgz`, and native minion collect archive names if extraction is already safe. |
| `reference_time` | string | no | Optional ISO-like reference time. Used only when collection time cannot be extracted. |
| `copy_source` | boolean | no | Debug option. Defaults to current selective-scan behavior. |

#### Success Response

```json
{
  "success": true,
  "data": {
    "preprocessing_id": "prep_20260418_120000_abcd1234",
    "status": "completed",
    "contract_version": "waf-preprocessing-response/v1",
    "source_archive_path": "uploads/prep_...tar.gz",
    "source_directory_path": "workdir/prep_.../source",
    "resource_history_csv_path": "workdir/prep_.../resources/resource_history.csv",
    "status_analysis_evidence_path": "workdir/prep_.../status_analysis_evidence.json",
    "status_analysis_summary_path": "workdir/prep_.../status_analysis_summary.json",
    "status_analysis_md_path": "workdir/prep_.../status_analysis.md",
    "summary": {
      "coverage_level": "full",
      "resource_history_point_count": 1,
      "stability_event_count": 0,
      "service_finding_count": 0,
      "warnings": []
    }
  }
}
```

### GET /api/waf/preprocessing/{preprocessing_id}

Return preprocessing task metadata and artifact paths.

Status: implemented.

### GET /api/waf/preprocessing/{preprocessing_id}/status-analysis

Download or return the generated `status_analysis.md`.

Status: implemented.

### POST /api/waf/trend-enhancements

Create a trend-enhancement run from an existing preprocessing task or an uploaded cleaned status-analysis markdown.

Status: implemented for `preprocessing_id`; direct markdown upload remains draft-only.

#### Request Option A: Existing Preprocessing Task

`multipart/form-data`

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `preprocessing_id` | string | yes | Existing preprocessing run id, such as `prep_20260418_120000_abcd1234`. |
| `base_report_docx` | binary | no | Existing Word report to append the trend appendix into. |

#### Request Option B: Markdown + Optional DOCX

`multipart/form-data`

| Field | Type | Required | Description |
|------|------|----------|-------------|
| `status_analysis_md` | binary | yes | Cleaned status-analysis markdown. |
| `base_report_docx` | binary | no | Existing Word report to append trend appendix into. |

#### Success Response

```json
{
  "success": true,
  "data": {
    "trend_id": "trd_20260418_120500_abcd1234",
    "status": "completed",
    "contract_version": "waf-trend-enhancement-response/v1",
    "trend_input_path": "workdir/trd_.../trend_input.json",
    "trend_assessment_path": "workdir/trd_.../trend_assessment.json",
    "trend_summary_path": "workdir/trd_.../trend_summary.md",
    "trend_state_graph_path": "outputs/trd_.../trend_state_graph.mmd",
    "trend_state_graph_image_path": "outputs/trd_.../trend_state_graph.png",
    "chart_paths": [
      "outputs/trd_.../cpu_trend.png"
    ],
    "augmented_report_path": "outputs/trd_.../augmented_report.docx",
    "summary": {
      "overall_status": "unknown",
      "data_quality": "partial",
      "warnings": [
        "CPU 历史点少于 2 个，第一阶段不会生成 CPU 趋势图。"
      ]
    }
  }
}
```

### GET /api/waf/trend-enhancements/{trend_id}

Return trend-enhancement metadata and artifact paths.

Status: implemented.

### GET /api/waf/trend-enhancements/{trend_id}/summary

Download or return `trend_summary.md`.

Status: implemented.

### GET /api/waf/trend-enhancements/{trend_id}/augmented-report

Download `augmented_report.docx` when generated.

Status: implemented.

## Error Envelope

Future endpoints should reuse the platform style:

```json
{
  "success": false,
  "error": {
    "code": "waf_preprocessing_failed",
    "message": "Failed to build status analysis from uploaded WAF logs.",
    "details": {
      "preprocessing_id": "prep_...",
      "stage": "status_analysis_builder"
    }
  }
}
```

## Suggested Error Codes

| Code | Meaning |
|------|---------|
| `unsupported_archive_type` | Uploaded archive type is not supported. |
| `archive_extract_failed` | Archive could not be safely extracted. |
| `waf_preprocessing_failed` | Status-analysis artifacts could not be generated. |
| `trend_input_build_failed` | Markdown could not be converted to `trend_input.json`. |
| `trend_enhancement_failed` | Trend assessment or summary generation failed. |
| `base_report_not_found` | Requested base DOCX path does not exist. |
| `artifact_not_found` | Requested output artifact does not exist. |

## API Readiness Constraints

- Single snapshot must not be presented as a real trend chart.
- `resource_history.csv` remains the canonical resource-history handoff artifact.
- Trend image rendering stays optional and non-blocking.
- Mermaid renderer failures should not fail the trend task if `.mmd` was generated.
- Existing offline scripts must remain usable after API exposure.

## Non-goals for v1

- No frontend requirement.
- No LLM-based trend prediction.
- No complex time-series model.
- No automatic background scheduling.
- No changes to `/api/tasks`, xray, or `waf_audits`.
- No multi-product generalized preprocessing API yet.
