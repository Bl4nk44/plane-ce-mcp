"""Plane MCP Server - A Model Context Protocol server for Plane integration."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("plane-ce-mcp")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
