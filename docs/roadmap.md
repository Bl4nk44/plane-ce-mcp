# Roadmap — Plane MCP Server Fork (self-host stabilization)

Goal: a fork of `makeplane/plane-mcp-server` that "always works" against a self-hosted
Plane (Community Edition, Docker) and stays Cloud-compatible. Stages below are a
checklist; keep it updated as work lands.

## Stage 1 — Project & requirements audit
- [x] Identify stack: Python 3.10+, FastMCP 3.2.0, plane-sdk 0.2.19, uv, Docker.
- [x] Map repo structure (see CLAUDE.md Architecture).
- [x] List tools actually needed daily; mark which must be bulletproof.
      (2026-07-12, per user: basic read/write/edit — daily information capture and
      retrieval. Bulletproof tier: work items create/list/retrieve/update,
      projects list/retrieve, comments, states, labels. Second tier: cycles,
      modules, members. Pages would fit the "information storage" use case but
      are blocked on CE — see Stage 12.)
- [x] Catalog known self-host breakages (404s, auth issues, broken tools) in
      `docs/plane-api-compat.md` — verified against local CE v1.3.1 (2026-07-11):
      pages/issue-types/initiatives/estimates APIs missing; core CRUD OK.

## Stage 2 — Claude Code harness
- [x] Extend CLAUDE.md with fork mission, tool rules, prohibitions, upstream sync.
- [x] `.claude/skills/`: plane-tool-editor, self-host-compat, docker-release, commit-style.
- [x] `.claude/settings.json` with project permissions.

## Stage 3 — Local environment & CI
- [x] CI workflow: ruff check + format + unit tests on PR/push (`.github/workflows/ci.yml`).
- [x] Runtime `.env.example` (currently only `.env.test` exists). (2026-07-11)
- [ ] Rule: no merge without green CI.
- [ ] Optional: integration test job gated by repo secrets pointing at a test Plane instance.

## Stage 4 — Functional spec of MCP behavior
- [ ] Per critical tool: expected input/output/errors, edge cases (404, timeout, bad data).
- [ ] Map each tool to Plane API endpoints + minimum Plane version.

## Stage 5 — Self-host compatibility
- [x] Central compatibility layer (shared wrapper, not per-tool hacks) for endpoint
      differences (`/work-items/` vs legacy `/issues/`, lite endpoints).
      (2026-07-11: `plane_mcp/compat.py` — client proxy via `wrap_client()`, all SDK
      errors → actionable ToolErrors; `/work-items/` works on CE 1.3.1, no legacy
      fallback needed yet.)
- [x] Fallback strategy: try current endpoint, fall back to legacy, log the fallback.
      (2026-07-11: `FALLBACKS` registry — 5 lite endpoints missing on CE 1.3.1 fall
      back to full endpoints with response re-shaping; WARNING logged. Verified live:
      list_projects, list_cycles, list_modules, get_project_members,
      get_workspace_members all work on CE.)
- [x] Capability detection / env profile for self-host vs Cloud.
      (2026-07-12: `fetch_instance_profile()`/`describe_instance()` in compat.py —
      unauthenticated `GET /api/instances/`, cached; new `get_instance_info` tool
      reports edition/version + known CE limitations so agents learn gaps up-front
      instead of via 404s. Verified live on CE 1.3.1.)

## Stage 6 — Auth & sessions
- [x] Primary mode: PAT via `x-api-key` + `x-workspace-slug` (and stdio env vars).
      OAuth is secondary; do not depend on it for self-host workflows.
      (2026-07-11: HTTP mode no longer requires OAuth env — without
      `PLANE_OAUTH_PROVIDER_CLIENT_ID` it serves header-auth only at `/http/api-key/mcp`.)
- [ ] Clear error reporting for invalid key / missing workspace / expired token.

## Stage 7 — Docker / deployment
- [ ] Image tagging convention (dev/prod), compose service definition, healthcheck.
- [ ] Rollout/rollback procedure documented.

## Stage 8 — Tool refactoring
- [ ] Unified error handling / logging / retry style across tool modules.
- [ ] Remove dead code and legacy paths that only cause confusion.

## Stage 9 — Functional testing & dev UX
- [ ] Manual checklist per release: `docs/self-host-testing.md`.
- [ ] Scripts for common flows (e.g. smoke test against self-host).

## Stage 10 — Documentation
- [x] `docs/` skeleton (this file, plane-api-compat, self-host-testing).
- [x] README note: fork stabilized for self-host. (2026-07-11)
- [ ] Upstream issues/PRs for fixes that are generally useful.

## Stage 11 — Upstream sync & maintenance
- [x] `upstream` remote added.
- [ ] Monthly: `git fetch upstream && git log --oneline main..upstream/main`, merge
      selectively, run self-host checklist after sync.
- [ ] Periodic review of CLAUDE.md + `.claude/` (keep lean, prune stale rules).

## Stage 12 — Plane Pages/Docs tools (priority: Perplexity will query these)

Existing tools in `plane_mcp/tools/pages.py`: `list_pages`, `retrieve_page`,
`create_page`, `list_work_item_pages`, `attach_page_to_work_item`,
`detach_page_from_work_item`. Gap analysis below is against those.

- [x] E12.1 — Verify Pages endpoints on the local self-host instance
      (workspace pages, project pages, page detail); record availability and any
      version/feature gating in `docs/plane-api-compat.md`.
      (2026-07-11: CE v1.3.1 has NO public Pages API — all `/api/v1/.../pages/`
      paths 404; pages exist only behind the session-auth internal API. Stage 12
      blocked until Plane ships the public API or we add an internal-API adapter.)
- [x] E12.2 — Verify existing tools (`list_pages`, `retrieve_page`,
      `list_work_item_pages`) against self-host; fix what 404s.
      (2026-07-12: internal-API adapter `plane_mcp/internal_api.py` — session
      sign-in + read-only project-pages routes, wired as compat fallbacks for
      `pages.list_project_pages`/`pages.retrieve_project_page`. Set
      `PLANE_INTERNAL_API_EMAIL`/`PASSWORD` to enable; happy path pending live
      verification with a real account. Workspace pages: no CE equivalent.)
- [ ] E12.3 — Add content truncation to `retrieve_page`: `max_length` param
      (env default `PLANE_PAGES_MAX_CONTENT_LENGTH`), response flags truncation.
      Page bodies can be large — external agents need bounded output.
- [ ] E12.4 — Add `search_pages`: full-text via Plane API if supported, otherwise
      client-side title/content filter over `list_pages`.
- [ ] E12.5 — Output format review: title, content, project, timestamps — easy for
      an external agent (Perplexity) to interpret.
- [ ] E12.6 — Test Pages tools locally (curl + Claude Code), extend
      `docs/self-host-testing.md` with a Pages section.

## Stage 13 — Remote HTTP endpoint for Perplexity (external agents)

Server already ships OAuth (`PlaneOAuthProvider`, `/oauth/mcp`) and PAT header auth
(`/http/api-key/mcp`). Strategy: internal clients (Claude Code, Cursor) keep PAT;
Perplexity gets a public HTTPS endpoint with Bearer/OAuth.

- [ ] E13.1 — HTTPS in front of the MCP container: Caddy or Nginx TLS terminator in
      compose, public URL e.g. `https://plane-mcp.<domain>/mcp`.
      (2026-07-12: `deploy/` ready — docker-compose.yml [mcp + caddy, healthcheck],
      Caddyfile [auto-TLS, only MCP routes exposed], `.env.deploy.example` with
      `MCP_PUBLIC_DOMAIN`. Remaining: pick the domain, point DNS at the host,
      `docker compose up -d --build`, then live TLS check.)
- [ ] E13.2 — Auth for Perplexity Remote Connector — decide and implement ONE:
      (a) reuse existing OAuth provider (check Perplexity redirect URI, add to
      `PLANE_OAUTH_ALLOWED_REDIRECT_URIS`), or
      (b) minimal `/oauth/token` Client Credentials endpoint issuing a short-lived
      Bearer (TTL ~1h) mapped 1:1 to a PAT — no full OIDC.
- [ ] E13.3 — Test with curl: obtain token, list tools on `/mcp` with Bearer.
- [ ] E13.4 — Read-only tool surface for external agents: expose only `list_*` /
      `retrieve_*` / `search_*` (no `create_*`/`update_*`/`delete_*`) on the public
      endpoint — chat must not mutate Plane data accidentally.
- [ ] E13.5 — Add Custom Remote Connector in Perplexity (Settings → Connectors),
      verify end-to-end: question in Perplexity → data from Plane
      (`list_pages`, `retrieve_page`, `list_work_items`).
- [ ] E13.6 — Document: `docs/auth.md` (token strategy, TTL) and
      `docs/perplexity-integration.md` (URL schema, env vars, connector setup);
      README section "Perplexity integration".
- [ ] E13.7 — New env vars in `.env.example`:
      `MCP_PUBLIC_BASE_URL`, `MCP_OAUTH_CLIENT_ID`, `MCP_OAUTH_CLIENT_SECRET`,
      `MCP_OAUTH_TOKEN_TTL`, `PLANE_PAGES_MAX_CONTENT_LENGTH`.
