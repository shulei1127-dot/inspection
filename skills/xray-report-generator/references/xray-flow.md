# Xray Flow

## Main chain

`xray archive -> platform upload -> extract -> analyzer -> unified.json -> report_payload.json -> optional xray LLM sections -> Carbone -> report.docx`

## Local page

- `/xray`

## Main APIs

- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/render-report`
- `GET /api/tasks/{task_id}/report`

## Main artifacts

- `uploads/{task_id}...`
- `workdir/{task_id}/unified.json`
- `workdir/{task_id}/report_payload.json`
- `outputs/{task_id}/report.docx`

## Practical debug order

1. check task status
2. inspect `unified.json`
3. inspect `report_payload.json`
4. inspect `report.docx`
