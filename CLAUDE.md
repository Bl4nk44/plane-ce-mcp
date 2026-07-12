# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

plane-ce-mcp - an unofficial Python-based Model Context Protocol server that exposes Plane's project management API as MCP tools, targeting **self-hosted Plane (Community Edition)**. Built on FastMCP with the official `plane-sdk`. Supports three transport modes: stdio (local), HTTP (with OAuth or header auth), and SSE (legacy).

## Common Commands

```bash
# Install dependencies (uses uv)
uv pip install -e ".[dev]"

# Run the server locally (stdio mode)
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... python -m plane_mcp stdio

# Run HTTP server
python -m plane_mcp http

# Run all tests
pytest

# Run a single test
pytest tests/test_integration.py::test_full_integration -v

# Run tests with env vars from file
export $(cat .env.test.local | xargs) && pytest tests/ -v

# Format code (line length: 120)
ruff format plane_mcp/

# Lint (rules: E, F, I, UP, B; line length: 120)
ruff check plane_mcp/
```

## Architecture

### Entry Point & Transport Modes

`plane_mcp/__main__.py` parses a positional arg (`stdio`, `http`, or `sse`) and launches the corresponding server:
- **stdio**: Requires `PLANE_API_KEY` + `PLANE_WORKSPACE_SLUG` env vars. Runs locally.
- **http**: Starts on port 8211 with two auth endpoints - OAuth (`/oauth/mcp`) and header-based PAT (`/http/api-key/mcp`).
- **sse**: Legacy OAuth-only SSE transport.

### Server Factories (`server.py`)

Three factory functions (`get_oauth_mcp`, `get_header_mcp`, `get_stdio_mcp`) each create a `FastMCP` instance, register all tools, and configure the appropriate auth provider. OAuth/HTTP modes use Redis for token storage (falls back to in-memory).

### Client Context (`client.py`)

`get_plane_client_context()` returns a `PlaneClientContext(client, workspace_slug)` namedtuple. It resolves credentials from the MCP request context (OAuth token or header API key) or from environment variables (stdio mode). Prefers `PLANE_INTERNAL_BASE_URL` for server-to-server calls.

### Authentication (`auth/`)

- `PlaneOAuthProvider` - Full OAuth flow with token verification against the Plane API.
- `PlaneHeaderAuthProvider` - Simple header-based auth using `x-api-key` and `x-workspace-slug` headers.

### Tools (`tools/`)

19 tool modules organized by Plane domain (projects, work_items, cycles, modules, etc.), totaling 55+ tools. Each module exports a `register_*_tools(mcp: FastMCP)` function called from `tools/__init__.py`.

**Tool pattern:**
```python
def register_*_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def tool_name(param: str, optional_param: str | None = None) -> SomePlaneModel:
        """Docstring with Args and Returns sections."""
        client, workspace_slug = get_plane_client_context()
        return client.endpoint.operation(workspace_slug=workspace_slug, ...)
```

Tools return Pydantic models from `plane-sdk` and use Python 3.10+ union syntax (`str | None`).

### Testing

Integration tests in `tests/test_integration.py` use `FastMCP.Client` with `StreamableHttpTransport`. Tests run against a live Plane instance - configure via `.env.test` (copy to `.env.test.local` with real values).

## Key Environment Variables

| Variable | Required For | Purpose |
|---|---|---|
| `PLANE_API_KEY` | stdio | API key for authentication |
| `PLANE_WORKSPACE_SLUG` | stdio | Target workspace |
| `PLANE_BASE_URL` | all (default: https://api.plane.so) | Plane API URL |
| `PLANE_INTERNAL_BASE_URL` | http/sse (optional) | Internal URL for server-to-server calls |
| `REDIS_HOST` / `REDIS_PORT` | http/sse (optional) | Token storage (falls back to in-memory) |
| `PLANE_OAUTH_PROVIDER_*` | http/sse OAuth | OAuth client credentials and base URL |
| `PLANE_OAUTH_ALLOWED_REDIRECT_URIS` | http/sse OAuth (optional) | Comma-separated redirect URI patterns appended to the built-in allowlist (onboard clients without a release) |
| `LOG_USER_INFO` | all (optional, default: false) | When `true`, include user info (PII such as display name) in logs alongside the opaque user id |

## Project Mission

This is a standalone, unofficial project (originally forked from `makeplane/plane-mcp-server`, MIT - remote `upstream` kept for cherry-picks). Its purpose is to make the MCP server work reliably against a **self-hosted Plane instance (Community Edition, Docker)**. Plane Cloud is out of scope: Cloud code paths stay in place but are untested and unadvertised.

**Current phase: self-host stabilization.** Priorities, in order:
1. Critical daily-use tools work against self-host: work items (create/update/list), projects, cycles, modules, states, labels.
2. Consistent error handling and diagnosability (404/401 must produce actionable messages, not stack traces).
3. Self-host vs Cloud differences documented and handled (see `docs/plane-api-compat.md`).
4. Pages/Docs tools solid + public read-only HTTPS endpoint for external agents (Perplexity).
5. Nice-to-haves (stats, reports, extra tools) come after the above.


## Rules for New or Modified Tools

- Follow the existing tool pattern (see Tools section above). One domain per module, registered via `register_*_tools` in `tools/__init__.py`.
- Every tool that hits the Plane API must handle: 404 (missing resource OR endpoint not available on this Plane version), 401/403 (auth), timeouts. Return a clear error message naming the resource and endpoint - never let a raw SDK exception surface to the MCP client.
- Endpoint differences between Plane versions (e.g. `/work-items/` vs legacy `/issues/`, lite endpoints) are handled centrally, not with per-tool hacks. Compatibility notes and fallback strategy: `docs/plane-api-compat.md`.
- Log fallbacks when they trigger (which endpoint failed, which was used instead) so self-host issues are diagnosable from logs.
- New tool = docstring with Args/Returns + entry in README tool tables + manual check against the local self-host instance before merge.

## Prohibitions

- Do NOT change or remove existing tool signatures/behavior without a fallback path for self-host - MCP clients depend on them.
- Do NOT add dependencies without justification; pin exact versions for anything security-relevant.
- Do NOT rely on Cloud-only endpoints or features without a capability check or documented fallback.
- Do NOT merge tool changes that were not exercised against the local self-host Plane.
## Upstream Cherry-Picks

- Remote `upstream` = `makeplane/plane-mcp-server`. Review upstream changes occasionally: `git fetch upstream && git log --oneline main..upstream/main`.
- Cherry-pick generally useful fixes selectively (no wholesale merges - histories have diverged); run the self-host test checklist after every pick.
- Offering general fixes upstream as PRs is optional.

## Session Memory (memorygraph MCP - use actively)

Sessions are frequently restarted - persist important context to the memorygraph MCP
server so nothing critical is lost between sessions.

**At session start / before tackling a problem:**
- `recall_memories(query="<problem description>")` - check whether it was already
  solved or investigated. For exact names (tool, endpoint, error code) prefer
  `search_memories` with tags.

**Store during work (don't wait to be asked)** - tag every entry `plane-mcp`:
- Confirmed self-host vs Cloud API difference (also goes in `docs/plane-api-compat.md`;
  memory entry = quick pointer + verdict) → type `problem`/`solution`.
- Root cause of a non-trivial bug in a tool, auth, or the SDK → `problem` + `solution`.
- Decision made mid-work that isn't committed anywhere yet (chosen approach for
  Stage 12/13, rejected alternatives and why) → `project`.
- Working command/config specific to the local self-host instance (URLs, ports,
  test project slug) → `command`/`workflow`.
- Current work-in-progress state at the end of a session: what's done, what's next,
  which roadmap item is active → `project`.

**Do not store:** anything already in git, code, CLAUDE.md, or `docs/` (link to it
instead); secrets or API keys. Link related entries with `create_relationship`;
update stale entries with `update_memory` instead of duplicating.

## Project Docs

| File | Content |
|---|---|
| `docs/plane-api-compat.md` | Self-host vs Cloud API differences, endpoint mapping, fallback strategy |
