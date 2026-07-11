# Perplexity integration (Custom Remote Connector)

Working setup verified 2026-07-12 against the production deployment
(`docs/tailscale-deployment.md`).

## Connector settings

Perplexity → Account settings → Connectors → **+ Custom connector** → Remote:

| Field | Value |
|---|---|
| MCP Server URL | `https://ubuntu.<tailnet>.ts.net:8443/http/api-key-readonly/mcp` |
| Authentication | **API Key** — paste a Plane Personal Access Token |
| Transport | Streamable HTTP |
| Network access | Public |

Leave the OAuth Client ID/Secret fields empty (they apply only to the OAuth
auth mode, which this deployment does not use).

## How auth works

Perplexity's "API Key" mode sends only the key itself (as a bearer token) —
there is no way to attach custom headers. The server therefore resolves the
workspace from its own `PLANE_WORKSPACE_SLUG` environment variable when the
`x-workspace-slug` header is absent (introduced for exactly this client).
Multi-header clients (Claude Code, Cursor, custom agents) keep overriding the
workspace per request via the header.

## What Perplexity can reach

The public endpoint is the **read-only surface** (E13.4): 59 `list_*` /
`retrieve_*` / `get_*` / `count_*` / `search_*` / `read_*` tools, zero
mutating tools. A leaked PAT through this endpoint cannot create, update or
delete anything in Plane — and the full endpoint is not reachable from the
public internet at all (only through the tailnet).

On Community Edition, pages/epics/initiatives/estimates/milestones need the
internal-API adapter (`docs/plane-api-compat.md` §Internal-API adapter);
without `PLANE_INTERNAL_API_EMAIL`/`PASSWORD` on the server, pages tools
return a clear message and agents report the gap via `get_instance_info`.

## Reference

- Perplexity docs: https://www.perplexity.ai/help-center/en/articles/13915507-adding-custom-remote-connectors
- Perplexity OAuth redirect (only if OAuth mode is ever adopted):
  `https://www.perplexity.ai/rest/connections/oauth_callback`
