## Title

Local stack scripts + first Agent Skill v1

## Goal

Make the repository easier for other people and AI agents to bootstrap locally by:

1. adding one standard local bootstrap/start/stop/verify script set
2. adding one first-pass Agent Skills compatible skill that explains how to run xray and WAF flows on top of this repository

This round focuses on repository ergonomics and reusable operations, not new business parsing or report logic.

## Scope

In scope:

- add standard local stack scripts under `scripts/`
- keep the scripts aligned with the current repository runtime:
  - FastAPI platform
  - standalone `log-analyzer-service`
  - Carbone runtime
  - optional Mermaid renderer left out of the mandatory stack
- add a first repository-local skill in Agent Skills style
- update README and project status for the new bootstrap flow

Out of scope:

- changing xray or WAF report logic
- changing analyzer contracts
- adding a new deployment target
- forcing LLM to be enabled
- packaging the whole system as Docker Compose in this round

## Design Notes

### Standard local stack

This round will add a small four-script set:

- `scripts/bootstrap_local_env.sh`
- `scripts/start_local_stack.sh`
- `scripts/stop_local_stack.sh`
- `scripts/verify_local_stack.sh`

The scripts should:

- work from repository root
- default to the current local port conventions where reasonable
- write runtime state into one repo-local runtime directory instead of relying on terminal memory
- remain safe when LLM env vars are absent

### Runtime boundary

Mandatory local stack for this round:

- platform FastAPI app
- `log-analyzer-service`
- Carbone container

Optional / not forced in this round:

- Mermaid renderer service
- external LLM configuration

### LLM behavior

The new scripts and skill must clearly document:

- the project works in base mode without any LLM key
- xray/WAF LLM enhancements only activate when the corresponding env vars are configured
- skill instructions must never hardcode secret keys

### Skill shape

The first skill will follow the Agent Skills style:

- one required `SKILL.md`
- optional `references/`
- no extra clutter docs inside the skill folder

It should teach an AI agent how to:

- bootstrap the repo
- start and verify the local stack
- run xray report generation
- run WAF preprocessing / audit / document-only review
- distinguish base mode from LLM-enhanced mode

## Implementation Steps

1. Inspect current startup/runtime expectations in README, existing scripts, and analyzer docs.
2. Add a repo-local runtime directory convention and ignore it in git if needed.
3. Implement `bootstrap_local_env.sh`.
4. Implement `start_local_stack.sh`.
5. Implement `stop_local_stack.sh`.
6. Implement `verify_local_stack.sh`.
7. Create the first Agent Skills compatible skill folder and `SKILL.md`.
8. Add one or two compact reference files only if they materially help the skill.
9. Update `README.md`.
10. Update `docs/project_status.md`.
11. Run shell syntax checks and targeted local verification.

## Verification

Minimum verification for this round:

- `bash -n` passes for all new shell scripts
- `scripts/bootstrap_local_env.sh --help` or equivalent safe invocation works if a help mode is added
- `scripts/start_local_stack.sh` can be reviewed for expected commands and path handling
- `scripts/verify_local_stack.sh` validates:
  - platform `/health`
  - analyzer `/health`
  - Carbone `/status`
- skill files exist and follow the expected folder layout

## Acceptance Criteria

- another engineer can discover one standard script path for bootstrap/start/stop/verify
- another AI agent can read the first skill and understand how to operate xray and WAF flows in this repository
- the repository docs explicitly explain that LLM is optional and configuration-driven
