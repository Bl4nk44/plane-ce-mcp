# plane-ce-mcp Improvement Plan

Quality-hardening roadmap. Goal: make this server materially more reliable and
pleasant to run against self-hosted Plane CE than the upstream official server.
Baseline analysis: 2026-07-12.

Each task ships as its own PR, target diff <= 150 lines (see CLAUDE.md).
Priority order by impact: Stage 1 > Stage 2 > Stage 3 > Stage 4.

## Baseline audit findings

Solid foundation already present: compat proxy (`compat.py`) classifying errors
into actionable ToolErrors, lite->full endpoint fallbacks, instance capability
detection, read-only tool surface, CI with lint + unit tests, JSON structured
logging with PII gating.

Gaps found:

| # | Area | Problem |
|---|------|---------|
| 1 | Context | ~190 tools, all always registered. Every MCP client loads every tool definition into context - kills Claude/Cursor sessions. No toolset filtering. |
| 2 | Safety metadata | Zero tool annotations (`readOnlyHint`/`destructiveHint`/`idempotentHint`). Clients cannot tell safe from destructive. Read-only surface keys off a brittle name prefix. |
| 3 | Response size | Only pages truncate. `list_work_items` with `description_html` can dump megabytes into client context. |
| 4 | Reliability | No retry/backoff. 429/5xx/timeout = immediate fail. |
| 5 | Version drift | CI skips `test_integration.py` (needs live Plane). Plane CE version drift - the root cause of "official server doesn't work" - only caught by hand. |
| 6 | Test coverage | Tools themselves untested (compat/auth/internal are). No type checker in CI. |
| 7 | Logging | `include_payloads=True` hardcoded despite a `LOG_USER_INFO` flag existing. Full payloads always logged. |
| 8 | Ops | No `/healthz`, no Docker `HEALTHCHECK`. |
| 9 | Deps | `fakeredis` pin comment cites "fastmcp 2.14.4" but pin is `fastmcp==3.2.0` - stale, needs re-check. |
| 10 | DX | `SERVER_INSTRUCTIONS` covers only epics. No pagination/PQL/flow guidance. |
| 11 | Docs drift | README tool tables hand-maintained against ~190 tools. |

## Stage 1 - Client context (biggest win)

- **1.1 Toolsets.** `PLANE_TOOLSETS` env (comma-separated, e.g. `core,pages,admin`).
  Conditional module registration. Default = sensible core set; `all` for everything.
  A `list_toolsets`-style diagnostic so users see what is active.
- **1.2 Annotations.** `readOnlyHint`/`destructiveHint`/`idempotentHint` on every tool.
- **1.3 Read-only surface** switches from name-prefix matching to `readOnlyHint`.
- **1.4 Response size limits.** Uniform truncation for list tools + `total_count`
  + hint to narrow with `fields`/`per_page`. Sensible default sparse fieldset.

## Stage 2 - Reliability (done)

- **2.1 Retry with backoff** - DONE. `retry.py`: 429/503 retried for any call,
  502/504/timeouts for read-only ops only (a write may have landed). Exponential
  backoff + jitter. Env: `PLANE_MAX_RETRIES`, `PLANE_RETRY_BASE_DELAY`.
- **2.2 Integration CI** - DONE. `nightly-integration.yml` runs the live suite
  against a persistent self-host instance (secrets, self-skips when absent).
  Booting a full Plane CE stack in Actions was rejected as too flaky/heavy.
  TODO: version matrix as new CE releases land.
- **2.3 Tool unit tests** - STARTED. In-memory FastMCP client + fake SDK pattern
  (`tests/test_tools_work_items.py`). Coverage gate at 53% (`--cov-fail-under`).
  TODO: extend the pattern to the remaining tool modules and raise the floor.
- **2.4 Pyright in CI** - DONE (non-blocking). Baseline has ~27 plane-sdk
  call-signature false positives; job runs `continue-on-error` until triaged.
  New modules (retry/response/annotations) are pyright-clean.

## Stage 3 - Security / ops

- **3.1** `LOG_PAYLOADS` env (default false); PII audit of logs.
- **3.2** `/healthz` endpoint + Docker `HEALTHCHECK`; server version in `get_instance_info`.
- **3.3** Dependency audit: verify fakeredis pin, add `osv-scanner` to CI.

## Stage 4 - DX / distribution

- **4.1** Expand `SERVER_INSTRUCTIONS` (pagination, PQL quickstart, common flows).
  PQL reference as an MCP resource rather than a tool.
- **4.2** Script generating README tool tables from the registry + CI drift check.
- **4.3** Release: PyPI (`uvx plane-ce-mcp`), ghcr.io image, CHANGELOG, MCP registry entry.
