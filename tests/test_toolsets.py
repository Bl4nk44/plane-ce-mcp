"""Tests for toolset selection and response-size guard (Stage 1)."""

import asyncio

from fastmcp import FastMCP

from plane_mcp.response import guard_result_size
from plane_mcp.tools import TOOLSETS, register_tools, resolve_toolsets


def test_resolve_defaults_to_all():
    assert resolve_toolsets("") == list(TOOLSETS)
    assert resolve_toolsets("all") == list(TOOLSETS)
    assert resolve_toolsets("   ") == list(TOOLSETS)


def test_resolve_selects_subset_in_canonical_order():
    assert resolve_toolsets("pages,core") == ["core", "pages"]
    assert resolve_toolsets("core") == ["core"]


def test_resolve_drops_unknown_and_dedupes():
    assert resolve_toolsets("core,bogus,core") == ["core"]
    # only unknown names -> fall back to all
    assert resolve_toolsets("bogus") == list(TOOLSETS)


def test_every_register_fn_reachable_from_exactly_one_toolset():
    seen = [fn for fns in TOOLSETS.values() for fn in fns]
    assert len(seen) == len(set(seen)), "a register fn appears in more than one toolset"


def _tool_names(selection: str) -> set[str]:
    mcp = FastMCP("t")
    register_tools(mcp, selection)
    return {t.name for t in asyncio.run(mcp.list_tools(run_middleware=False))}


def test_core_is_a_strict_subset_of_all():
    core = _tool_names("core")
    everything = _tool_names("all")
    assert core, "core toolset registered no tools"
    assert core < everything
    assert "list_work_items" in core
    assert "list_pages" not in core  # pages is its own toolset


def test_guard_returns_payload_when_small():
    payload = {"results": [1, 2, 3], "total_count": 3}
    assert guard_result_size(payload, "list_x", narrow_hint="h") is payload


def test_guard_trips_on_oversized_payload(monkeypatch):
    monkeypatch.setenv("PLANE_MAX_RESPONSE_KB", "1")
    payload = {"results": ["x" * 5000], "total_count": 1}
    out = guard_result_size(payload, "list_work_items", narrow_hint="narrow it")
    assert "error" in out
    assert out["total_count"] == 1
    assert out["hint"] == "narrow it"
    assert out["response_bytes"] > out["limit_bytes"]


def test_guard_disabled_with_zero(monkeypatch):
    monkeypatch.setenv("PLANE_MAX_RESPONSE_KB", "0")
    payload = {"results": ["x" * 5000], "total_count": 1}
    assert guard_result_size(payload, "list_x", narrow_hint="h") is payload
