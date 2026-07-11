"""Compatibility layer for self-host vs Cloud Plane API differences.

Central place for classifying Plane API errors and turning them into actionable
MCP tool errors. Endpoint availability differences between Plane editions
(Community Edition lacks pages, issue-types, initiatives, estimates — see
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
from collections.abc import Callable
from enum import Enum
from typing import Any

import httpx
from fastmcp.exceptions import ToolError
from plane.errors import HttpError, PlaneError
from plane.models.cycles import PaginatedCycleLiteResponse
from plane.models.modules import PaginatedModuleLiteResponse
from plane.models.projects import PaginatedProjectLiteResponse, PaginatedProjectMemberResponse
from plane.models.query_params import PaginatedQueryParams
from plane.models.workspaces import PaginatedWorkspaceMemberResponse

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

    ``operation`` names what was attempted — an SDK call path like
    ``work_item_types.list`` (from the client proxy) or a tool name.
    """
    kind = classify_http_error(error)
    if kind is PlaneErrorKind.MISSING_ENDPOINT:
        return (
            f"Plane API call '{operation}' failed: this Plane instance does not expose the "
            f"required API endpoint (HTTP 404, endpoint missing). This is usually an "
            f"edition/version limitation — e.g. Community Edition lacks pages, issue-types, "
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


# Keyed by the proxy operation path; each handler receives the *unwrapped* SDK
# api group followed by the original call arguments.
FALLBACKS: dict[str, Callable[..., Any]] = {
    "projects.list_lite": _fb_projects_list_lite,
    "cycles.list_lite": _fb_cycles_list_lite,
    "modules.list_lite": _fb_modules_list_lite,
    "projects.get_members_lite": _fb_project_members_lite,
    "workspaces.get_members_lite": _fb_workspace_members_lite,
}


def _wrap_callable(func: Any, operation: str, group: Any) -> Any:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ToolError:
            raise
        except HttpError as e:
            if classify_http_error(e) is PlaneErrorKind.MISSING_ENDPOINT:
                fallback = FALLBACKS.get(operation)
                if fallback is not None:
                    logger.warning(
                        "Plane API call %s not available on this instance (HTTP 404) - "
                        "falling back to the full endpoint",
                        operation,
                    )
                    try:
                        return fallback(group, *args, **kwargs)
                    except HttpError as fe:
                        raise ToolError(
                            f"{describe_http_error(operation, e)} The fallback to the full "
                            f"endpoint also failed: {describe_http_error(operation, fe)}"
                        ) from fe
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
