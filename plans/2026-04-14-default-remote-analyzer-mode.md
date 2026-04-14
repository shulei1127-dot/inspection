## Task

Make the platform default to `remote` analyzer mode.

## Goal

Complete the most important analyzer-decoupling closeout step by making the
platform prefer the standalone `log-analyzer-service` by default, while keeping
local mode available as an explicit development/testing override.

## Scope

1. Change platform default `ANALYZER_MODE` from `local` to `remote`.
2. Update environment examples and docs to reflect the new default.
3. Keep `local` mode available as an explicit override.
4. Stabilize the root test suite so it still runs without requiring a live remote analyzer.

## Implementation Plan

1. Update `app/core/config.py` default analyzer mode to `remote`.
2. Update `.env.example` and `README.md` to document:
   - `remote` is now the default runtime mode
   - `local` is still supported for explicit development/testing use
3. Add a root `tests/conftest.py` autouse fixture that pins `ANALYZER_MODE=local`
   for the platform test suite unless a test overrides it.
4. Add a targeted test that verifies the actual configuration default remains `remote`
   when the environment variable is not set.
5. Update `docs/project_status.md`.

## Non-Goals

- no parser changes
- no platform workflow redesign
- no second product placeholder work
- no change to analyzer service defaults
