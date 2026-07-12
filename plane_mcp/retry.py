"""Retry-with-backoff for transient Plane API failures.

Self-hosted Plane sits behind reverse proxies (Caddy/Tailscale/Nginx) and can
briefly return 502/503/504 during restarts or rate-limit with 429. Failing the
whole tool call on the first blip is the single biggest reliability gap versus a
resilient client, so the compat proxy retries transient failures with
exponential backoff and jitter.

Safety: a write that timed out or hit a gateway error MAY already have been
applied server-side, so retrying it risks duplicates. We therefore retry
timeouts / 502 / 504 only for read-only operations, and retry 429 / 503 (request
rejected or explicitly deferred, not applied) for every operation. Connection
errors that never reached the server are safe to retry for anything.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from fastmcp.utilities.logging import get_logger
from plane.errors import HttpError

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 2
DEFAULT_BASE_DELAY = 0.5
MAX_DELAY = 10.0

# Server rejected or deferred the request without applying it -> safe to retry
# for any operation.
_RETRY_ANY_STATUS = frozenset({429, 503})
# Gateway/timeout: a write may already have landed -> retry read-only only.
_RETRY_READ_ONLY_STATUS = frozenset({502, 504})

_READ_VERBS = ("list", "retrieve", "get", "count", "search", "read")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        logger.warning("%s=%r is not an integer; using default %d", name, raw, default)
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(float(raw), 0.0)
    except ValueError:
        logger.warning("%s=%r is not a number; using default %s", name, raw, default)
        return default


def max_retries() -> int:
    """Retries after the first attempt (PLANE_MAX_RETRIES, default 2)."""
    return _int_env("PLANE_MAX_RETRIES", DEFAULT_MAX_RETRIES)


def is_read_only_operation(operation: str) -> bool:
    """True if the SDK operation (e.g. ``work_items.list``) only reads data."""
    method = operation.rsplit(".", 1)[-1]
    return method.startswith(_READ_VERBS)


def _is_retryable(exc: Exception, read_only: bool) -> bool:
    if isinstance(exc, HttpError):
        if exc.status_code in _RETRY_ANY_STATUS:
            return True
        if exc.status_code in _RETRY_READ_ONLY_STATUS:
            return read_only
        return False
    # A connection that never established did not apply anything -> always safe.
    if isinstance(exc, httpx.ConnectError):
        return True
    # Other timeouts / transport errors: a write may have landed -> read-only only.
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return read_only
    return False


def _backoff_delay(attempt: int, base: float) -> float:
    """Exponential backoff (attempt starts at 1) with full jitter, capped."""
    ceiling = min(base * (2 ** (attempt - 1)), MAX_DELAY)
    return random.uniform(0, ceiling)


def call_with_retries(
    func: Callable[[], T],
    operation: str,
    *,
    read_only: bool,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``func`` retrying transient failures per the module's safety rules.

    Non-retryable exceptions propagate immediately so the compat proxy can
    translate them into actionable ToolErrors.
    """
    retries = max_retries()
    base = _float_env("PLANE_RETRY_BASE_DELAY", DEFAULT_BASE_DELAY)
    attempt = 0
    while True:
        attempt += 1
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - re-raised unless provably transient
            if attempt > retries or not _is_retryable(exc, read_only):
                raise
            delay = _backoff_delay(attempt, base)
            logger.warning(
                "Plane API call %s failed (%s: %s); retry %d/%d in %.2fs",
                operation,
                type(exc).__name__,
                exc,
                attempt,
                retries,
                delay,
            )
            sleep(delay)
