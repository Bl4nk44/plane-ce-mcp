"""Tools for Plane MCP Server.

Tools are grouped into named *toolsets* so a client can register only the
domains it needs. Every MCP client loads every registered tool definition into
its context window; with ~190 tools that is expensive, so a client that only
manages work items can set ``PLANE_TOOLSETS=core`` and skip the rest.

Default is ``all`` (backward compatible - existing clients keep every tool).
"""

from __future__ import annotations

import os
from collections.abc import Callable

from fastmcp import FastMCP
from fastmcp.utilities.logging import get_logger

from plane_mcp.annotations import apply_tool_annotations
from plane_mcp.tools.cycles import register_cycle_tools
from plane_mcp.tools.initiatives import register_initiative_tools
from plane_mcp.tools.instance import register_instance_tools
from plane_mcp.tools.intake import register_intake_tools
from plane_mcp.tools.labels import register_label_tools
from plane_mcp.tools.milestones import register_milestone_tools
from plane_mcp.tools.modules import register_module_tools
from plane_mcp.tools.pages import register_page_tools
from plane_mcp.tools.pql import register_pql_tools
from plane_mcp.tools.projects import register_project_tools
from plane_mcp.tools.roles import register_role_tools
from plane_mcp.tools.states import register_state_tools
from plane_mcp.tools.users import register_user_tools
from plane_mcp.tools.work_item_activities import register_work_item_activity_tools
from plane_mcp.tools.work_item_attachments import register_work_item_attachment_tools
from plane_mcp.tools.work_item_comments import register_work_item_comment_tools
from plane_mcp.tools.work_item_links import register_work_item_link_tools
from plane_mcp.tools.work_item_properties import register_work_item_property_tools
from plane_mcp.tools.work_item_relation_definitions import register_work_item_relation_definition_tools
from plane_mcp.tools.work_item_relations import register_work_item_relation_tools
from plane_mcp.tools.work_item_types import register_work_item_type_tools
from plane_mcp.tools.work_items import register_work_item_tools
from plane_mcp.tools.work_logs import register_work_log_tools
from plane_mcp.tools.workspaces import register_workspace_tools

logger = get_logger(__name__)

# Named toolsets. Keys are the values accepted in PLANE_TOOLSETS. "core" is the
# daily-driver set that works against self-host CE without extra config; the
# other sets are opt-in domains. Keep every register_* function reachable from
# exactly one toolset so `all` stays complete.
TOOLSETS: dict[str, tuple[Callable[[FastMCP], None], ...]] = {
    "core": (
        register_project_tools,
        register_work_item_tools,
        register_state_tools,
        register_label_tools,
        register_cycle_tools,
        register_module_tools,
        register_user_tools,
        register_workspace_tools,
        register_instance_tools,
    ),
    "comments": (
        register_work_item_comment_tools,
        register_work_item_link_tools,
        register_work_item_attachment_tools,
        register_work_item_activity_tools,
    ),
    "pages": (register_page_tools,),
    "types": (
        register_work_item_type_tools,
        register_work_item_property_tools,
        register_work_item_relation_definition_tools,
        register_work_item_relation_tools,
    ),
    "planning": (
        register_initiative_tools,
        register_milestone_tools,
        register_intake_tools,
        register_work_log_tools,
    ),
    "admin": (register_role_tools,),
    "pql": (register_pql_tools,),
}


def resolve_toolsets(value: str | None = None) -> list[str]:
    """Resolve the effective toolset names from an env value.

    ``value`` defaults to PLANE_TOOLSETS. Empty or ``all`` selects everything.
    Unknown names are dropped with a warning rather than failing startup, so a
    typo never takes the whole server down. Order follows TOOLSETS insertion.
    """
    if value is None:
        value = os.getenv("PLANE_TOOLSETS", "")
    requested = [name.strip().lower() for name in value.split(",") if name.strip()]
    if not requested or "all" in requested:
        return list(TOOLSETS)

    selected: list[str] = []
    for name in TOOLSETS:  # preserve canonical order, dedupe
        if name in requested and name not in selected:
            selected.append(name)
    unknown = [name for name in requested if name not in TOOLSETS]
    if unknown:
        logger.warning(
            "PLANE_TOOLSETS: ignoring unknown toolset(s) %s; valid names: %s",
            ", ".join(sorted(set(unknown))),
            ", ".join(TOOLSETS),
        )
    if not selected:
        logger.warning("PLANE_TOOLSETS=%r matched no valid toolset; falling back to all", value)
        return list(TOOLSETS)
    return selected


def register_tools(mcp: FastMCP, toolsets: str | None = None) -> None:
    """Register the selected toolsets with the MCP server.

    ``toolsets`` is a comma-separated string (defaults to the PLANE_TOOLSETS env
    var, then to ``all``). See TOOLSETS for the available names.
    """
    selected = resolve_toolsets(toolsets)
    for name in selected:
        for register in TOOLSETS[name]:
            register(mcp)
    apply_tool_annotations(mcp)
    logger.info("Registered toolsets: %s", ", ".join(selected))
