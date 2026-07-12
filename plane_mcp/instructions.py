SERVER_INSTRUCTIONS = """
This server exposes a self-hosted Plane (Community Edition) workspace as MCP
tools. Read this before your first calls.

## Orientation

- Call `get_instance_info` once to learn the Plane edition/version and which API
  families are unavailable on this instance (Community Edition lacks pages,
  work-item types/epics, initiatives, estimates and milestones). Prefer this
  over discovering gaps through 404 errors.
- Call `list_toolsets` to see which tool groups are active. If a tool you expect
  is missing, the operator may have narrowed PLANE_TOOLSETS.

## Resolving names to IDs

Most write tools take UUIDs, not names. Given a human name or short identifier,
call the matching `list_*` tool first and match on `name`/`identifier` to get the
`id`: projects -> `list_projects`, states -> `list_states`, labels ->
`list_labels`, members -> `get_project_members` / `get_workspace_members`,
cycles -> `list_cycles`, modules -> `list_modules`.

## Listing and pagination

- List tools are paginated: pass `per_page` (1-100, default 25) and `cursor`
  (from the previous response's `next_cursor`). `total_count` is the true DB
  total, not the page size - use it for counts.
- `list_work_items` accepts a sparse `fields` list (e.g. `id,name,sequence_id,state`).
  Use it to keep responses small; heavy fields like `description_html` are only
  returned when you ask for them. A field you omit comes back null - null means
  "not requested", not "empty".
- To count without fetching bodies, use `count_work_items` (supports grouping).
- Very large list responses are refused with an actionable error telling you to
  narrow with `fields`/`per_page`/PQL rather than overflowing your context.

## PQL (filtering work items)

`list_work_items`, `list_archived_work_items`, `list_cycle_work_items`,
`list_module_work_items` and `count_work_items` take an optional `pql` filter.
Read the `resource://pql-reference` resource (or call `get_pql_reference`) before
composing anything beyond a trivial filter. On a bad filter the tool returns the
reference inline so you can self-correct in one step.

## Epics

There are no epic tools - an epic is a work item whose type is named "Epic". Work
items always belong to a project; ask which if one is not named.
1. type = resolve_work_item_type(project_id, "Epic") - type.id is the type_id.
2. Create: create_work_item(project_id, type_id=type.id, name=...).
3. List: list_work_items(project_id, pql='type = "<type id>"').
4. Read / update / delete / nest: retrieve_work_item / update_work_item /
   delete_work_item by work item id (set parent=<work item id> to nest).
5. List an epic's children: list_work_items(project_id, pql='childOf("<EPIC-IDENTIFIER>")')
   using the epic's human-readable identifier (e.g. "PROJ-12") from retrieve_work_item.
"""
