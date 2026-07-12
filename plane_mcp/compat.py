"""Compatibility layer for self-host vs Cloud Plane API differences.

Central place for classifying Plane API errors and turning them into actionable
MCP tool errors. Endpoint availability differences between Plane editions
(Community Edition lacks pages, issue-types, initiatives, estimates - see
docs/plane-api-compat.md) are handled here, never inline in individual tools.

The boundary is ``wrap_client``: ``get_plane_client_context()`` returns the SDK
client wrapped in a proxy that translates every ``PlaneError`` raised by an SDK
call into a ``fastmcp.exceptions.ToolError`` whose message FastMCP forwards to
the MCP client verbatim. (FastMCP catches tool exceptions below its middleware
layer, so a middleware cannot do this translation.)
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from enum import Enum
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from plane.errors import HttpError, PlaneError
from plane.models.cycles import PaginatedCycleLiteResponse
from plane.models.modules import PaginatedModuleLiteResponse
from plane.models.pages import Page, PaginatedPageResponse
from plane.models.projects import PaginatedProjectLiteResponse, PaginatedProjectMemberResponse
from plane.models.query_params import PaginatedQueryParams
from plane.models.workspaces import PaginatedWorkspaceMemberResponse

from plane_mcp.internal_api import get_internal_client, internal_credentials_configured
from plane_mcp.retry import call_with_retries, is_read_only_operation

logger = logging.getLogger("fastmcp.plane_mcp.compat")

COMPAT_DOC = "docs/plane-api-compat.md"

# Verified on Plane CE v1.3.1: a route that does not exist in this edition/version
# returns {"error": "Page not found."}; an existing route with an unknown id returns
# {"error": "The requested resource does not exist."}. Both are 404 application/json,
# so the body text is the only reliable discriminator.
_MISSING_ENDPOINT_MARKER = "page not found"


class PlaneErrorKind(Enum):
    MISSING_ENDPOINT = "missing_endpoint"
    MISSING_RESOURCE = "missing_resource"
    AUTH = "auth"
    OTHER = "other"


def classify_http_error(error: HttpError) -> PlaneErrorKind:
    """Classify a Plane SDK HttpError into an actionable category."""
    if error.status_code in (401, 403):
        return PlaneErrorKind.AUTH
    if error.status_code == 404:
        body = error.response
        text = ""
        if isinstance(body, dict):
            text = str(body.get("error") or body.get("detail") or "")
        elif isinstance(body, str):
            text = body
        if _MISSING_ENDPOINT_MARKER in text.lower():
            return PlaneErrorKind.MISSING_ENDPOINT
        return PlaneErrorKind.MISSING_RESOURCE
    return PlaneErrorKind.OTHER


def describe_http_error(operation: str, error: HttpError) -> str:
    """Build a clear, actionable error message for an MCP client.

    ``operation`` names what was attempted - an SDK call path like
    ``work_item_types.list`` (from the client proxy) or a tool name.
    """
    kind = classify_http_error(error)
    if kind is PlaneErrorKind.MISSING_ENDPOINT:
        return (
            f"Plane API call '{operation}' failed: this Plane instance does not expose the "
            f"required API endpoint (HTTP 404, endpoint missing). This is usually an "
            f"edition/version limitation - e.g. Community Edition lacks pages, issue-types, "
            f"initiatives and estimates APIs. See {COMPAT_DOC}."
        )
    if kind is PlaneErrorKind.MISSING_RESOURCE:
        return (
            f"Plane API call '{operation}' failed: the requested resource does not exist "
            f"(HTTP 404). Check the id/slug arguments passed to the tool."
        )
    if kind is PlaneErrorKind.AUTH:
        return (
            f"Plane API call '{operation}' failed: authentication/authorization error "
            f"(HTTP {error.status_code}). Check the API key (PAT), workspace slug, and that "
            f"the key's user has access to the target project."
        )
    return f"Plane API call '{operation}' failed: Plane API error (HTTP {error.status_code}): {error}"


# --- lite -> full endpoint fallbacks -------------------------------------------
#
# The SDK's read-only "lite" endpoints (/projects-lite/, /cycles-lite/,
# /modules-lite/, /project-members-lite/, /members-lite/) do not exist on
# self-host CE v1.3.1 (all verified 404 "Page not found."). The full endpoints
# do. Each fallback below calls the full endpoint on the same SDK api group and
# adapts the response into the lite response model the tool signature promises.


def _synthesize_envelope(model_cls: Any, items: list[Any]) -> Any:
    """Build a single-page paginated envelope from a bare list response."""
    data = [item.model_dump() if hasattr(item, "model_dump") else item for item in items]
    n = len(data)
    return model_cls.model_validate(
        {
            "total_count": n,
            "next_cursor": "",
            "prev_cursor": "",
            "next_page_results": False,
            "prev_page_results": False,
            "count": n,
            "total_pages": 1,
            "total_results": n,
            "results": data,
        }
    )


def _convert_envelope(model_cls: Any, response: Any) -> Any:
    """Re-shape a full paginated envelope (or bare list) into a lite model."""
    if isinstance(response, list):
        return _synthesize_envelope(model_cls, response)
    return model_cls.model_validate(response.model_dump())


def _fb_projects_list_lite(group: Any, workspace_slug: str, params: Any = None, **kw: Any) -> Any:
    full_params = None
    if params is not None:
        full_params = PaginatedQueryParams(cursor=params.cursor, per_page=params.per_page)
    return _convert_envelope(
        PaginatedProjectLiteResponse, group.list(workspace_slug=workspace_slug, params=full_params, **kw)
    )


def _fb_cycles_list_lite(group: Any, workspace_slug: str, project_id: str, params: Any = None, **kw: Any) -> Any:
    mapping = params.to_query_params() if params is not None else None
    return _convert_envelope(
        PaginatedCycleLiteResponse,
        group.list(workspace_slug=workspace_slug, project_id=project_id, params=mapping, **kw),
    )


def _fb_modules_list_lite(group: Any, workspace_slug: str, project_id: str, params: Any = None, **kw: Any) -> Any:
    mapping = params.to_query_params() if params is not None else None
    return _convert_envelope(
        PaginatedModuleLiteResponse,
        group.list(workspace_slug=workspace_slug, project_id=project_id, params=mapping, **kw),
    )


def _fb_project_members_lite(group: Any, workspace_slug: str, project_id: str, params: Any = None, **kw: Any) -> Any:
    # MemberListQueryParams subclasses MemberQueryParams, so the full endpoint
    # accepts it directly (the extra cursor/per_page query params are ignored).
    members = group.get_members(workspace_slug=workspace_slug, project_id=project_id, params=params, **kw)
    return _synthesize_envelope(PaginatedProjectMemberResponse, members)


def _fb_workspace_members_lite(group: Any, workspace_slug: str, params: Any = None, **kw: Any) -> Any:
    members = group.get_members(workspace_slug=workspace_slug, params=params, **kw)
    return _synthesize_envelope(PaginatedWorkspaceMemberResponse, members)


def _plane_base_url() -> str:
    return os.getenv("PLANE_INTERNAL_BASE_URL") or os.getenv("PLANE_BASE_URL", "https://api.plane.so")


def _fb_pages_list_project(group: Any, workspace_slug: str, project_id: str, params: Any = None, **kw: Any) -> Any:
    # CE has no public Pages API - go through the internal session-auth adapter
    # (read-only; requires PLANE_INTERNAL_API_EMAIL/PASSWORD, see internal_api.py).
    internal = get_internal_client(_plane_base_url())
    pages = internal.list_project_pages(workspace_slug, project_id)
    return _synthesize_envelope(PaginatedPageResponse, pages)


def _fb_pages_retrieve_project(
    group: Any, workspace_slug: str, project_id: str, page_id: str, params: Any = None, **kw: Any
) -> Any:
    internal = get_internal_client(_plane_base_url())
    return Page.model_validate(internal.retrieve_project_page(workspace_slug, project_id, page_id))


# Keyed by the proxy operation path; each handler receives the *unwrapped* SDK
# api group followed by the original call arguments.
FALLBACKS: dict[str, Callable[..., Any]] = {
    "projects.list_lite": _fb_projects_list_lite,
    "cycles.list_lite": _fb_cycles_list_lite,
    "modules.list_lite": _fb_modules_list_lite,
    "projects.get_members_lite": _fb_project_members_lite,
    "workspaces.get_members_lite": _fb_workspace_members_lite,
    "pages.list_project_pages": _fb_pages_list_project,
    "pages.retrieve_project_page": _fb_pages_retrieve_project,
}


def _run_fallback(
    fallback: Callable[..., Any], group: Any, operation: str, original: HttpError, args: Any, kwargs: Any
) -> Any:
    logger.warning(
        "Plane API call %s not available on this instance (HTTP 404) - falling back",
        operation,
    )
    try:
        return fallback(group, *args, **kwargs)
    except ToolError:
        raise
    except HttpError as fe:
        raise ToolError(
            f"{describe_http_error(operation, original)} The fallback also failed: {describe_http_error(operation, fe)}"
        ) from fe
    except Exception as fe:  # noqa: BLE001 - any fallback failure must surface cleanly
        raise ToolError(f"{describe_http_error(operation, original)} The fallback also failed: {fe}") from fe


def _wrap_callable(func: Any, operation: str, group: Any) -> Any:
    read_only = is_read_only_operation(operation)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return call_with_retries(lambda: func(*args, **kwargs), operation, read_only=read_only)
        except ToolError:
            raise
        except HttpError as e:
            if classify_http_error(e) is PlaneErrorKind.MISSING_ENDPOINT:
                fallback = FALLBACKS.get(operation)
                if fallback is not None:
                    return _run_fallback(fallback, group, operation, e, args, kwargs)
                logger.warning("Plane API call %s hit a missing endpoint (HTTP 404): %s", operation, e)
            raise ToolError(describe_http_error(operation, e)) from e
        except httpx.TimeoutException as e:
            raise ToolError(
                f"Plane API call '{operation}' failed: the Plane API did not respond in time "
                f"(timeout). Check that the instance at PLANE_BASE_URL is reachable."
            ) from e
        except PlaneError as e:
            raise ToolError(f"Plane API call '{operation}' failed: Plane SDK error: {e}") from e

    return wrapper


class CompatClientProxy:
    """Attribute-chain proxy over the Plane SDK client.

    Tools call ``client.<api_group>.<operation>(...)``; this proxy follows the
    attribute chain and wraps the final callable so any SDK error surfaces as a
    ToolError with an actionable message instead of a raw exception.
    """

    def __init__(self, target: Any, path: str = "") -> None:
        self._target = target
        self._path = path

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        path = f"{self._path}.{name}" if self._path else name
        if callable(attr):
            return _wrap_callable(attr, path, self._target)
        if hasattr(attr, "__dict__") or hasattr(attr, "__slots__"):
            return CompatClientProxy(attr, path)
        return attr


def wrap_client(client: Any) -> CompatClientProxy:
    """Wrap a PlaneClient so all SDK errors become actionable ToolErrors."""
    return CompatClientProxy(client)


# --- instance capability detection ----------------------------------------------
#
# GET /api/instances/ is unauthenticated and works on self-host CE (verified on
# v1.3.1); it exposes instance.current_version and instance.edition. There is no
# /features/ capability endpoint on CE, so this is the only up-front signal for
# self-host vs Cloud profiling. Errors never propagate - the profile is a hint,
# not a dependency; endpoint 404s are still handled reactively by the proxy.

# API families verified missing on Community Edition v1.3.1 (docs/plane-api-compat.md).
# Lite endpoints are excluded: they are missing too but handled by FALLBACKS.
CE_UNAVAILABLE_FEATURES = [
    "pages (public API; internal session-auth API only)",
    "work item types / epics (issue-types)",
    "initiatives",
    "estimates",
    "milestones",
    "workspace features endpoint",
]

_profile_cache: dict[str, dict[str, Any]] = {}


def fetch_instance_profile(base_url: str) -> dict[str, Any]:
    """Fetch edition/version info for a Plane instance (cached per base_url).

    Returns {"edition": ..., "version": ...}; values are None when the endpoint
    is unreachable or malformed (e.g. Plane Cloud does not expose it publicly).
    """
    cached = _profile_cache.get(base_url)
    if cached is not None:
        return cached

    profile: dict[str, Any] = {"edition": None, "version": None}
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/instances/", timeout=5)
        response.raise_for_status()
        instance = response.json().get("instance") or {}
        profile["edition"] = instance.get("edition")
        profile["version"] = instance.get("current_version")
    except Exception as exc:  # noqa: BLE001 - profile is best-effort by design
        logger.info("Could not fetch instance profile from %s: %s", base_url, exc)

    _profile_cache[base_url] = profile
    return profile


def describe_instance(base_url: str) -> dict[str, Any]:
    """Instance profile plus known API limitations, for diagnostics tools."""
    from plane_mcp import __version__ as server_version

    profile = fetch_instance_profile(base_url)
    edition = profile["edition"]
    info: dict[str, Any] = {
        "base_url": base_url,
        "edition": edition,
        "version": profile["version"],
        "server_version": server_version,
        "compat_reference": COMPAT_DOC,
    }
    if edition == "PLANE_COMMUNITY":
        unavailable = list(CE_UNAVAILABLE_FEATURES)
        if internal_credentials_configured():
            # The internal-API adapter makes project pages readable despite the
            # missing public API - do not report them as unavailable.
            unavailable = [f for f in unavailable if not f.startswith("pages")]
            info["available_via_internal_adapter"] = (
                "pages (project pages, read-only: list_pages/retrieve_page with a "
                "project_id WORK on this instance; private pages stay owner-only)"
            )
        info["unavailable_features"] = unavailable
        info["note"] = (
            "Community Edition: the APIs listed in unavailable_features return 404 "
            "(missing endpoint). Lite list endpoints are also absent but fall back "
            "to the full endpoints automatically."
        )
    return info
