"""Central MCP tool-annotation assignment.

MCP tool annotations (readOnlyHint / destructiveHint / idempotentHint /
openWorldHint) let a client tell safe reads from mutations before calling a
tool. Rather than hand-annotate ~140 tools across 24 modules (and drift over
time), annotations are derived once from the tool-name prefix and applied to
every registered tool. The same readOnlyHint drives the read-only tool surface
(server.get_readonly_header_mcp), so there is a single source of truth for what
"read-only" means.

Every tool talks to the remote Plane API, so openWorldHint is always True.
"""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger
from mcp.types import ToolAnnotations

logger = get_logger(__name__)

# Read-only: no state change. Keep in sync with the read-only surface intent.
# `resolve_` is intentionally excluded - resolve_work_item_type creates the type
# when it is absent, so it is a write.
READ_ONLY_PREFIXES = ("list_", "retrieve_", "get_", "count_", "search_", "read_")

# Removes/undoes a resource. Deleting an already-deleted resource lands on the
# same end state, so these are idempotent.
DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "detach_")

# Full-overwrite writes: same input -> same resulting state (idempotent), and
# they do not remove data.
IDEMPOTENT_WRITE_PREFIXES = ("update_", "set_")

# Additive writes: each call creates something new (not idempotent) and does not
# destroy existing data.
CREATE_PREFIXES = ("create_", "attach_", "link_", "import_", "upload_")

# Everything else (manage_, complete_, transfer_, resolve_) is a write whose
# effect depends on arguments; stay conservative and leave destructive/idempotent
# unset so clients treat it as a potentially destructive mutation.


def classify_annotations(name: str) -> ToolAnnotations:
    """Derive MCP annotations for a tool from its name prefix."""
    if name.startswith(READ_ONLY_PREFIXES):
        return ToolAnnotations(readOnlyHint=True, openWorldHint=True)
    if name.startswith(DESTRUCTIVE_PREFIXES):
        return ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)
    if name.startswith(IDEMPOTENT_WRITE_PREFIXES):
        return ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
    if name.startswith(CREATE_PREFIXES):
        return ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
    # Conservative default: a write we cannot prove is safe.
    return ToolAnnotations(readOnlyHint=False, openWorldHint=True)


def is_read_only(annotations: ToolAnnotations | None) -> bool:
    """True if annotations mark a tool read-only. Missing annotations -> not read-only."""
    return bool(annotations and annotations.readOnlyHint)


async def _apply(mcp: FastMCP) -> None:
    for tool in await mcp.list_tools(run_middleware=False):
        live = await mcp.get_tool(tool.name)
        # Respect an annotation a tool set explicitly at definition time.
        if live.annotations is None:
            live.annotations = classify_annotations(tool.name)


def apply_tool_annotations(mcp: FastMCP) -> None:
    """Annotate every registered tool in-place based on its name prefix.

    Call after all tools are registered. Runs its own event loop (the server
    factories are synchronous and run before any loop is started).
    """
    import asyncio

    asyncio.run(_apply(mcp))
