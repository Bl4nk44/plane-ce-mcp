"""Unit tests for the compatibility layer (plane_mcp/compat.py)."""

import asyncio

import httpx
import pytest
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.exceptions import ToolError
from plane.errors import HttpError, PlaneError

from plane_mcp.compat import (
    PlaneErrorKind,
    classify_http_error,
    describe_http_error,
    wrap_client,
)

# --- classify_http_error -------------------------------------------------------


def test_classify_missing_endpoint():
    # Body shape verified on Plane CE v1.3.1 (docs/plane-api-compat.md)
    err = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})
    assert classify_http_error(err) is PlaneErrorKind.MISSING_ENDPOINT


def test_classify_missing_resource():
    err = HttpError("HTTP 404: Not Found", 404, {"error": "The requested resource does not exist."})
    assert classify_http_error(err) is PlaneErrorKind.MISSING_RESOURCE


def test_classify_missing_resource_when_body_empty():
    err = HttpError("HTTP 404: Not Found", 404, None)
    assert classify_http_error(err) is PlaneErrorKind.MISSING_RESOURCE


def test_classify_missing_endpoint_string_body():
    err = HttpError("HTTP 404: Not Found", 404, "Page not found.")
    assert classify_http_error(err) is PlaneErrorKind.MISSING_ENDPOINT


@pytest.mark.parametrize("status", [401, 403])
def test_classify_auth(status):
    err = HttpError("auth", status, {"detail": "Authentication credentials were not provided."})
    assert classify_http_error(err) is PlaneErrorKind.AUTH


def test_classify_other():
    err = HttpError("boom", 500, {"error": "Internal server error"})
    assert classify_http_error(err) is PlaneErrorKind.OTHER


# --- describe_http_error -------------------------------------------------------


def test_describe_names_operation_and_compat_doc_for_missing_endpoint():
    err = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})
    msg = describe_http_error("pages.list", err)
    assert "pages.list" in msg
    assert "plane-api-compat" in msg
    assert "endpoint" in msg


def test_describe_missing_resource_mentions_arguments():
    err = HttpError("HTTP 404: Not Found", 404, {"error": "The requested resource does not exist."})
    msg = describe_http_error("projects.retrieve", err)
    assert "projects.retrieve" in msg
    assert "id/slug" in msg


def test_describe_auth_mentions_api_key():
    err = HttpError("HTTP 401", 401, None)
    msg = describe_http_error("projects.list", err)
    assert "API key" in msg


# --- wrap_client proxy ----------------------------------------------------------


class FakeApiGroup:
    def __init__(self, exc: Exception | None = None):
        self._exc = exc

    def list(self, workspace_slug: str) -> dict:
        if self._exc:
            raise self._exc
        return {"results": [], "workspace": workspace_slug}


class FakeClient:
    def __init__(self, exc: Exception | None = None):
        self.work_items = FakeApiGroup(exc)


def test_proxy_passes_through_successful_calls():
    client = wrap_client(FakeClient())
    assert client.work_items.list(workspace_slug="ws") == {"results": [], "workspace": "ws"}


def test_proxy_translates_missing_endpoint_with_operation_path():
    exc = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})
    client = wrap_client(FakeClient(exc))
    with pytest.raises(ToolError, match="work_items.list.*does not expose the required API endpoint"):
        client.work_items.list(workspace_slug="ws")


def test_proxy_translates_timeout():
    client = wrap_client(FakeClient(httpx.ConnectTimeout("timed out")))
    with pytest.raises(ToolError, match="did not respond in time"):
        client.work_items.list(workspace_slug="ws")


def test_proxy_translates_generic_plane_error():
    client = wrap_client(FakeClient(PlaneError("token refresh failed")))
    with pytest.raises(ToolError, match="Plane SDK error: token refresh failed"):
        client.work_items.list(workspace_slug="ws")


def test_proxy_does_not_wrap_toolerror():
    client = wrap_client(FakeClient(ToolError("already client-facing")))
    with pytest.raises(ToolError, match="^already client-facing$"):
        client.work_items.list(workspace_slug="ws")


# --- lite -> full endpoint fallbacks --------------------------------------------

MISSING_ENDPOINT_404 = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})


def _envelope(results: list[dict]) -> dict:
    n = len(results)
    return {
        "total_count": n,
        "next_cursor": "",
        "prev_cursor": "",
        "next_page_results": False,
        "prev_page_results": False,
        "count": n,
        "total_pages": 1,
        "total_results": n,
        "results": results,
    }


class FakeProjectsGroup:
    """list_lite 404s (missing endpoint); full list works — the CE 1.3.1 situation."""

    def __init__(self):
        self.list_params = "unset"

    def list_lite(self, workspace_slug, params=None):
        raise MISSING_ENDPOINT_404

    def list(self, workspace_slug, params=None):
        self.list_params = params
        from plane.models.projects import PaginatedProjectResponse

        return PaginatedProjectResponse.model_validate(
            _envelope([{"id": "11111111-1111-1111-1111-111111111111", "name": "P1", "identifier": "P1"}])
        )


class FakeWorkspacesGroup:
    """get_members_lite 404s; full get_members returns a bare list."""

    def get_members_lite(self, workspace_slug, params=None):
        raise MISSING_ENDPOINT_404

    def get_members(self, workspace_slug, params=None):
        return [{"id": "22222222-2222-2222-2222-222222222222", "display_name": "user"}]


class FakeSdkClient:
    def __init__(self):
        self.projects = FakeProjectsGroup()
        self.workspaces = FakeWorkspacesGroup()


def test_fallback_projects_list_lite_to_full_list():
    from plane.models.projects import PaginatedProjectLiteResponse
    from plane.models.query_params import ProjectLiteListQueryParams

    client = wrap_client(FakeSdkClient())
    params = ProjectLiteListQueryParams(cursor="100:0:0", per_page=100)
    resp = client.projects.list_lite(workspace_slug="ws", params=params)
    assert isinstance(resp, PaginatedProjectLiteResponse)
    assert resp.total_count == 1
    assert str(resp.results[0].id) == "11111111-1111-1111-1111-111111111111"


def test_fallback_forwards_pagination_params():
    fake = FakeSdkClient()
    client = wrap_client(fake)
    from plane.models.query_params import ProjectLiteListQueryParams

    client.projects.list_lite(workspace_slug="ws", params=ProjectLiteListQueryParams(cursor="50:2:0", per_page=50))
    assert fake.projects.list_params.cursor == "50:2:0"
    assert fake.projects.list_params.per_page == 50
    client.projects.list_lite(workspace_slug="ws")
    assert fake.projects.list_params is None


def test_fallback_workspace_members_synthesizes_envelope():
    from plane.models.workspaces import PaginatedWorkspaceMemberResponse

    client = wrap_client(FakeSdkClient())
    resp = client.workspaces.get_members_lite(workspace_slug="ws")
    assert isinstance(resp, PaginatedWorkspaceMemberResponse)
    assert resp.total_count == 1
    assert resp.next_page_results is False


def test_fallback_failure_reports_both_errors():
    class BrokenGroup:
        def list_lite(self, workspace_slug, params=None):
            raise MISSING_ENDPOINT_404

        def list(self, workspace_slug, params=None):
            raise HttpError("HTTP 401", 401, None)

    class BrokenClient:
        projects = BrokenGroup()

    client = wrap_client(BrokenClient())
    with pytest.raises(ToolError, match="The fallback also failed"):
        client.projects.list_lite(workspace_slug="ws")


def test_resource_404_does_not_trigger_fallback():
    class Group:
        def list_lite(self, workspace_slug, params=None):
            raise HttpError("HTTP 404", 404, {"error": "The requested resource does not exist."})

        def list(self, workspace_slug, params=None):  # pragma: no cover - must not be called
            raise AssertionError("fallback must not run for a missing resource")

    class C:
        projects = Group()

    client = wrap_client(C())
    with pytest.raises(ToolError, match="the requested resource does not exist"):
        client.projects.list_lite(workspace_slug="ws")


# --- instance capability detection ----------------------------------------------


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self):
        return self._payload


def test_fetch_instance_profile_ce(monkeypatch):
    import plane_mcp.compat as compat

    compat._profile_cache.clear()
    monkeypatch.setattr(
        compat.httpx,
        "get",
        lambda url, timeout: FakeResponse({"instance": {"edition": "PLANE_COMMUNITY", "current_version": "1.3.1"}}),
    )
    profile = compat.fetch_instance_profile("http://plane.local:8800")
    assert profile == {"edition": "PLANE_COMMUNITY", "version": "1.3.1"}


def test_fetch_instance_profile_unreachable_returns_nones(monkeypatch):
    import plane_mcp.compat as compat

    compat._profile_cache.clear()

    def boom(url, timeout):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(compat.httpx, "get", boom)
    profile = compat.fetch_instance_profile("http://nope.invalid")
    assert profile == {"edition": None, "version": None}


def test_fetch_instance_profile_is_cached(monkeypatch):
    import plane_mcp.compat as compat

    compat._profile_cache.clear()
    calls = {"n": 0}

    def counting_get(url, timeout):
        calls["n"] += 1
        return FakeResponse({"instance": {"edition": "PLANE_COMMUNITY", "current_version": "1.3.1"}})

    monkeypatch.setattr(compat.httpx, "get", counting_get)
    compat.fetch_instance_profile("http://plane.local:8800")
    compat.fetch_instance_profile("http://plane.local:8800")
    assert calls["n"] == 1


def test_describe_instance_lists_ce_limitations(monkeypatch):
    import plane_mcp.compat as compat

    compat._profile_cache.clear()
    monkeypatch.setattr(
        compat.httpx,
        "get",
        lambda url, timeout: FakeResponse({"instance": {"edition": "PLANE_COMMUNITY", "current_version": "1.3.1"}}),
    )
    info = compat.describe_instance("http://plane.local:8800")
    assert info["edition"] == "PLANE_COMMUNITY"
    assert any("pages" in f for f in info["unavailable_features"])
    assert info["compat_reference"] == "docs/plane-api-compat.md"


def test_describe_instance_cloud_has_no_limitations_list(monkeypatch):
    import plane_mcp.compat as compat

    compat._profile_cache.clear()

    def boom(url, timeout):
        raise httpx.ConnectError("cloud does not expose /api/instances/")

    monkeypatch.setattr(compat.httpx, "get", boom)
    info = compat.describe_instance("https://api.plane.so")
    assert info["edition"] is None
    assert "unavailable_features" not in info


# --- end-to-end: ToolError message reaches the MCP client ----------------------


def test_toolerror_from_wrapped_client_reaches_mcp_client():
    exc = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})
    wrapped = wrap_client(FakeClient(exc))
    mcp = FastMCP("test")

    @mcp.tool()
    def list_things() -> dict:
        """Calls the wrapped SDK client."""
        return wrapped.work_items.list(workspace_slug="ws")

    async def _run() -> str:
        async with Client(mcp) as client:
            result = await client.call_tool("list_things", {}, raise_on_error=False)
            assert result.is_error
            return result.content[0].text

    text = asyncio.run(_run())
    assert "work_items.list" in text
    assert "does not expose the required API endpoint" in text
