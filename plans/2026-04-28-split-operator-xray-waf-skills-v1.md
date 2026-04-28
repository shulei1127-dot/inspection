## Title

Split the first repository skill into operator + xray + waf skills

## Goal

Refine the first Agent Skills integration by splitting the current generic repository operator skill into three clearer skills:

1. `inspection-report-platform-operator`
2. `xray-report-generator`
3. `waf-report-reviewer`

The objective is better trigger precision, clearer responsibility boundaries, and a cleaner future path for additional product flows.

## Scope

In scope:

- keep `inspection-report-platform-operator` as the repo/bootstrap/runtime skill
- add `xray-report-generator`
- add `waf-report-reviewer`
- keep all skills in Agent Skills style:
  - required `SKILL.md`
  - optional `agents/openai.yaml`
  - optional `references/`
- update repository docs to describe the three-skill layout

Out of scope:

- changing startup scripts
- changing xray or WAF API behavior
- changing report generation logic
- adding a separate published skill package outside this repo in this round

## Design Notes

### Skill split rationale

`inspection-report-platform-operator` should answer:

- how to bootstrap the repo
- how to start/stop/verify local services
- how to do stack-level troubleshooting

`xray-report-generator` should answer:

- how to use xray logs with this platform
- which endpoints/pages/artifacts matter for xray
- how to debug xray-specific report generation issues

`waf-report-reviewer` should answer:

- how to run WAF preprocessing
- how to run WAF audit
- how to run WAF document-only review
- which artifacts and constraints matter for WAF

### Relationship

The three skills are parallel skills with complementary responsibilities, not one nested skill tree.

## Implementation Steps

1. Keep the existing operator skill and tighten its scope language.
2. Add `skills/xray-report-generator/`.
3. Add `skills/waf-report-reviewer/`.
4. Add compact references for each skill only where they materially help.
5. Add `agents/openai.yaml` metadata for each skill.
6. Update `README.md`.
7. Update `docs/project_status.md`.
8. Verify the resulting skill layout.

## Verification

- all three skill folders exist
- each skill has a valid-looking `SKILL.md` with frontmatter
- each skill has `agents/openai.yaml`
- repository docs mention the three-skill split

## Acceptance Criteria

- another AI agent can select a runtime/bootstrap skill separately from xray and WAF business-flow skills
- xray-specific and WAF-specific instructions are no longer mixed into one generic skill body
