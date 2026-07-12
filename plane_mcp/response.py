"""Response-size guard for list tools.

Every byte a tool returns is loaded into the MCP client's context window. A
wide list call (many items, or heavy fields like description_html / expanded
relations) can dump hundreds of KB into a single turn and wreck the session.

`guard_result_size` is a safety net: when a serialized payload exceeds the
configured limit it returns an actionable error telling the caller how to
narrow the request, instead of shipping the blob. The default limit is generous
so ordinary paginated calls are untouched; it only trips on genuine blowups.
Set PLANE_MAX_RESPONSE_KB=0 to disable.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_RESPONSE_KB = 1024


def max_response_bytes() -> int:
    """Response-size limit in bytes from PLANE_MAX_RESPONSE_KB (0 disables)."""
    raw = os.getenv("PLANE_MAX_RESPONSE_KB")
    if raw is None or raw.strip() == "":
        kb = DEFAULT_MAX_RESPONSE_KB
    else:
        try:
            kb = int(raw)
        except ValueError:
            logger.warning("PLANE_MAX_RESPONSE_KB=%r is not an integer; using default %d", raw, DEFAULT_MAX_RESPONSE_KB)
            kb = DEFAULT_MAX_RESPONSE_KB
    return max(kb, 0) * 1024


def guard_result_size(payload: dict[str, Any], tool_name: str, narrow_hint: str) -> dict[str, Any]:
    """Return ``payload`` unchanged, or an error dict if it is too large.

    ``narrow_hint`` tells the caller how to shrink the request (which args to
    pass). ``total_count`` is preserved in the error so the caller still learns
    the size of the result set.
    """
    limit = max_response_bytes()
    if limit == 0:
        return payload
    size = len(json.dumps(payload, default=str).encode("utf-8"))
    if size <= limit:
        return payload
    logger.warning(
        "%s response is %d bytes (limit %d) - returning size-guard error instead of the payload",
        tool_name,
        size,
        limit,
    )
    return {
        "error": (
            f"{tool_name} response is too large to return safely "
            f"({size} bytes, limit {limit}). It was not sent to avoid overflowing the "
            f"context window."
        ),
        "hint": narrow_hint,
        "total_count": payload.get("total_count"),
        "response_bytes": size,
        "limit_bytes": limit,
        "limit_env": "PLANE_MAX_RESPONSE_KB",
    }
