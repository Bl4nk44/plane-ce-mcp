"""Main entry point for the Plane MCP Server."""

import json
import logging
import os
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from enum import Enum

import uvicorn
from fastmcp.server.dependencies import get_access_token
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from plane_mcp import __version__
from plane_mcp.server import get_header_mcp, get_oauth_mcp, get_readonly_header_mcp, get_stdio_mcp


def _healthz(_request: Request) -> JSONResponse:
    """Liveness probe: 200 as soon as the HTTP app is serving. Does not call
    Plane (so a Plane outage never marks the MCP server itself unhealthy)."""
    return JSONResponse({"status": "ok", "server_version": __version__})


def _health_route() -> Route:
    return Route("/healthz", _healthz, methods=["GET"])


LOG_USER_INFO: bool = os.getenv("LOG_USER_INFO", "").lower() == "true"


class UserContextFilter(logging.Filter):
    """Attach authenticated user/workspace context to every log record.

    Pulls the current request's access token via FastMCP's dependency, which
    returns None (never raises) outside a request context - so startup logs fall
    back to environment config and otherwise carry no user info.

    Always logs the opaque user id (sub claim) and the workspace slug; neither is
    PII. The display name IS PII and is only included when LOG_USER_INFO=true.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        user_id = None
        display_name = None
        workspace_slug = None
        try:
            token = get_access_token()
            if token:
                user_id = token.claims.get("sub")
                workspace_slug = token.claims.get("workspace_slug")
                if LOG_USER_INFO:
                    display_name = token.claims.get("display_name")
        except Exception as exc:
            # Never let logging enrichment break a request, but leave a signal.
            record.user_context_enrichment_error = type(exc).__name__
        record.user_id = user_id
        record.display_name = display_name
        # stdio mode has no token; fall back to the configured workspace.
        record.workspace_slug = workspace_slug or os.getenv("PLANE_WORKSPACE_SLUG") or None
        return True


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging (Datadog, ELK, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        # The logging middleware emits a JSON object as its log message. Promote
        # those keys to top-level fields (event, method, tool, duration_ms, ...)
        raw_message = record.getMessage()
        try:
            parsed = json.loads(raw_message)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            log_entry.update(parsed)
        else:
            log_entry["message"] = raw_message
        user_id = getattr(record, "user_id", None)
        if user_id:
            log_entry["user_id"] = user_id
        workspace_slug = getattr(record, "workspace_slug", None)
        if workspace_slug:
            log_entry["workspace_slug"] = workspace_slug
        display_name = getattr(record, "display_name", None)
        if display_name:
            log_entry["display_name"] = display_name
        err = getattr(record, "user_context_enrichment_error", None)
        if err:
            log_entry["user_context_enrichment_error"] = err
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = str(record.exc_info[1])
            log_entry["error_type"] = type(record.exc_info[1]).__name__
        return json.dumps(log_entry)


def configure_json_logging():
    """Replace FastMCP's Rich handlers with a JSON formatter on the fastmcp logger."""
    fastmcp_logger = logging.getLogger("fastmcp")

    # Remove all existing handlers (Rich)
    for handler in fastmcp_logger.handlers[:]:
        fastmcp_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(UserContextFilter())
    fastmcp_logger.addHandler(handler)
    fastmcp_logger.setLevel(logging.INFO)
    fastmcp_logger.propagate = False


configure_json_logging()

logger = logging.getLogger("fastmcp.plane_mcp")


class ServerMode(Enum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


def combined_lifespan(*apps):
    """Combine the lifespans of several mounted MCP apps into one."""

    @asynccontextmanager
    async def lifespan(_app):
        async with AsyncExitStack() as stack:
            for mounted in apps:
                await stack.enter_async_context(mounted.lifespan(mounted))
            yield

    return lifespan


def _build_http_app(prefix: str) -> Starlette:
    """Build the Starlette app for HTTP mode.

    OAuth (and the OAuth-only SSE transport) requires provider credentials.
    On self-host deployments PAT header auth is the primary mode, so when
    OAuth is not configured we serve only the header-auth endpoints instead
    of failing. The read-only endpoint (/http/api-key-readonly/mcp) exposes
    only list/retrieve/get/count/search/read tools - the surface meant for
    external agents (Tailscale Funnel, Perplexity).
    """
    header_app = get_header_mcp().http_app(stateless_http=True)
    readonly_app = get_readonly_header_mcp().http_app(stateless_http=True)

    if not os.getenv("PLANE_OAUTH_PROVIDER_CLIENT_ID"):
        logger.warning(
            "PLANE_OAUTH_PROVIDER_CLIENT_ID not set - OAuth and SSE endpoints disabled, "
            "serving header (PAT) auth at %s/http/api-key/mcp and read-only at "
            "%s/http/api-key-readonly/mcp",
            prefix,
            prefix,
        )
        return Starlette(
            routes=[
                _health_route(),
                Mount(prefix + "/http/api-key-readonly", app=readonly_app),
                Mount(prefix + "/http/api-key", app=header_app),
            ],
            lifespan=combined_lifespan(header_app, readonly_app),
        )

    oauth_mcp = get_oauth_mcp(prefix + "/http")
    oauth_app = oauth_mcp.http_app(stateless_http=True)

    sse_mcp = get_oauth_mcp(prefix)
    sse_app = sse_mcp.http_app(transport="sse")

    # mcp_path is appended to the auth provider's base_url to form the
    # advertised resource URL. base_url already carries the prefix, so these
    # stay at /mcp and /sse to avoid double-prefixing.
    oauth_well_known = oauth_mcp.auth.get_well_known_routes(mcp_path="/mcp")
    sse_well_known = sse_mcp.auth.get_well_known_routes(mcp_path="/sse")

    return Starlette(
        routes=[
            _health_route(),
            # Well-known routes for OAuth and Header HTTP
            *oauth_well_known,
            *sse_well_known,
            # Mount the MCP servers (most specific paths first)
            Mount(prefix + "/http/api-key-readonly", app=readonly_app),
            Mount(prefix + "/http/api-key", app=header_app),
            Mount(prefix + "/http", app=oauth_app),
            Mount(prefix or "/", app=sse_app),
        ],
        lifespan=combined_lifespan(oauth_app, header_app, readonly_app, sse_app),
    )


def main() -> None:
    """Run the MCP server."""
    server_mode = ServerMode.STDIO
    if len(sys.argv) > 1:
        server_mode = ServerMode(sys.argv[1])

    if server_mode == ServerMode.STDIO:
        # Validate API_KEY and PLANE_WORKSPACE_SLUG are set
        if not os.getenv("PLANE_API_KEY"):
            raise ValueError("PLANE_API_KEY is not set")
        if not os.getenv("PLANE_WORKSPACE_SLUG"):
            raise ValueError("PLANE_WORKSPACE_SLUG is not set")

        get_stdio_mcp().run()
        return

    if server_mode == ServerMode.HTTP:
        prefix = os.getenv("MCP_PATH_PREFIX") or ""

        app = _build_http_app(prefix)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Configure uvicorn loggers to use JSON formatting too
        for uv_logger_name in ("uvicorn", "uvicorn.error"):
            uv_logger = logging.getLogger(uv_logger_name)
            for h in uv_logger.handlers[:]:
                uv_logger.removeHandler(h)
            uv_handler = logging.StreamHandler(sys.stderr)
            uv_handler.setFormatter(JSONFormatter())
            uv_handler.addFilter(UserContextFilter())
            uv_logger.addHandler(uv_handler)

        logger.info("Starting HTTP server at URLs: /mcp and /header/mcp")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8211,
            log_level="info",
            access_log=False,
        )
        return


if __name__ == "__main__":
    main()
