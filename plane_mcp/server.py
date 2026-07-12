"""FastMCP server factories for the three supported transports."""

from __future__ import annotations

import asyncio
import os

from fastmcp import FastMCP

from plane_mcp.annotations import is_read_only
from plane_mcp.auth import PlaneHeaderAuthProvider, PlaneOAuthProvider
from plane_mcp.instructions import SERVER_INSTRUCTIONS
from plane_mcp.middleware import PlaneLoggingMiddleware
from plane_mcp.storage import build_token_store
from plane_mcp.tools import register_tools

# Baseline redirect URIs shipped with the server. Additional patterns can be
# supplied at runtime via PLANE_OAUTH_ALLOWED_REDIRECT_URIS (comma-separated) so
# onboarding a new MCP client needs only a config change, not a new release.
DEFAULT_ALLOWED_REDIRECT_URIS = [
    # Localhost only for http (dynamic ports from MCP clients)
    "http://localhost:*",
    "http://localhost:*/*",
    "http://127.0.0.1:*",
    "http://127.0.0.1:*/*",
    # Known MCP client custom protocol schemes
    "cursor://anysphere.cursor-mcp/oauth/*",
    "https://www.cursor.com/*",
    "https://vscode.dev/redirect",
    "https://insiders.vscode.dev/redirect",
    "https://antigravity.google/oauth-callback",
    # Claude.ai web client
    "https://claude.ai/*",
    # ChatGPT connectors - per-connector callback + legacy redirect
    "https://chatgpt.com/connector/oauth/*",
    "https://chatgpt.com/connector_platform_oauth_redirect",
]


def log_payloads() -> bool:
    """Whether tool-call payloads are included in structured logs.

    Payloads can carry PII and full work-item descriptions, so they are OFF by
    default and enabled only with LOG_PAYLOADS=true (e.g. for debugging).
    """
    return os.getenv("LOG_PAYLOADS", "").lower() == "true"


def get_allowed_client_redirect_uris() -> list[str]:
    """Return the redirect URI allowlist: built-in defaults plus any extras
    from the PLANE_OAUTH_ALLOWED_REDIRECT_URIS env var (comma-separated)."""
    allowed = list(DEFAULT_ALLOWED_REDIRECT_URIS)
    extra = os.getenv("PLANE_OAUTH_ALLOWED_REDIRECT_URIS", "")
    for uri in extra.split(","):
        uri = uri.strip()
        if uri and uri not in allowed:
            allowed.append(uri)
    return allowed


def get_oauth_mcp(base_path: str = "/") -> FastMCP:
    """Build the FastMCP instance for the OAuth HTTP / SSE transports."""
    oauth_mcp = FastMCP(
        "plane-ce-mcp",
        instructions=SERVER_INSTRUCTIONS,
        website_url="https://github.com/Bl4nk44/plane-ce-mcp",
        auth=PlaneOAuthProvider(
            client_id=os.getenv("PLANE_OAUTH_PROVIDER_CLIENT_ID", ""),
            client_secret=os.getenv("PLANE_OAUTH_PROVIDER_CLIENT_SECRET", ""),
            base_url=f"{os.getenv('PLANE_OAUTH_PROVIDER_BASE_URL')}{base_path}",
            plane_base_url=os.getenv("PLANE_BASE_URL", ""),
            plane_internal_base_url=os.getenv("PLANE_INTERNAL_BASE_URL", ""),
            enable_cimd=os.getenv("PLANE_OAUTH_PROVIDER_ENABLE_CIMD", "false").lower() == "true",
            client_storage=build_token_store(),
            required_scopes=["read", "write"],
            allowed_client_redirect_uris=get_allowed_client_redirect_uris(),
        ),
    )
    oauth_mcp.add_middleware(PlaneLoggingMiddleware(include_payloads=log_payloads()))
    register_tools(oauth_mcp)
    return oauth_mcp


def get_header_mcp():
    header_mcp = FastMCP(
        "plane-ce-mcp (header-http)",
        instructions=SERVER_INSTRUCTIONS,
        auth=PlaneHeaderAuthProvider(
            required_scopes=["read", "write"],
        ),
    )
    header_mcp.add_middleware(PlaneLoggingMiddleware(include_payloads=log_payloads()))
    register_tools(header_mcp)
    return header_mcp


def get_stdio_mcp():
    stdio_mcp = FastMCP(
        "plane-ce-mcp (stdio)",
        instructions=SERVER_INSTRUCTIONS,
    )
    stdio_mcp.add_middleware(PlaneLoggingMiddleware(include_payloads=log_payloads()))
    register_tools(stdio_mcp)
    return stdio_mcp


def get_readonly_header_mcp():
    """Header-auth FastMCP exposing only read-only tools.

    Public surface for external agents (Perplexity et al., roadmap E13.4):
    a chat connector must not be able to mutate Plane data even with a valid
    PAT, so every non-read tool is removed after registration. "Read-only" is
    driven by the readOnlyHint tool annotation (see plane_mcp.annotations), the
    same signal MCP clients see - one source of truth, no separate prefix list.
    """
    readonly_mcp = FastMCP(
        "plane-ce-mcp (read-only)",
        instructions=SERVER_INSTRUCTIONS,
        auth=PlaneHeaderAuthProvider(
            required_scopes=["read", "write"],
        ),
    )
    readonly_mcp.add_middleware(PlaneLoggingMiddleware(include_payloads=log_payloads()))
    register_tools(readonly_mcp)
    for tool in asyncio.run(readonly_mcp.list_tools(run_middleware=False)):
        if not is_read_only(tool.annotations):
            readonly_mcp.remove_tool(tool.name)
    return readonly_mcp
