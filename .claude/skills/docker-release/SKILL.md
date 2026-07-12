---
name: docker-release
description: Use when building the Docker image, changing the Dockerfile, tagging a release, or deploying the MCP server container alongside self-hosted Plane.
---

# Docker build & release

## Build & run

```bash
docker build -t plane-ce-mcp:dev .

# HTTP transport (default CMD), port 8211
docker run --rm -p 8211:8211 \
  -e PLANE_BASE_URL=http://<self-host-plane>:<port> \
  plane-ce-mcp:dev
```

Image: `python:3.11-slim`, deps installed with `uv pip install --system`. Default
transport: streamable-http; override CMD with `stdio`/`sse` if needed.

## Rules

- Tags: `dev` for local work, `vX.Y.Z` matching `pyproject.toml` version for releases.
- Dockerfile changes → run `checkov` on it (global security workflow) and rebuild +
  smoke test: container starts, `/http/api-key/mcp` responds with valid headers.
- When the MCP container runs next to the Plane compose stack, prefer
  `PLANE_INTERNAL_BASE_URL` pointing at Plane's internal service name (skips proxy).
- Redis env (`REDIS_HOST`/`REDIS_PORT`) only matters for OAuth token storage —
  header-auth/PAT mode works without it (in-memory fallback).
- Before pushing a release image: green CI + `docs/self-host-testing.md` core
  checklist passed against the local instance.
- Rollback = redeploy the previous version tag; never overwrite an existing version tag.
