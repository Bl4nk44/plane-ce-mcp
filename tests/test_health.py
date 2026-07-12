"""Tests for the /healthz probe and server-version reporting (Stage 3.2)."""

import plane_mcp.compat as compat
from plane_mcp import __version__
from plane_mcp.__main__ import _build_http_app
from plane_mcp.server import log_payloads


def test_log_payloads_off_by_default(monkeypatch):
    monkeypatch.delenv("LOG_PAYLOADS", raising=False)
    assert log_payloads() is False


def test_log_payloads_opt_in(monkeypatch):
    monkeypatch.setenv("LOG_PAYLOADS", "true")
    assert log_payloads() is True
    monkeypatch.setenv("LOG_PAYLOADS", "TRUE")
    assert log_payloads() is True
    monkeypatch.setenv("LOG_PAYLOADS", "1")
    assert log_payloads() is False


def test_healthz_returns_ok(monkeypatch):
    from starlette.testclient import TestClient

    # No OAuth creds -> header-only app; both branches mount /healthz.
    monkeypatch.delenv("PLANE_OAUTH_PROVIDER_CLIENT_ID", raising=False)
    app = _build_http_app("")
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["server_version"] == __version__


def test_describe_instance_reports_server_version(monkeypatch):
    monkeypatch.setattr(compat, "fetch_instance_profile", lambda base_url: {"edition": None, "version": None})
    info = compat.describe_instance("http://plane.local")
    assert info["server_version"] == __version__
    assert info["base_url"] == "http://plane.local"
