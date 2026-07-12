# Changelog

All notable changes to plane-ce-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [1.1.0] - 2026-07-12

Quality-hardening release (Stages 1-4 of `docs/improvement-plan.md`).

### Added

- **Toolsets**: `PLANE_TOOLSETS` env selects which tool groups to register
  (`core,comments,pages,types,planning,admin,pql` or `all`, the default).
  `core` loads ~64 tools instead of ~142 - a much smaller client context.
  New `list_toolsets` diagnostic tool.
- **Tool annotations**: every tool now carries MCP `readOnlyHint` /
  `destructiveHint` / `idempotentHint` / `openWorldHint` annotations, derived
  centrally in `plane_mcp/annotations.py`.
- **Response-size guard**: `PLANE_MAX_RESPONSE_KB` (default 1024) caps
  `list_work_items` / `list_archived_work_items` payloads; oversized responses
  return an actionable error instead of flooding the client context.
- **Retry with backoff**: transient Plane API failures are retried
  (429/503 for any call; 502/504/timeouts for read-only calls only, so a write
  that may have landed is never duplicated). `PLANE_MAX_RETRIES` (default 2),
  `PLANE_RETRY_BASE_DELAY` (default 0.5s).
- **Health probe**: unauthenticated `GET /healthz` in HTTP mode plus a Docker
  `HEALTHCHECK`. `get_instance_info` now reports `server_version`.
- **PQL resource**: the full PQL reference is exposed as the
  `resource://pql-reference` MCP resource in addition to `get_pql_reference`.
- **Docs tooling**: `scripts/check_tool_docs.py` keeps the README tool tables
  in sync with the registered tools; enforced in CI.
- **CI**: coverage gate, non-blocking pyright job, osv-scanner dependency audit,
  nightly live-integration workflow, ghcr.io Docker publish workflow.

### Changed

- Server instructions rewritten: orientation (`get_instance_info`,
  `list_toolsets`), name->UUID resolution, pagination and sparse `fields`
  guidance, PQL pointers, epics flow.
- The read-only HTTP surface (`/http/api-key-readonly/mcp`) now derives from
  tool annotations (`readOnlyHint`) instead of a name-prefix list.
- Tool-call payloads are no longer logged by default; opt in with
  `LOG_PAYLOADS=true` (they can carry PII).

### Fixed

- Dependency vulnerabilities: `pyjwt` bumped to 2.13.0 (High-severity
  GHSA-xgmm-8j9v-c9wx and four others), `python-multipart` >= 0.0.31 and
  `pydantic-settings` >= 2.14.2 forced via uv constraints. `osv-scanner`
  reports zero known vulnerabilities.

### Removed

- Upstream leftover `build-branch.yml` workflow (pushed images to the
  `makeplane` Docker Hub org); replaced by the ghcr.io publish workflow.

## [1.0.0] - 2026-07-05

First release as **plane-ce-mcp**, detached from upstream
`makeplane/plane-mcp-server` and refocused on self-hosted Plane Community
Edition: compat layer with actionable errors and lite-endpoint fallbacks,
instance capability detection, internal-API pages adapter, read-only public
surface, deploy stack (Caddy/Tailscale), PQL support.
