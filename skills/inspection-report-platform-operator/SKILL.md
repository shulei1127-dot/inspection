---
name: inspection-report-platform-operator
description: Bootstrap, start, stop, verify, and troubleshoot the inspection-report-platform repository runtime. Use when an AI agent needs to prepare the local environment, start the required services, inspect local health, or recover the stack before handing off to xray or WAF business-flow skills.
---

# Inspection Report Platform Operator

Use this skill when the repository already exists locally and the goal is to run or troubleshoot the platform runtime rather than edit its business logic.

## Core Workflow

1. Run `scripts/bootstrap_local_env.sh` once to create `.venv`, install dependencies, and create `.env` when missing.
2. Review `.env` only as needed.
   - The platform works in base mode without any LLM key.
   - LLM summary features activate only when the corresponding env vars are configured.
3. Run `scripts/start_local_stack.sh`.
4. Run `scripts/verify_local_stack.sh`.
5. Hand off to the xray or WAF flow that the user actually wants.

## Local Entry Points

- xray report generation: `/xray`
- WAF preprocessing: `/waf`
- WAF audits: `/waf-audits/ui`

The exact host port comes from `.env` or the value printed by `scripts/start_local_stack.sh`.

Prefer the built-in pages when the user wants a manual browser workflow.
Prefer direct API calls when the user already provided local file paths and wants automation.

## Scope Boundary

This skill is the runtime/bootstrap skill.

Use the xray-specific or WAF-specific companion skills for business-flow execution once the stack is healthy.

## LLM Boundary

- Do not assume LLM is enabled.
- Do not hardcode API keys into scripts or task instructions.
- If the user wants LLM-enhanced xray or WAF summaries, configure `.env`, restart the stack, and then rerun the target flow.

## Troubleshooting

Read `references/troubleshooting.md` when:

- analyzer looks stale or does not match the latest code
- Carbone render fails
- a task produced `completed` instead of `rendered`
- a generated DOCX contains too many empty fields

Read `references/flows.md` when you need the exact local page/API mapping and artifact expectations for xray and WAF.
