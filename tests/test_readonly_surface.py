"""Tests for the read-only tool surface (roadmap E13.4)."""

import asyncio

from plane_mcp.annotations import READ_ONLY_PREFIXES, is_read_only
from plane_mcp.server import get_header_mcp, get_readonly_header_mcp

MUTATING_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "manage_",
    "transfer_",
    "attach_",
    "detach_",
    "upload_",
    "import_",
    "set_",
    "link_",
    "complete_",
    "remove_",
    "resolve_",  # resolve_work_item_type creates the type when missing
)


def test_readonly_surface_has_no_mutating_tools():
    tools = [t.name for t in asyncio.run(get_readonly_header_mcp().list_tools(run_middleware=False))]
    assert tools, "read-only endpoint must expose at least one tool"
    offenders = [name for name in tools if name.startswith(MUTATING_PREFIXES)]
    assert not offenders, f"mutating tools leaked into the read-only surface: {offenders}"
    non_matching = [name for name in tools if not name.startswith(READ_ONLY_PREFIXES)]
    assert not non_matching, f"tools outside the read-only prefixes: {non_matching}"


def test_readonly_surface_keeps_the_read_tools():
    full = {t.name for t in asyncio.run(get_header_mcp().list_tools(run_middleware=False))}
    readonly = {t.name for t in asyncio.run(get_readonly_header_mcp().list_tools(run_middleware=False))}
    assert readonly < full
    expected_read = {name for name in full if name.startswith(READ_ONLY_PREFIXES)}
    assert readonly == expected_read
    for essential in ("list_projects", "list_work_items", "retrieve_work_item", "list_pages", "retrieve_page"):
        assert essential in readonly


def test_full_surface_annotations_agree_with_readonly_prefixes():
    """The read-only surface keys off readOnlyHint, so annotations and the
    prefix list must classify every tool identically."""
    tools = asyncio.run(get_header_mcp().list_tools(run_middleware=False))
    assert tools
    for tool in tools:
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        by_prefix = tool.name.startswith(READ_ONLY_PREFIXES)
        assert is_read_only(tool.annotations) == by_prefix, tool.name
