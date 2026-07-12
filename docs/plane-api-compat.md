# Plane API compatibility - self-host vs Cloud

Living document. Record every self-host vs Cloud difference discovered here, with the
Plane version it applies to. Tools must consult this before assuming an endpoint exists.
Since the rebrand to plane-ce-mcp, self-host CE is the only supported target - the
Cloud column stays as historical/comparison reference, not a maintained target.

## Environments

| Profile | Base URL | Auth | Notes |
|---|---|---|---|
| Self-host CE (primary target) | `PLANE_BASE_URL` → local Docker instance | PAT (`x-api-key`) or env `PLANE_API_KEY` | API version depends on the deployed Plane release |
| Plane Cloud | `https://api.plane.so` | PAT or OAuth | Always latest API |

`PLANE_INTERNAL_BASE_URL` is preferred over `PLANE_BASE_URL` for server-to-server calls
(see `plane_mcp/client.py`).

## Known differences / issues

Verified 2026-07-11 against local self-host **Plane CE v1.3.1** (`edition: PLANE_COMMUNITY`,
`http://192.168.178.22:8800`, workspace `projekty`, PAT auth via `x-api-key`).

| # | Symptom | Endpoint | Affects | Status |
|---|---|---|---|---|
| 1 | 404 on `/work-items/` paths | `/api/v1/workspaces/{ws}/projects/{p}/work-items/` | Older self-host releases | **NOT an issue on CE 1.3.1** - both `/work-items/` and legacy `/issues/` return 200 |
| 2 | Pages API missing | `/api/v1/workspaces/{ws}/pages/` and `.../projects/{p}/pages/` | CE 1.3.1 | **CONFIRMED 404, HANDLED (project pages, read-only)** - internal-API adapter (`plane_mcp/internal_api.py`): session sign-in with `PLANE_INTERNAL_API_EMAIL`/`PASSWORD`, fallback wired for `pages.list_project_pages` and `pages.retrieve_project_page`. Workspace-level pages have no internal equivalent on CE (project-scoped only). Without credentials the tools return an actionable message naming the env vars |
| 3 | Work item types API missing | `.../projects/{p}/issue-types/` | CE 1.3.1 | **CONFIRMED 404** - EE/Cloud feature. `resolve_work_item_type` / Epic-by-type flows won't work on CE |
| 4 | Initiatives API missing | `/api/v1/workspaces/{ws}/initiatives/` | CE 1.3.1 | **CONFIRMED 404** - EE/Cloud feature |
| 5 | Estimates API missing | `.../projects/{p}/estimates/` | CE 1.3.1 | **CONFIRMED 404** |
| 6 | Features/capability endpoint missing | `/api/v1/workspaces/{ws}/features/` | CE 1.3.1 | **CONFIRMED 404** - capability detection cannot rely on a features endpoint; probe target endpoints directly |
| 7 | Lite endpoints missing (SDK `list_lite`/`get_members_lite`) | `/projects-lite/`, `/cycles-lite/`, `/modules-lite/`, `/project-members-lite/`, `/members-lite/` | CE 1.3.1 | **CONFIRMED 404, HANDLED** - compat layer (`plane_mcp/compat.py` `FALLBACKS`) transparently falls back to the full endpoints and re-shapes the response into the lite models; fallback logged at WARNING |
| 8 | Milestones API missing | `.../projects/{p}/milestones/` (`milestones.create` 404) | CE 1.3.1 | **CONFIRMED 404** - EE/Cloud feature; integration test skips the milestone flow on CE |

Verified working on CE 1.3.1 (200): `projects`, `work-items`, legacy `issues`, `states`,
`labels`, `cycles`, `modules`, `intake-issues`, workspace `members`, project `members`.

Instance metadata (no auth): `GET /api/instances/` → `instance.current_version`,
`instance.edition` - usable for capability profiling.

## Fallback strategy (implemented - `plane_mcp/compat.py`)

The boundary is `wrap_client()`: `get_plane_client_context()` returns the SDK client
wrapped in a proxy (`CompatClientProxy`) so every SDK call passes through the compat
layer. FastMCP catches tool exceptions below its middleware, so a middleware cannot do
this - the client proxy is the only central point that works.

1. Call the current endpoint first (what `plane-sdk` uses).
2. On 404 classified as missing *endpoint* (not missing resource), consult the
   `FALLBACKS` registry (operation path → handler, e.g. `projects.list_lite` →
   full `projects.list` + envelope conversion). No registered fallback → clear
   ToolError pointing at this document.
3. Every fallback is logged at WARNING (JSON log: operation, workspace slug).
4. All other SDK errors (401/403, timeouts, other HTTP) are translated into
   actionable ToolError messages - raw SDK exceptions never reach an MCP client.
5. Fallbacks live only in `plane_mcp/compat.py` - never inline in individual tools.

Distinguishing "resource not found" from "endpoint not available" (verified on CE 1.3.1 -
both are `404` + `application/json`, differ only in body text):

- Missing **endpoint** (route not in this edition/version): `{"error": "Page not found."}`
- Missing **resource** (route exists, id doesn't): `{"error":"The requested resource does not exist."}`

The compatibility layer should match on the error message text to decide whether a
fallback (legacy path) is worth attempting.

## Internal-API adapter (pages on CE)

Routes pinned from Plane v1.3.1 sources (`apps/api/plane/authentication/urls.py`,
`apps/api/plane/app/urls/page.py`) and verified against the local instance:

- Auth: `GET /auth/get-csrf-token/` (csrftoken cookie + JSON token), then
  `POST /auth/sign-in/` (form: email, password, csrfmiddlewaretoken; Referer
  header required) → redirect + session cookie; `GET /api/users/me/` confirms.
  Failed sign-in redirects with `error_code` query params.
- Pages (project-scoped only on CE): `GET /api/workspaces/{slug}/projects/{pid}/pages/`
  (list) and `.../pages/{page_id}/` (detail, `PageDetailSerializer` incl.
  `description_html`; pass `track_visit=false`). The separate
  `.../description/` endpoint streams the yjs **binary** - not useful for text.
- The internal API is not a stable contract: re-verify these routes after every
  Plane upgrade (they are exercised by `tests/test_internal_api.py` against
  mocked responses and by the manual checklist against the live instance).

## Version matrix

| Plane release (self-host) | work-items path | legacy `/issues/` | pages API | issue-types | initiatives | Notes |
|---|---|---|---|---|---|---|
| CE v1.3.1 (local, 2026-07-11) | ✅ 200 | ✅ 200 | ❌ 404 | ❌ 404 | ❌ 404 | Pages only via internal session-auth API |
