"""Unit tests for pages tool helpers (truncation E12.3 + search E12.4)."""

from plane.models.pages import Page

from plane_mcp.tools.pages import (
    match_page_content,
    match_pages_by_name,
    truncate_page_content,
)


def make_page(**kw) -> Page:
    defaults = {"id": "11111111-1111-1111-1111-111111111111", "name": "Notes"}
    defaults.update(kw)
    return Page.model_validate(defaults)


# --- truncate_page_content ------------------------------------------------------


def test_no_truncation_returns_page_unchanged(monkeypatch):
    monkeypatch.delenv("PLANE_PAGES_MAX_CONTENT_LENGTH", raising=False)
    page = make_page(description_html="<p>short</p>")
    assert truncate_page_content(page, None) is page


def test_truncation_flags_and_cuts_content():
    page = make_page(description_html="x" * 100, description_stripped="y" * 100)
    result = truncate_page_content(page, 10)
    assert isinstance(result, dict)
    assert result["description_html"] == "x" * 10
    assert result["description_stripped"] == "y" * 10
    assert result["content_truncated"] is True
    assert result["total_content_length"] == 100


def test_truncation_env_default(monkeypatch):
    monkeypatch.setenv("PLANE_PAGES_MAX_CONTENT_LENGTH", "5")
    page = make_page(description_html="0123456789")
    result = truncate_page_content(page, None)
    assert result["description_html"] == "01234"
    # explicit param beats the env default
    page2 = make_page(description_html="0123456789")
    assert truncate_page_content(page2, 100) is page2


def test_truncation_env_invalid_or_zero_means_unlimited(monkeypatch):
    for raw in ("", "abc", "0", "-5"):
        monkeypatch.setenv("PLANE_PAGES_MAX_CONTENT_LENGTH", raw)
        page = make_page(description_html="0123456789")
        assert truncate_page_content(page, None) is page


# --- search helpers -------------------------------------------------------------


def test_match_pages_by_name_case_insensitive():
    pages = [make_page(name="Deploy Notes"), make_page(name="Roadmap"), make_page(name=None)]
    matches = match_pages_by_name(pages, "notes", "p1")
    assert len(matches) == 1
    assert matches[0]["name"] == "Deploy Notes"
    assert matches[0]["match_field"] == "name"
    assert matches[0]["project_id"] == "p1"


def test_match_page_content_uses_stripped_or_html():
    hit = make_page(description_stripped="alpha beta gamma")
    assert match_page_content(hit, "BETA", None)["match_field"] == "content"
    html_only = make_page(description_html="<p>hello <b>world</b></p>", description_stripped=None)
    match = match_page_content(html_only, "world", None)
    assert match and "world" in match["snippet"]
    miss = make_page(description_stripped="nothing here")
    assert match_page_content(miss, "absent", None) is None


def test_match_page_content_snippet_window():
    text = "a" * 500 + " NEEDLE " + "b" * 500
    page = make_page(description_stripped=text)
    snippet = match_page_content(page, "needle", None)["snippet"]
    assert "NEEDLE" in snippet
    assert len(snippet) < 250
