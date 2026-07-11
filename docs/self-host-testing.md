# Self-host manual test checklist

Run against the local self-hosted Plane before merging any tool change. Use the
header-auth HTTP endpoint (`/http/api-key/mcp`) or stdio mode with env vars.

## Setup

```bash
# stdio
PLANE_API_KEY=... PLANE_WORKSPACE_SLUG=... PLANE_BASE_URL=http://<self-host>:<port> \
  python -m plane_mcp stdio

# or HTTP
PLANE_BASE_URL=http://<self-host>:<port> python -m plane_mcp http
```

Integration tests against a live instance:

```bash
export $(cat .env.test.local | xargs) && pytest tests/test_integration.py -v
```

## Core checklist (must pass)

- [ ] `list_projects` returns projects
- [ ] `create_work_item` in a test project; verify visible in Plane UI
- [ ] `update_work_item` — change name, state, priority
- [ ] `list_work_items` with and without filters
- [ ] `retrieve_work_item_by_identifier` (e.g. `PROJ-12`)
- [ ] `create_work_item_comment` + `list_work_item_comments`
- [ ] `list_states` / `list_labels` for the test project
- [ ] Cycles: `create_cycle`, `manage_cycle_work_items` (add + remove), `list_cycle_work_items`
- [ ] Modules: `create_module`, `manage_module_work_items`, `list_module_work_items`
- [ ] Delete created test entities (work item, cycle, module)

## Error-path checklist

- [ ] Invalid API key → clear auth error, no stack trace
- [ ] Nonexistent project id → clear 404 message naming the resource
- [ ] Wrong workspace slug → clear error

## Extended (when touched)

- [ ] Work item types / properties (CE feature availability — note results in
      `docs/plane-api-compat.md`)
- [ ] Intake, initiatives, milestones, pages, work logs
