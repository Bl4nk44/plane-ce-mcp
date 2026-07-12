# plane-ce-mcp

**Unofficial MCP server for self-hosted Plane (Community Edition).**

A Model Context Protocol server exposing Plane's project management API as MCP tools,
built for people who run Plane themselves. Based on
[makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server) (MIT).
Not affiliated with Plane / makeplane.

## Why this exists

The upstream server targets Plane Cloud. Run it against a self-hosted Community
Edition instance and you hit missing "lite" endpoints, raw SDK stack traces on every
404, and no pages support. This project fixes what upstream didn't:

* **Central compatibility layer** ([plane_mcp/compat.py](plane_mcp/compat.py)): every
  Plane API error becomes an actionable message - missing endpoint vs missing resource
  vs auth vs timeout. No raw SDK exceptions reach the MCP client.
* **Transparent endpoint fallbacks**: lite endpoints absent on CE fall back to the
  full endpoints (projects, cycles, modules, project/workspace members), with the
  fallback logged for diagnosability.
* **PAT-only HTTP mode**: the HTTP transport runs without any OAuth configuration -
  header auth alone (`/http/api-key/mcp`).
* **Pages tools on CE**: list/retrieve/search/create pages via Plane's internal API
  (CE has no public pages API), with content truncation for LLM-sized outputs.
* **Documented CE vs Cloud differences**: [docs/plane-api-compat.md](docs/plane-api-compat.md).

May still work against Plane Cloud - untested, unmaintained, not a goal.

## Quick start

Requirements: **Python 3.10+** and [uv](https://docs.astral.sh/uv/). No clone, no
install - `uvx` runs the server straight from GitHub.

**1. Get your credentials from Plane:**

- API key: Plane → Workspace Settings → API tokens → create token
- Workspace slug: the part of your Plane URL after the host
  (`https://plane.your-domain.tld/<slug>/`)

**2. Smoke-test the server** (optional, confirms connectivity):

```bash
PLANE_API_KEY=<your-api-key> \
PLANE_WORKSPACE_SLUG=<your-workspace-slug> \
PLANE_BASE_URL=https://plane.your-domain.tld \
uvx --from git+https://github.com/Bl4nk44/plane-ce-mcp plane-ce-mcp stdio
```

Server starts and waits for MCP messages on stdin - Ctrl+C to exit. Errors at this
point mean wrong URL or key, not a client problem.

**3. Add to your MCP client** (Claude Code, Claude Desktop, Cursor, ...):

```json
{
  "mcpServers": {
    "plane": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Bl4nk44/plane-ce-mcp", "plane-ce-mcp", "stdio"],
      "env": {
        "PLANE_API_KEY": "<your-api-key>",
        "PLANE_WORKSPACE_SLUG": "<your-workspace-slug>",
        "PLANE_BASE_URL": "https://plane.your-domain.tld"
      }
    }
  }
}
```

For Claude Code that's one command:

```bash
claude mcp add plane \
  -e PLANE_API_KEY=<your-api-key> \
  -e PLANE_WORKSPACE_SLUG=<your-workspace-slug> \
  -e PLANE_BASE_URL=https://plane.your-domain.tld \
  -- uvx --from git+https://github.com/Bl4nk44/plane-ce-mcp plane-ce-mcp stdio
```

`PLANE_BASE_URL` must point at your instance's API - the default is Plane Cloud
(`https://api.plane.so`), so self-host setups **must** set it.

### Run from source

```bash
git clone https://github.com/Bl4nk44/plane-ce-mcp.git
cd plane-ce-mcp
uv pip install -e .
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... PLANE_BASE_URL=... python -m plane_mcp stdio
```

## HTTP transport (self-hosted, PAT auth)

Run the server next to your Plane instance (port 8211):

```bash
PLANE_BASE_URL=https://plane.your-domain.tld python -m plane_mcp http
```

Connect with a Personal Access Token - no OAuth setup required:

**URL**: `http://<server>:8211/http/api-key/mcp`

**Headers**:
- `Authorization: Bearer <PAT_TOKEN>` (or `x-api-key: <PAT_TOKEN>`)
- `X-Workspace-slug: <SLUG>`

```json
{
  "mcpServers": {
    "plane": {
      "command": "npx",
      "args": ["mcp-remote@latest", "http://<server>:8211/http/api-key/mcp"],
      "headers": {
        "Authorization": "Bearer <PAT_TOKEN>",
        "X-Workspace-slug": "<SLUG>"
      }
    }
  }
}
```

An OAuth endpoint (`/oauth/mcp`) and a legacy SSE transport also exist for setups
with a configured Plane OAuth app - see [Configuration](#configuration). Deployment
recipes (Docker Compose, Caddy, Tailscale) live in [deploy/](deploy/) and
[docs/tailscale-deployment.md](docs/tailscale-deployment.md).

## Configuration

| Variable | Required for | Purpose |
|---|---|---|
| `PLANE_BASE_URL` | all (self-host: **required**) | Your Plane API URL (default: `https://api.plane.so` = Cloud) |
| `PLANE_API_KEY` | stdio | API key (workspace settings → API tokens) |
| `PLANE_WORKSPACE_SLUG` | stdio | Target workspace |
| `PLANE_INTERNAL_BASE_URL` | http/sse (optional) | Internal URL for server-to-server calls (e.g. `http://plane-api:8000` inside Docker) |
| `PLANE_INTERNAL_API_EMAIL` / `PLANE_INTERNAL_API_PASSWORD` | pages tools | Plane account used by the internal-API adapter (CE has no public pages API); the account needs membership in the relevant projects |
| `PLANE_PAGES_MAX_CONTENT_LENGTH` | optional | Default truncation for `retrieve_page` content |
| `REDIS_HOST` / `REDIS_PORT` | http/sse (optional) | Token storage (falls back to in-memory) |
| `PLANE_OAUTH_PROVIDER_*` | http/sse OAuth only | OAuth client credentials and base URL |
| `PLANE_OAUTH_ALLOWED_REDIRECT_URIS` | http/sse OAuth (optional) | Comma-separated redirect URI patterns appended to the built-in allowlist |
| `LOG_USER_INFO` | optional (default: `false`) | When `true`, include user display name (PII) in logs alongside the opaque user id |

### Logging

The server emits structured JSON logs. Each tool call is logged with its tool name,
duration, status, and (when available) the opaque user id and workspace slug.
Endpoint fallbacks are logged when they trigger (which endpoint failed, which was
used instead), so CE quirks are diagnosable from logs.

## Available Tools

All tools use Pydantic models from the Plane SDK for type safety and validation.

### Projects

| Tool Name | Description |
|-----------|-------------|
| `list_projects` | List all projects in a workspace with optional pagination and filtering |
| `create_project` | Create a new project with name, identifier, and optional configuration |
| `retrieve_project` | Retrieve a project by ID |
| `update_project` | Update a project with partial data |
| `delete_project` | Delete a project by ID |
| `get_project_worklog_summary` | Get work log summary for a project |
| `get_project_members` | Get all members of a project |
| `update_project_features` | Update features configuration of a project |

### Work Items

| Tool Name | Description |
|-----------|-------------|
| `list_work_items` | List all work items in a project with optional filtering and pagination |
| `create_work_item` | Create a new work item with name, assignees, labels, and other attributes |
| `retrieve_work_item` | Retrieve a work item by ID with optional field expansion |
| `retrieve_work_item_by_identifier` | Retrieve a work item by project identifier and issue sequence number |
| `update_work_item` | Update a work item with partial data |
| `delete_work_item` | Delete a work item by ID |
| `search_work_items` | Search work items across a workspace with query string |

### Cycles

| Tool Name | Description |
|-----------|-------------|
| `list_cycles` | List cycles in a project (set `archived=true` for archived) |
| `create_cycle` | Create a new cycle with name, dates, and owner |
| `retrieve_cycle` | Retrieve a cycle by ID |
| `update_cycle` | Update a cycle with partial data |
| `delete_cycle` | Delete a cycle by ID |
| `manage_cycle_work_items` | Add and/or remove work items on a cycle |
| `list_cycle_work_items` | List work items in a cycle |
| `transfer_cycle_work_items` | Transfer work items from one cycle to another |
| `manage_cycle_archive` | Archive or unarchive a cycle |

### Modules

| Tool Name | Description |
|-----------|-------------|
| `list_modules` | List modules in a project (set `archived=true` for archived) |
| `create_module` | Create a new module with name, dates, status, and members |
| `retrieve_module` | Retrieve a module by ID |
| `update_module` | Update a module with partial data |
| `delete_module` | Delete a module by ID |
| `manage_module_work_items` | Add and/or remove work items on a module |
| `list_module_work_items` | List work items in a module |
| `manage_module_archive` | Archive or unarchive a module |

### Initiatives

| Tool Name | Description |
|-----------|-------------|
| `list_initiatives` | List all initiatives in a workspace |
| `create_initiative` | Create a new initiative with name, dates, state, and lead |
| `retrieve_initiative` | Retrieve an initiative by ID |
| `update_initiative` | Update an initiative with partial data |
| `delete_initiative` | Delete an initiative by ID |

### Intake Work Items

| Tool Name | Description |
|-----------|-------------|
| `list_intake_work_items` | List all intake work items in a project with optional pagination |
| `create_intake_work_item` | Create a new intake work item in a project |
| `retrieve_intake_work_item` | Retrieve an intake work item by work item ID with optional field expansion |
| `update_intake_work_item` | Update an intake work item with partial data |
| `delete_intake_work_item` | Delete an intake work item by work item ID |

### Work Item Properties

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_properties` | List work item properties for a work item type |
| `create_work_item_property` | Create a new work item property with type, settings, and validation rules |
| `retrieve_work_item_property` | Retrieve a work item property by ID |
| `update_work_item_property` | Update a work item property with partial data |
| `delete_work_item_property` | Delete a work item property by ID |

### Milestones

| Tool Name | Description |
|-----------|-------------|
| `list_milestones` | List all milestones in a project |
| `create_milestone` | Create a new milestone |
| `retrieve_milestone` | Retrieve a milestone by ID |
| `update_milestone` | Update a milestone by ID |
| `delete_milestone` | Delete a milestone by ID |
| `manage_milestone_work_items` | Add and/or remove work items on a milestone |
| `list_milestone_work_items` | List work items in a milestone |

### Labels

| Tool Name | Description |
|-----------|-------------|
| `list_labels` | List all labels in a project |
| `create_label` | Create a new label |
| `retrieve_label` | Retrieve a label by ID |
| `update_label` | Update a label by ID |
| `delete_label` | Delete a label by ID |

### States

| Tool Name | Description |
|-----------|-------------|
| `list_states` | List all states in a project |
| `create_state` | Create a new state |
| `retrieve_state` | Retrieve a state by ID |
| `update_state` | Update a state by ID |
| `delete_state` | Delete a state by ID |

### Work Item Comments

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_comments` | List comments for a work item |
| `retrieve_work_item_comment` | Retrieve a specific comment for a work item |
| `create_work_item_comment` | Create a comment for a work item |
| `update_work_item_comment` | Update a comment for a work item |
| `delete_work_item_comment` | Delete a comment for a work item |

### Work Item Links

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_links` | List links for a work item |
| `retrieve_work_item_link` | Retrieve a specific link for a work item |
| `create_work_item_link` | Create a link for a work item |
| `update_work_item_link` | Update a link for a work item |
| `delete_work_item_link` | Delete a link for a work item |

### Work Item Types

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_types` | List all work item types in a project |
| `create_work_item_type` | Create a new work item type |
| `retrieve_work_item_type` | Retrieve a work item type by ID |
| `update_work_item_type` | Update a work item type by ID |
| `delete_work_item_type` | Delete a work item type by ID |
| `import_work_item_types_to_project` | Bulk-link workspace-level work item types to a project |
| `resolve_work_item_type` | Find or create a named type for a project, auto-handling workspace vs project scope and import |

### Work Item Relations

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_relations` | List relations for a work item |
| `create_work_item_relation` | Create relations for a work item |
| `remove_work_item_relation` | Remove a relation from a work item |

### Work Item Relation Definitions

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_relation_definitions` | List workspace custom relation definitions |
| `create_work_item_relation_definition` | Create a workspace relation definition |
| `update_work_item_relation_definition` | Update a relation definition |
| `delete_work_item_relation_definition` | Delete a relation definition |

### Work Item Activities

| Tool Name | Description |
|-----------|-------------|
| `list_work_item_activities` | List activities for a work item |
| `retrieve_work_item_activity` | Retrieve a specific activity for a work item |

### Work Logs

| Tool Name | Description |
|-----------|-------------|
| `list_work_logs` | List work logs for a work item |
| `create_work_log` | Create a work log for a work item |
| `update_work_log` | Update a work log for a work item |
| `delete_work_log` | Delete a work log for a work item |

### Pages

| Tool Name | Description |
|-----------|-------------|
| `list_pages` | List pages - metadata only (workspace, or a project's if `project_id` given) |
| `retrieve_page` | Retrieve a page incl. content; optional `max_length` truncation (env default `PLANE_PAGES_MAX_CONTENT_LENGTH`) |
| `search_pages` | Search pages by title, optionally inside content (client-side, case-insensitive) |
| `create_page` | Create a workspace or project page |

### Workspaces

| Tool Name | Description |
|-----------|-------------|
| `get_workspace_members` | Get all members of the current workspace |
| `get_features` | Get feature flags (workspace, or a project's if `project_id` given) |
| `update_workspace_features` | Update features of the current workspace |

### Users

| Tool Name | Description |
|-----------|-------------|
| `get_me` | Get current authenticated user information |

### Instance

| Tool Name | Description |
|-----------|-------------|
| `get_instance_info` | Get edition/version of the connected Plane instance and its known API limitations (e.g. Community Edition) |

**Total Tools**: 100+ tools across 20 categories

## Development

```bash
# Install (uses uv)
uv pip install -e ".[dev]"

# Tests
pytest

# Format + lint
ruff format plane_mcp/
ruff check plane_mcp/
```

Integration tests run against a live Plane instance - copy `.env.test` to
`.env.test.local` with real values, then `export $(cat .env.test.local | xargs) && pytest tests/ -v`.

## Attribution & License

MIT License - see [LICENSE](LICENSE).

Based on [makeplane/plane-mcp-server](https://github.com/makeplane/plane-mcp-server)
(MIT, © 2025 Plane MCP Server Contributors). This is an independent, unofficial
project: not affiliated with, endorsed by, or supported by Plane / makeplane.
"Plane" is a trademark of its respective owner.

## Contributing

Contributions welcome - especially fixes for self-hosted Community Edition quirks.
See [CONTRIBUTING.md](CONTRIBUTING.md).
