# Rebrand Plan — standalone unofficial Plane MCP server

Goal: detach from `makeplane/plane-mcp-server`, rebrand as an independent, unofficial
MCP server **for self-hosted Plane (Community Edition)**. Cloud is out of scope as a
target: we don't remove Cloud code paths, but we stop advertising, testing, or
maintaining Cloud compatibility.

Decided: new name = **`plane-ce-mcp`**; old fork `Bl4nk44/plane-mcp-server` gets
**deleted** after the new repo is verified (CI green + fresh-install test passes).

## Positioning statement (drives all copy)

> Unofficial MCP server for **self-hosted Plane (Community Edition)**.
> Upstream targets Plane Cloud; CE users hit missing lite endpoints, raw SDK
> stack traces, and no pages support. This project fixes that: a central
> compatibility layer, transparent endpoint fallbacks, PAT-only HTTP auth,
> and pages tools via the internal API.

Legal basis: upstream is MIT. We keep the original LICENSE and copyright notice,
add our own copyright line. We do not use the Plane logo and clearly state
"unofficial, not affiliated with Plane / makeplane".

## Stages (each = one PR, ≤150 lines diff)

### Stage R1 — Repo detach + metadata

1. Create fresh GitHub repo `Bl4nk44/plane-ce-mcp` (NOT a fork — kills the
   "forked from makeplane" banner without a support ticket).
2. `git push --mirror` from local clone; update `origin` to the new repo.
   Keep remote `upstream` = makeplane for future cherry-picks.
3. Delete the old fork `Bl4nk44/plane-mcp-server` — only after CI green + fresh-install test on the new repo.
4. `pyproject.toml`:
   - `name = "plane-ce-mcp"`
   - `version = "1.0.0"` — independence marker; upstream lineage noted in README.
   - `authors`: add maintainer; move original authors to a `# Original authors (upstream)` credit
     or keep both entries.
   - Add `[project.urls]` (Homepage, Repository, Issues) pointing at the new repo.
   - `description`: "Unofficial MCP server for self-hosted Plane (Community Edition)".
5. `LICENSE`: add `Copyright (c) 2026 Bl4nk44` line above the existing
   `Copyright (c) 2025 Plane MCP Server Contributors` (keep the original — MIT requires it).
6. `glama.json`: update `maintainers` or delete the file (it registers the *upstream*
   listing on glama.ai; a stale entry misleads).

### Stage R2 — README rewrite

Full rewrite, self-host-first:

- Title: `plane-ce-mcp` + one-liner from the positioning statement.
- "Why this exists" section: upstream = Cloud-first; CE gaps we fixed
  (compat layer `plane_mcp/compat.py`, lite-endpoint fallbacks, PAT-only HTTP mode,
  pages via internal API, content truncation, actionable 404/401 errors).
- Features list rewritten around CE; drop "Remote & Local" Cloud framing.
- Cloud note (honesty, one line): "May still work against Plane Cloud — untested,
  not maintained, not a goal."
- Attribution section: "Based on [makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server)
  (MIT). Not affiliated with Plane."
- Tool tables: verify against current `plane_mcp/tools/` (19 modules, 55+ tools,
  including pages/search_pages added in this fork).
- Setup docs: lead with self-host config (`PLANE_BASE_URL` **required** for CE —
  default still points at api.plane.so; document explicitly).

### Stage R3 — Community files

- `CONTRIBUTING.md`: rewrite — contribution flow for this repo (fork → PR,
  ruff, pytest, self-host test checklist). Remove plane.so references.
- `SECURITY.md`: replace plane.so contact with GitHub Security Advisories on the new repo.
- `CODE_OF_CONDUCT.md`: keep Contributor Covenant, swap contact email; or delete.

### Stage R4 — CLAUDE.md + docs

- `CLAUDE.md`:
  - "Fork Mission" → "Project Mission": standalone unofficial CE-focused server.
    Drop "while remaining compatible with Plane Cloud" from the mission.
  - "Prohibitions": drop the "keep upstream syncs mergeable" constraint on CLAUDE.md
    edits (no longer syncing wholesale); keep the rest.
  - "Upstream Sync" → "Upstream cherry-picks": review upstream occasionally,
    cherry-pick generally useful fixes; offering PRs upstream becomes optional.
- `docs/roadmap.md`: add rebrand stage, mark Cloud-compat items out of scope.
- `docs/plane-api-compat.md`: keep (it documents CE vs Cloud — still the core
  technical asset), reframe intro: Cloud column = historical reference, not target.
- `.claude/skills/docker-release/SKILL.md` + `deploy/docker-compose.yml`:
  image name → `plane-ce-mcp`.

### Stage R5 — Code touch-ups (minimal, zero behavior change)

- `plane_mcp/server.py:57-58`: `icons` (plane.so favicon) and `website_url`
  (`https://plane.so`) → new repo URL, drop the Plane favicon (trademark hygiene —
  this is what MCP clients display as the server identity).
- Server `name`/instructions strings if they claim to be official Plane.
- **Do NOT change**: default `PLANE_BASE_URL` (behavior), package dir `plane_mcp`
  (import churn, no benefit), tool names/signatures (MCP clients depend on them),
  OAuth/Cloud code paths (leave working, just unadvertised).

### Stage R6 — Verification + release

- `pytest` full suite against local self-host instance.
- `docs/self-host-testing.md` manual checklist.
- Fresh-install test: `uvx --from git+https://github.com/Bl4nk44/plane-ce-mcp ...` stdio mode.
- Tag `v1.0.0`, build Docker image under the new name.
- Optional later: PyPI publish (name must be free on PyPI — check before finalizing).

## Decisions

1. **Name**: `plane-ce-mcp` (descriptive, trademark-safe; "unofficial" stated in README).
   Rejected: `plane-selfhost-mcp`, `unofficial-plane-mcp`.
2. **Old fork**: delete after new repo verified (R6 green).
3. **PyPI publish**: deferred — check name availability before publishing.

## Out of scope

- Renaming the `plane_mcp` Python package/imports.
- Removing OAuth / Cloud code paths.
- Any tool behavior changes.
