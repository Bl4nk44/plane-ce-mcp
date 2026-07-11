"""Unit tests for the internal web API adapter (plane_mcp/internal_api.py)."""

import httpx
import pytest
from fastmcp.exceptions import ToolError
from plane.errors import HttpError

import plane_mcp.compat as compat
import plane_mcp.internal_api as internal_api
from plane_mcp.compat import wrap_client
from plane_mcp.internal_api import PlaneInternalApiError, PlaneInternalClient

BASE = "http://plane.local:8800"
PAGE = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "name": "Notes",
    "description_html": "<p>hello</p>",
}


def make_client(handler) -> PlaneInternalClient:
    client = PlaneInternalClient(BASE, "bot@local", "secret")
    client._http = httpx.Client(base_url=BASE, transport=httpx.MockTransport(handler), follow_redirects=False)
    return client


def happy_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/auth/get-csrf-token/":
        return httpx.Response(200, json={"csrf_token": "tok"})
    if path == "/auth/sign-in/":
        assert request.method == "POST"
        body = request.content.decode()
        assert "email=bot%40local" in body and "csrfmiddlewaretoken=tok" in body
        return httpx.Response(302, headers={"location": BASE + "/"})
    if path == "/api/users/me/":
        return httpx.Response(200, json={"id": "u1"})
    if path.endswith("/pages/"):
        return httpx.Response(200, json=[PAGE])
    if PAGE["id"] in path:
        return httpx.Response(200, json=PAGE)
    return httpx.Response(404, json={"error": "Page not found."})


def test_sign_in_and_list_pages():
    client = make_client(happy_handler)
    pages = client.list_project_pages("ws", "proj-1")
    assert pages == [PAGE]


def test_retrieve_page():
    client = make_client(happy_handler)
    page = client.retrieve_project_page("ws", "proj-1", PAGE["id"])
    assert page["description_html"] == "<p>hello</p>"


def test_bad_credentials_raise_clear_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/get-csrf-token/":
            return httpx.Response(200, json={"csrf_token": "tok"})
        if request.url.path == "/auth/sign-in/":
            return httpx.Response(302, headers={"location": BASE + "/?error_code=AUTHENTICATION_FAILED"})
        return httpx.Response(401)

    client = make_client(handler)
    with pytest.raises(PlaneInternalApiError, match="Sign-in rejected"):
        client.list_project_pages("ws", "proj-1")


def test_expired_session_reauthenticates_once():
    state = {"me_calls": 0, "page_calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/auth/get-csrf-token/":
            return httpx.Response(200, json={"csrf_token": "tok"})
        if path == "/auth/sign-in/":
            return httpx.Response(302, headers={"location": BASE + "/"})
        if path == "/api/users/me/":
            state["me_calls"] += 1
            return httpx.Response(200, json={"id": "u1"})
        if path.endswith("/pages/"):
            state["page_calls"] += 1
            # first call: expired session; after re-auth: success
            if state["page_calls"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json=[PAGE])
        return httpx.Response(404)

    client = make_client(handler)
    assert client.list_project_pages("ws", "proj-1") == [PAGE]
    assert state["me_calls"] == 2  # signed in twice


def test_get_internal_client_requires_env(monkeypatch):
    monkeypatch.delenv("PLANE_INTERNAL_API_EMAIL", raising=False)
    monkeypatch.delenv("PLANE_INTERNAL_API_PASSWORD", raising=False)
    with pytest.raises(PlaneInternalApiError, match="PLANE_INTERNAL_API_EMAIL"):
        internal_api.get_internal_client(BASE)


# --- pages fallback through the compat proxy ------------------------------------

MISSING_ENDPOINT_404 = HttpError("HTTP 404: Not Found", 404, {"error": "Page not found."})


class FakePagesGroup:
    def list_project_pages(self, workspace_slug, project_id, params=None):
        raise MISSING_ENDPOINT_404

    def retrieve_project_page(self, workspace_slug, project_id, page_id, params=None):
        raise MISSING_ENDPOINT_404


class FakeSdk:
    pages = FakePagesGroup()


def test_pages_fallback_uses_internal_adapter(monkeypatch):
    class FakeInternal:
        def list_project_pages(self, ws, pid):
            return [PAGE]

        def retrieve_project_page(self, ws, pid, page_id):
            return PAGE

    monkeypatch.setattr(compat, "get_internal_client", lambda base_url: FakeInternal())
    client = wrap_client(FakeSdk())

    listed = client.pages.list_project_pages(workspace_slug="ws", project_id="p1")
    assert listed.total_count == 1
    assert str(listed.results[0].id) == PAGE["id"]

    page = client.pages.retrieve_project_page(workspace_slug="ws", project_id="p1", page_id=PAGE["id"])
    assert page.description_html == "<p>hello</p>"


def test_pages_fallback_without_credentials_gives_actionable_error(monkeypatch):
    monkeypatch.delenv("PLANE_INTERNAL_API_EMAIL", raising=False)
    monkeypatch.delenv("PLANE_INTERNAL_API_PASSWORD", raising=False)
    client = wrap_client(FakeSdk())
    with pytest.raises(ToolError, match="PLANE_INTERNAL_API_EMAIL"):
        client.pages.list_project_pages(workspace_slug="ws", project_id="p1")
