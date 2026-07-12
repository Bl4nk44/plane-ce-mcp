"""Pytest configuration for Plane MCP Server tests."""

import pytest


@pytest.fixture(autouse=True)
def _disable_retries(monkeypatch):
    """Disable the compat proxy's retry/backoff by default.

    Retries would make error-path tests slow and timing-dependent (real
    backoff sleeps). Retry behaviour is covered explicitly in test_retry.py,
    which sets PLANE_MAX_RETRIES itself.
    """
    monkeypatch.setenv("PLANE_MAX_RETRIES", "0")
