"""Tests for the PQL reference MCP resource (Stage 4.2)."""

import asyncio

from fastmcp import Client, FastMCP

from plane_mcp.tools.pql import register_pql_tools
from plane_mcp.tools.pql_reference import PQL_FULL_REFERENCE


def test_pql_reference_resource_readable():
    mcp = FastMCP("t")
    register_pql_tools(mcp)

    async def go():
        async with Client(mcp) as client:
            resources = await client.list_resources()
            assert any(str(r.uri) == "resource://pql-reference" for r in resources)
            content = await client.read_resource("resource://pql-reference")
            return content[0].text

    text = asyncio.run(go())
    assert text == PQL_FULL_REFERENCE


def test_pql_reference_tool_still_registered():
    mcp = FastMCP("t")
    register_pql_tools(mcp)
    tools = asyncio.run(mcp.list_tools(run_middleware=False))
    assert [t.name for t in tools] == ["get_pql_reference"]
