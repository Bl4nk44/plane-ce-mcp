"""Unit tests for work item tools via the in-memory FastMCP client.

Pattern for tool tests in this repo: register the tool group on a throwaway
FastMCP, monkeypatch the module's get_plane_client_context to return a fake SDK
client that records calls, then drive the tool through fastmcp.Client and assert
on both the recorded SDK call and the returned payload.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import Client, FastMCP
from plane.errors import HttpError
from plane.models.work_items import WorkItem

import plane_mcp.tools.work_items as wi
from plane_mcp.tools.work_items import _resolve_description_html

# --- pure helper -----------------------------------------------------------


def test_resolve_description_prefers_html():
    assert _resolve_description_html("<p>hi</p>", "ignored") == "<p>hi</p>"


def test_resolve_description_wraps_plain_text():
    out = _resolve_description_html(None, "line1\nline2")
    assert out == "<p>line1<br/>line2</p>"


def test_resolve_description_escapes_html():
    assert _resolve_description_html(None, "a < b & c") == "<p>a &lt; b &amp; c</p>"


def test_resolve_description_none():
    assert _resolve_description_html(None, None) is None


# --- harness ---------------------------------------------------------------


def _paginated(results, total=None):
    n = len(results) if total is None else total
    return SimpleNamespace(
        results=[SimpleNamespace(model_dump=lambda r=r: r) for r in results],
        total_count=n,
        count=len(results),
        next_cursor="",
        prev_cursor="",
        next_page_results=False,
        prev_page_results=False,
    )


class _RecordingWorkItems:
    def __init__(self, list_resp=None, create_ret=None, raise_on_list=None):
        self.calls = {}
        self._list_resp = list_resp if list_resp is not None else _paginated([{"id": "1", "name": "A"}])
        self._create_ret = create_ret
        self._raise_on_list = raise_on_list

    def list(self, **kw):
        self.calls["list"] = kw
        if self._raise_on_list:
            raise self._raise_on_list
        return self._list_resp

    def list_workspace(self, **kw):
        self.calls["list_workspace"] = kw
        return self._list_resp

    def create(self, **kw):
        self.calls["create"] = kw
        return self._create_ret


def _run(mcp, tool, args, fake_client, monkeypatch):
    monkeypatch.setattr(wi, "get_plane_client_context", lambda: (fake_client, "ws"))

    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go())


@pytest.fixture
def mcp():
    m = FastMCP("t")
    wi.register_work_item_tools(m)
    return m


def test_list_scopes_to_project(mcp, monkeypatch):
    items = _RecordingWorkItems()
    client = SimpleNamespace(work_items=items)
    res = _run(mcp, "list_work_items", {"project_id": "p1"}, client, monkeypatch)
    assert "list" in items.calls and "list_workspace" not in items.calls
    assert items.calls["list"]["project_id"] == "p1"
    assert res.structured_content["total_count"] == 1


def test_list_workspace_wide_when_no_project(mcp, monkeypatch):
    items = _RecordingWorkItems()
    client = SimpleNamespace(work_items=items)
    _run(mcp, "list_work_items", {}, client, monkeypatch)
    assert "list_workspace" in items.calls and "list" not in items.calls


def test_list_size_guard_trips(mcp, monkeypatch):
    monkeypatch.setenv("PLANE_MAX_RESPONSE_KB", "1")
    big = _paginated([{"id": str(i), "blob": "x" * 2000} for i in range(5)])
    items = _RecordingWorkItems(list_resp=big)
    client = SimpleNamespace(work_items=items)
    res = _run(mcp, "list_work_items", {"project_id": "p1"}, client, monkeypatch)
    assert "error" in res.structured_content
    assert res.structured_content["limit_env"] == "PLANE_MAX_RESPONSE_KB"


def test_list_invalid_pql_returns_reference(mcp, monkeypatch):
    err = HttpError("bad pql", 400, {"pql": "syntax error near '='"})
    items = _RecordingWorkItems(raise_on_list=err)
    client = SimpleNamespace(work_items=items)
    res = _run(mcp, "list_work_items", {"project_id": "p1", "pql": "bogus"}, client, monkeypatch)
    body = res.structured_content
    assert body["failed_pql"] == "bogus"
    assert "pql_reference" in body


def test_create_resolves_plain_description(mcp, monkeypatch):
    created = WorkItem.model_validate({"id": "9", "name": "New"})
    items = _RecordingWorkItems(create_ret=created)
    client = SimpleNamespace(work_items=items)
    _run(
        mcp,
        "create_work_item",
        {"project_id": "p1", "name": "New", "description_stripped": "hello", "priority": "urgent"},
        client,
        monkeypatch,
    )
    sent = items.calls["create"]["data"]
    assert sent.description_html == "<p>hello</p>"
    assert sent.priority == "urgent"


def test_create_drops_invalid_priority(mcp, monkeypatch):
    created = WorkItem.model_validate({"id": "9", "name": "New"})
    items = _RecordingWorkItems(create_ret=created)
    client = SimpleNamespace(work_items=items)
    _run(
        mcp,
        "create_work_item",
        {"project_id": "p1", "name": "New", "priority": "not-a-priority"},
        client,
        monkeypatch,
    )
    assert items.calls["create"]["data"].priority is None
