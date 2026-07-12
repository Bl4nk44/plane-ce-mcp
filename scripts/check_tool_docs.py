#!/usr/bin/env python
"""Fail if the README tool tables drift from the registered tools.

The README hand-maintains per-domain tool tables with curated descriptions, so
this does not regenerate them - it enforces completeness: every registered tool
(with `PLANE_TOOLSETS=all`) must appear in a README tool table, and every tool
listed in the README must still exist. Run in CI and locally:

    python scripts/check_tool_docs.py

Exit code 0 when in sync, 1 (with a diff) otherwise.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from fastmcp import FastMCP

from plane_mcp.tools import register_tools

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

# A tool table row: first cell is a backticked lower-case identifier.
_ROW = re.compile(r"^\|\s*`([a-z][a-z0-9_]+)`\s*\|")


def registered_tools() -> set[str]:
    mcp = FastMCP("doc-check")
    register_tools(mcp, "all")
    return {t.name for t in asyncio.run(mcp.list_tools(run_middleware=False))}


def documented_tools() -> set[str]:
    names: set[str] = set()
    for line in README.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            names.add(m.group(1))
    return names


def main() -> int:
    registered = registered_tools()
    documented = documented_tools()

    missing = sorted(registered - documented)  # registered but not in README
    stale = sorted(documented - registered)  # in README but not registered

    if not missing and not stale:
        print(f"OK: all {len(registered)} tools documented in README.")
        return 0

    if missing:
        print(f"Tools missing from README ({len(missing)}):")
        for name in missing:
            print(f"  - {name}")
    if stale:
        print(f"README lists tools that are not registered ({len(stale)}):")
        for name in stale:
            print(f"  - {name}")
    print("\nUpdate the tool tables in README.md to match.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
