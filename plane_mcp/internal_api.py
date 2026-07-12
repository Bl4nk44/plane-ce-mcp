"""Session-authenticated client for Plane's internal web API.

Community Edition (verified on v1.3.1) does not expose Pages in the public
`/api/v1/` API - pages exist only in the internal web-app API under `/api/`,
which requires Django session-cookie authentication (a PAT gets 401 there).

This adapter signs in with a dedicated Plane account (email + password from
`PLANE_INTERNAL_API_EMAIL` / `PLANE_INTERNAL_API_PASSWORD`) and calls the
read-only Pages endpoints. It is intentionally minimal and read-only: the
internal API is not a stable contract, so every route used here is pinned in
docs/plane-api-compat.md and verified against the local self-host instance.

Auth flow (from plane v1.3.1 `apps/api/plane/authentication/urls.py`):
  1. GET  /auth/get-csrf-token/  -> csrftoken cookie + {"csrf_token": ...}
  2. POST /auth/sign-in/         -> form (email, password, csrfmiddlewaretoken),
                                    303/302 redirect + session cookie on success
  3. GET  /api/users/me/         -> 200 confirms the session is valid
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("fastmcp.plane_mcp.internal_api")

_TIMEOUT = 15.0


class PlaneInternalApiError(Exception):
    """Raised when the internal-API adapter cannot authenticate or fetch data."""


def internal_credentials_configured() -> bool:
    """True when the env vars for internal-API session auth are set."""
    return bool(os.getenv("PLANE_INTERNAL_API_EMAIL") and os.getenv("PLANE_INTERNAL_API_PASSWORD"))


class PlaneInternalClient:
    """Minimal session-authenticated client for the internal web API."""

    def __init__(self, base_url: str, email: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._http = httpx.Client(base_url=self._base_url, timeout=_TIMEOUT, follow_redirects=False)
        self._signed_in = False

    def close(self) -> None:
        self._http.close()

    # -- auth ---------------------------------------------------------------

    def _sign_in(self) -> None:
        csrf_response = self._http.get("/auth/get-csrf-token/")
        csrf_response.raise_for_status()
        csrf_token = csrf_response.json().get("csrf_token")
        if not csrf_token:
            raise PlaneInternalApiError("Could not obtain a CSRF token from /auth/get-csrf-token/")

        sign_in = self._http.post(
            "/auth/sign-in/",
            data={
                "email": self._email,
                "password": self._password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={"Referer": self._base_url + "/"},
        )
        # Success and failure both redirect (Django form flow); failures carry
        # error query params. The reliable check is whether the session works.
        if sign_in.status_code >= 400:
            raise PlaneInternalApiError(f"Sign-in request failed with HTTP {sign_in.status_code}")
        location = sign_in.headers.get("location", "")
        if "error_code" in location or "error_message" in location:
            raise PlaneInternalApiError(
                "Sign-in rejected by Plane (check PLANE_INTERNAL_API_EMAIL / "
                "PLANE_INTERNAL_API_PASSWORD); redirect carried an error code."
            )

        me = self._http.get("/api/users/me/")
        if me.status_code != 200:
            raise PlaneInternalApiError(
                f"Sign-in did not produce a working session (GET /api/users/me/ -> HTTP {me.status_code})"
            )
        self._signed_in = True
        logger.info("Internal-API session established for %s", self._base_url)

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self._signed_in:
            self._sign_in()
        response = self._http.request(method, path, **kwargs)
        if response.status_code == 401:
            # Session expired - re-authenticate once and retry.
            logger.warning("Internal-API session expired, re-authenticating")
            self._signed_in = False
            self._sign_in()
            response = self._http.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    # -- pages (read-only) ----------------------------------------------------

    def list_project_pages(self, workspace_slug: str, project_id: str) -> list[dict[str, Any]]:
        """List pages of a project (internal route: .../projects/<id>/pages/)."""
        response = self._request("GET", f"/api/workspaces/{workspace_slug}/projects/{project_id}/pages/")
        data = response.json()
        return data if isinstance(data, list) else data.get("results", [])

    def retrieve_project_page(self, workspace_slug: str, project_id: str, page_id: str) -> dict[str, Any]:
        """Retrieve one page incl. description_html (PageDetailSerializer)."""
        response = self._request(
            "GET",
            f"/api/workspaces/{workspace_slug}/projects/{project_id}/pages/{page_id}/",
            params={"track_visit": "false"},
        )
        return response.json()


_client_cache: dict[tuple[str, str], PlaneInternalClient] = {}


def get_internal_client(base_url: str) -> PlaneInternalClient:
    """Get (or create) a cached internal-API client for the given instance.

    Raises PlaneInternalApiError when credentials are not configured.
    """
    email = os.getenv("PLANE_INTERNAL_API_EMAIL", "")
    password = os.getenv("PLANE_INTERNAL_API_PASSWORD", "")
    if not email or not password:
        raise PlaneInternalApiError(
            "Pages on this Plane edition are only reachable through the internal "
            "session-auth API. Set PLANE_INTERNAL_API_EMAIL and "
            "PLANE_INTERNAL_API_PASSWORD (a dedicated Plane account) to enable the "
            "internal-API fallback. See docs/plane-api-compat.md."
        )
    key = (base_url, email)
    client = _client_cache.get(key)
    if client is None:
        client = PlaneInternalClient(base_url, email, password)
        _client_cache[key] = client
    return client
