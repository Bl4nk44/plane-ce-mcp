"""Page-related tools for Plane MCP Server."""

import os
import re
from typing import Any

from fastmcp import FastMCP
from plane.models.pages import CreatePage, Page
from plane.models.work_item_pages import CreateWorkItemPage, WorkItemPage

from plane_mcp.client import get_plane_client_context

# Search-with-content fetches each candidate page individually; cap the number
# of detail requests so one search cannot hammer the Plane API.
SEARCH_CONTENT_FETCH_LIMIT = 30


def _default_max_content_length() -> int | None:
    """Server-wide default for page content truncation (env, optional)."""
    raw = os.getenv("PLANE_PAGES_MAX_CONTENT_LENGTH", "")
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def truncate_page_content(page: Page, max_length: int | None) -> Page | dict[str, Any]:
    """Truncate a page's content fields to max_length characters.

    Returns the Page unchanged when no truncation applies; otherwise returns a
    dict with the page fields plus `content_truncated` and
    `total_content_length` so the caller knows the content is partial.
    """
    if max_length is None:
        max_length = _default_max_content_length()
    html = page.description_html or ""
    if max_length is None or len(html) <= max_length:
        return page
    data = page.model_dump()
    data["description_html"] = html[:max_length]
    stripped = data.get("description_stripped")
    if isinstance(stripped, str) and len(stripped) > max_length:
        data["description_stripped"] = stripped[:max_length]
    data["content_truncated"] = True
    data["total_content_length"] = len(html)
    return data


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _snippet(text: str, query: str, context: int = 80) -> str:
    index = text.lower().find(query.lower())
    if index < 0:
        return text[: context * 2].strip()
    start = max(0, index - context)
    return text[start : index + len(query) + context].strip()


def match_pages_by_name(pages: list[Page], query: str, project_id: str | None) -> list[dict[str, Any]]:
    """Case-insensitive title matches, in list order."""
    needle = query.lower()
    return [
        {
            "id": page.id,
            "name": page.name,
            "project_id": project_id,
            "match_field": "name",
            "snippet": page.name,
        }
        for page in pages
        if needle in (page.name or "").lower()
    ]


def match_page_content(page_detail: Page, query: str, project_id: str | None) -> dict[str, Any] | None:
    """Content match for one fetched page detail, or None."""
    text = page_detail.description_stripped or _strip_html(page_detail.description_html or "")
    if query.lower() not in text.lower():
        return None
    return {
        "id": page_detail.id,
        "name": page_detail.name,
        "project_id": project_id,
        "match_field": "content",
        "snippet": _snippet(text, query),
    }


def register_page_tools(mcp: FastMCP) -> None:
    """Register all page-related tools with the MCP server."""

    @mcp.tool()
    def list_pages(
        project_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[Page]:
        """
        List pages.

        Lists a project's pages if project_id is given, otherwise workspace-level pages.
        The list contains metadata only - description_html is null here by design;
        fetch a page's content with retrieve_page.

        Args:
            project_id: UUID of the project. Omit to list workspace pages.
            params: Optional query parameters as a dictionary (e.g., per_page, cursor)

        Returns:
            List of Page objects (metadata only, no page content)
        """
        client, workspace_slug = get_plane_client_context()
        if project_id is not None:
            response = client.pages.list_project_pages(
                workspace_slug=workspace_slug, project_id=project_id, params=params
            )
        else:
            response = client.pages.list_workspace_pages(workspace_slug=workspace_slug, params=params)
        return response.results

    @mcp.tool()
    def attach_page_to_work_item(
        project_id: str,
        work_item_id: str,
        page_id: str,
    ) -> WorkItemPage:
        """
        Link a page to a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item
            page_id: UUID of the page to link

        Returns:
            WorkItemPage link object
        """
        client, workspace_slug = get_plane_client_context()
        return client.work_items.pages.create(
            workspace_slug=workspace_slug,
            project_id=project_id,
            work_item_id=work_item_id,
            data=CreateWorkItemPage(page_id=page_id),
        )

    @mcp.tool()
    def list_work_item_pages(
        project_id: str,
        work_item_id: str,
    ) -> list[WorkItemPage]:
        """
        List all pages linked to a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item

        Returns:
            List of WorkItemPage link objects
        """
        client, workspace_slug = get_plane_client_context()
        response = client.work_items.pages.list(
            workspace_slug=workspace_slug,
            project_id=project_id,
            work_item_id=work_item_id,
        )
        return response.results

    @mcp.tool()
    def detach_page_from_work_item(
        project_id: str,
        work_item_id: str,
        work_item_page_id: str,
    ) -> None:
        """
        Remove a page link from a work item.

        Args:
            project_id: UUID of the project
            work_item_id: UUID of the work item
            work_item_page_id: UUID of the work item page link (not the page ID)
        """
        client, workspace_slug = get_plane_client_context()
        client.work_items.pages.delete(
            workspace_slug=workspace_slug,
            project_id=project_id,
            work_item_id=work_item_id,
            work_item_page_id=work_item_page_id,
        )

    @mcp.tool()
    def retrieve_page(
        page_id: str,
        project_id: str | None = None,
        max_length: int | None = None,
    ) -> Page | dict[str, Any]:
        """
        Retrieve a page by ID, including its content (description_html).

        Retrieves a project page if project_id is given, otherwise a workspace page.
        Page bodies can be large; pass max_length (or set the server-side
        PLANE_PAGES_MAX_CONTENT_LENGTH env default) to bound the returned content.

        Args:
            page_id: UUID of the page
            project_id: UUID of the project. Omit for a workspace page.
            max_length: Maximum number of characters of content to return. When
                the content is longer, the response carries content_truncated=true
                and total_content_length with the full size.

        Returns:
            Page object; when truncation applies, a dict with the page fields
            plus content_truncated and total_content_length.
        """
        client, workspace_slug = get_plane_client_context()

        if project_id is not None:
            page = client.pages.retrieve_project_page(
                workspace_slug=workspace_slug,
                project_id=project_id,
                page_id=page_id,
            )
        else:
            page = client.pages.retrieve_workspace_page(
                workspace_slug=workspace_slug,
                page_id=page_id,
            )
        return truncate_page_content(page, max_length)

    @mcp.tool()
    def search_pages(
        query: str,
        project_id: str | None = None,
        search_content: bool = False,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search pages by title (and optionally content) with a simple
        case-insensitive substring match.

        Plane has no server-side page search API, so this filters the page list
        client-side. With search_content=true each candidate page's content is
        fetched individually (capped at 30 pages) - slower but matches body text.

        Args:
            query: Text to look for (case-insensitive substring).
            project_id: UUID of the project. Omit to search workspace pages
                (workspace pages are unavailable on Community Edition).
            search_content: Also search inside page content, not just titles.
            max_results: Maximum number of matches to return (default 20).

        Returns:
            List of matches: id, name, project_id, match_field ("name" or
            "content") and a snippet of the surrounding text.
        """
        client, workspace_slug = get_plane_client_context()
        if project_id is not None:
            response = client.pages.list_project_pages(workspace_slug=workspace_slug, project_id=project_id)
        else:
            response = client.pages.list_workspace_pages(workspace_slug=workspace_slug)
        pages = response.results

        matches = match_pages_by_name(pages, query, project_id)
        if search_content:
            matched_ids = {m["id"] for m in matches}
            candidates = [p for p in pages if p.id not in matched_ids][:SEARCH_CONTENT_FETCH_LIMIT]
            for page in candidates:
                if len(matches) >= max_results:
                    break
                if project_id is not None:
                    detail = client.pages.retrieve_project_page(
                        workspace_slug=workspace_slug, project_id=project_id, page_id=page.id
                    )
                else:
                    detail = client.pages.retrieve_workspace_page(workspace_slug=workspace_slug, page_id=page.id)
                match = match_page_content(detail, query, project_id)
                if match:
                    matches.append(match)
        return matches[:max_results]

    @mcp.tool()
    def create_page(
        name: str,
        description_html: str,
        project_id: str | None = None,
        access: int | None = None,
        color: str | None = None,
        is_locked: bool | None = None,
        archived_at: str | None = None,
        view_props: dict[str, Any] | None = None,
        logo_props: dict[str, Any] | None = None,
        external_id: str | None = None,
        external_source: str | None = None,
    ) -> Page:
        """
        Create a page.

        Creates a project page if project_id is given, otherwise a
        workspace-level page.

        Args:
            name: Page name
            description_html: Page content in HTML format
            project_id: UUID of the project. Omit to create a workspace page.
            access: Access level for the page (integer)
            color: Page color
            is_locked: Whether the page is locked
            archived_at: Archive timestamp (ISO 8601 format)
            view_props: View properties dictionary
            logo_props: Logo properties dictionary
            external_id: External system identifier
            external_source: External system source name

        Returns:
            Created Page object
        """
        client, workspace_slug = get_plane_client_context()

        data = CreatePage(
            name=name,
            description_html=description_html,
            access=access,
            color=color,
            is_locked=is_locked,
            archived_at=archived_at,
            view_props=view_props,
            logo_props=logo_props,
            external_id=external_id,
            external_source=external_source,
        )

        if project_id is not None:
            return client.pages.create_project_page(
                workspace_slug=workspace_slug,
                project_id=project_id,
                data=data,
            )
        return client.pages.create_workspace_page(
            workspace_slug=workspace_slug,
            data=data,
        )
