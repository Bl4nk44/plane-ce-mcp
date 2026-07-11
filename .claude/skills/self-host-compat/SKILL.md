---
name: self-host-compat
description: Use when debugging 404/401/500 errors against self-hosted Plane, or when a tool works on Cloud but fails on Community Edition — endpoint mapping, capability checks, fallback strategy.
---

# Self-host vs Cloud compatibility

Use when a tool fails against the self-hosted Plane instance (Docker CE) or behaves
differently than on Cloud.

## Diagnosis order

1. Reproduce with a direct API call (curl with the same PAT) against
   `PLANE_BASE_URL` — isolates SDK/MCP from the Plane API itself:
   ```bash
   curl -s -H "x-api-key: $PLANE_API_KEY" \
     "$PLANE_BASE_URL/api/v1/workspaces/$PLANE_WORKSPACE_SLUG/projects/" | head
   ```
2. 404 → decide: missing resource vs endpoint not in this Plane version. Check the
   response body shape (JSON Plane error = resource; HTML/generic = endpoint).
3. 401/403 → verify PAT validity and workspace slug; check whether the endpoint needs
   a role the token's user lacks.
4. Feature-gated (initiatives, intake, types/properties)? Check `get_features` /
   workspace features — CE may have it disabled.
5. Record the finding in `docs/plane-api-compat.md` (known differences table) —
   every confirmed difference gets a row.

## Fixing

- Fallbacks (e.g. `/work-items/` → legacy `/issues/`) belong in the shared
  compatibility layer, logged at WARNING. Never patch a single tool silently.
- If the fix is generally useful (not a self-host hack), plan an upstream PR.
- After fixing: run the relevant section of `docs/self-host-testing.md` against the
  local instance.

## Auth model (this fork)

Primary: PAT — env `PLANE_API_KEY` + `PLANE_WORKSPACE_SLUG` (stdio) or headers
`x-api-key` + `x-workspace-slug` (HTTP `/http/api-key/mcp`). OAuth is secondary;
self-host workflows must not depend on it.
