# Plane API compatibility — self-host vs Cloud

Living document. Record every self-host vs Cloud difference discovered here, with the
Plane version it applies to. Tools must consult this before assuming an endpoint exists.

## Environments

| Profile | Base URL | Auth | Notes |
|---|---|---|---|
| Self-host CE (primary target) | `PLANE_BASE_URL` → local Docker instance | PAT (`x-api-key`) or env `PLANE_API_KEY` | API version depends on the deployed Plane release |
| Plane Cloud | `https://api.plane.so` | PAT or OAuth | Always latest API |

`PLANE_INTERNAL_BASE_URL` is preferred over `PLANE_BASE_URL` for server-to-server calls
(see `plane_mcp/client.py`).

## Known differences / issues

> Fill in as verified against the local instance. Format: symptom, affected endpoint,
> Plane versions, workaround/fallback.

| # | Symptom | Endpoint | Affects | Status |
|---|---|---|---|---|
| 1 | 404 on `/work-items/` paths | `/api/v1/workspaces/{ws}/projects/{p}/work-items/` | Older self-host releases expose legacy `/issues/` only | TO VERIFY on local instance |
| 2 | Cloud-only features (initiatives, intake, some work-item-type ops) may be disabled in CE | various | CE feature flags | TO VERIFY — check `get_features` |

## Fallback strategy

1. Call the current endpoint first (what `plane-sdk` uses).
2. On 404 that looks like a missing *endpoint* (not a missing resource), fall back to the
   legacy path where one exists.
3. Log every fallback at WARNING with: tool name, failed endpoint, endpoint used instead.
4. Fallbacks live in a shared compatibility layer (planned, Stage 5) — never inline in
   individual tools.

Distinguishing "resource not found" from "endpoint not available": a missing endpoint
typically 404s with an HTML or generic body; a missing resource returns the Plane JSON
error shape. Verify and document the exact difference here once observed.

## Version matrix

| Plane release (self-host) | work-items path | lite endpoints | Notes |
|---|---|---|---|
| (local instance version here) | ? | ? | |
