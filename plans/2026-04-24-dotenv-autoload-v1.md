# Dotenv Autoload v1

## Goal

Allow the platform to read configuration from a local `.env` file so everyday
development no longer requires a long list of manual `export` commands before
starting the service.

## Scope

1. Add minimal `.env` file loading to the current config layer.
2. Keep existing environment-variable precedence:
   - explicit shell `export` wins
   - `.env` acts as fallback
   - hard-coded defaults remain last
3. Do not introduce a new third-party dependency just for dotenv loading.
4. Keep the change local to config loading; do not refactor service startup.
5. Add focused tests for:
   - loading values from `.env`
   - shell env overriding `.env`
6. Sync README with the new startup workflow.

## Notes

- Default dotenv path: `.env` in the current project root.
- Optional override: `ENV_FILE=/custom/path/.env`
- Supported line shape for v1:
  - `KEY=value`
  - blank lines
  - `# comments`
  - quoted values with single or double quotes

## Out of Scope

- layered dotenv files such as `.env.local` / `.env.prod`
- secret management
- runtime hot reload of changed `.env`
