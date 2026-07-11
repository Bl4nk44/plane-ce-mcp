---
name: plane-tool-editor
description: Use when adding, modifying, or removing MCP tools in plane_mcp/tools/ — enforces the tool pattern, error handling, self-host fallback rules, and registration steps for this repo.
---

# Plane MCP Tool Editor

Use for any change to a tool in `plane_mcp/tools/` or a new tool module.

## Adding a tool

1. Pick the domain module in `plane_mcp/tools/` (one Plane domain per module). New
   domain → new module exporting `register_<domain>_tools(mcp: FastMCP)`.
2. Follow the exact pattern:

```python
@mcp.tool()
def tool_name(param: str, optional_param: str | None = None) -> SomePlaneModel:
    """One-line summary.

    Args:
        param: ...
    Returns:
        ...
    """
    client, workspace_slug = get_plane_client_context()
    return client.endpoint.operation(workspace_slug=workspace_slug, ...)
```

3. Python 3.10+ union syntax (`str | None`), return `plane-sdk` Pydantic models.
4. New module → register it in `plane_mcp/tools/__init__.py`.
5. Update the README "Available Tools" table.
6. Verify against the local self-host instance (`docs/self-host-testing.md`).

## Error handling (mandatory)

- Never let a raw SDK exception reach the MCP client. Catch API errors and raise/return
  a message naming the tool, resource, and endpoint.
- 404: distinguish missing resource vs endpoint unavailable on this Plane version —
  consult and update `docs/plane-api-compat.md`.
- Endpoint version differences go in the shared compatibility layer (Stage 5 of
  `docs/roadmap.md`), never inline per-tool.
- Log triggered fallbacks at WARNING (tool, failed endpoint, endpoint used).

## Changing an existing tool

- Signature/behavior changes need a fallback path — MCP clients depend on current
  behavior (see CLAUDE.md Prohibitions).
- Run `ruff format` + `ruff check` on touched files; run the manual checklist for the
  affected domain before merge.
