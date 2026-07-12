"""Instance diagnostics tools for Plane MCP Server."""

import os
from typing import Any

from fastmcp import FastMCP

from plane_mcp.compat import describe_instance


def register_instance_tools(mcp: FastMCP) -> None:
    """Register instance diagnostics tools with the MCP server."""

    @mcp.tool()
    def get_instance_info() -> dict[str, Any]:
        """
        Get edition/version info and known API limitations of the connected Plane instance.

        Use this to understand up-front which tool families are unavailable
        (e.g. pages, epics/work-item types, initiatives, estimates and milestones
        on Community Edition) instead of discovering them through 404 errors.

        Returns:
            Dict with base_url, edition (e.g. "PLANE_COMMUNITY"), version,
            compat_reference, and - for Community Edition - unavailable_features.
        """
        base_url = os.getenv("PLANE_INTERNAL_BASE_URL") or os.getenv("PLANE_BASE_URL", "https://api.plane.so")
        return describe_instance(base_url)
