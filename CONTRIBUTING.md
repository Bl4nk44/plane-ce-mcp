# Contributing to plane-ce-mcp

Thanks for your interest in contributing! This is an unofficial, community-maintained
MCP server for self-hosted Plane (Community Edition).

## Reporting issues

Before opening a new issue, search the
[issues](https://github.com/Bl4nk44/plane-ce-mcp/issues) tab - it may already be
known. When reporting a bug, include:

- Your Plane edition and version (`get_instance_info` tool output helps)
- The transport used (stdio / HTTP PAT / OAuth)
- The exact tool call and the error message returned
- A minimal reproduction where possible

Self-hosted CE quirks are the core focus of this project - reports of endpoints that
behave differently on CE vs what the SDK expects are especially valuable.

## Development setup

```bash
git clone https://github.com/Bl4nk44/plane-ce-mcp.git
cd plane-ce-mcp
uv pip install -e ".[dev]"
```

Run the server locally:

```bash
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... PLANE_BASE_URL=... python -m plane_mcp stdio
```

## Before submitting a PR

1. `ruff format plane_mcp/` and `ruff check plane_mcp/` pass (line length 120).
2. `pytest` passes. Integration tests need a live Plane instance - see
   `.env.test` and [docs/self-host-testing.md](docs/self-host-testing.md).
3. Tool changes were exercised against a self-hosted CE instance
   (checklist: [docs/self-host-testing.md](docs/self-host-testing.md)).
4. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat(scope):`, `fix(scope):`, `docs:`, ...).
5. Keep PRs small and focused - one logical change per PR.

## Rules for new or modified tools

- Follow the existing tool pattern: one domain per module in `plane_mcp/tools/`,
  registered via `register_*_tools` in `tools/__init__.py`.
- Every tool must handle 404 / 401 / 403 / timeouts through the compat layer
  (`plane_mcp/compat.py`) - never let a raw SDK exception reach the MCP client.
- Endpoint differences between Plane versions are handled centrally, not with
  per-tool hacks - see [docs/plane-api-compat.md](docs/plane-api-compat.md).
- New tool = docstring with Args/Returns + entry in the README tool tables.
- Do not change existing tool signatures without a fallback path - MCP clients
  depend on them.

## Questions

Open a [discussion or issue](https://github.com/Bl4nk44/plane-ce-mcp/issues) on GitHub.
