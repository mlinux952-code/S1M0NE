"""Tests de core/discover.py (Catégorie G : catalogue statique de découverte)."""

from __future__ import annotations

from core.discover import available_sites, catalog_metadata, list_entries, search_catalog


def test_catalog_has_exactly_100_entries():
    assert catalog_metadata()["total"] == 100
    assert len(list_entries()) == 100


def test_catalog_has_a_compiled_on_date():
    meta = catalog_metadata()
    assert meta["compiled_on"]
    assert "hors-ligne" in meta["note"] or "jamais" in meta["note"]


def test_available_sites_matches_the_seven_s1mone_connectors():
    assert available_sites() == [
        "codeberg",
        "github",
        "gitlab",
        "huggingface",
        "npm",
        "pypi",
        "sourceforge",
    ]


def test_list_entries_filters_by_site():
    npm_entries = list_entries(site="npm")
    assert len(npm_entries) > 0
    assert all(e["site"] == "npm" for e in npm_entries)


def test_list_entries_site_filter_is_case_insensitive():
    assert list_entries(site="NPM") == list_entries(site="npm")


def test_list_entries_filters_by_category():
    entries = list_entries(category="CLI")
    assert len(entries) > 0
    assert all(e["category"].lower() == "cli" for e in entries)


def test_every_entry_has_required_fields_and_a_real_looking_url():
    for e in list_entries():
        assert e["name"]
        assert e["site"]
        assert e["category"]
        assert e["description"]
        assert e["url"].startswith("https://")


def test_search_catalog_finds_by_name():
    results = search_catalog("lodash")
    assert any(e["name"] == "lodash" for e in results)


def test_search_catalog_finds_by_description_keyword():
    results = search_catalog("auto-hébergeable")
    assert len(results) > 0


def test_search_catalog_empty_query_returns_empty_list():
    assert search_catalog("   ") == []


def test_search_catalog_no_match_returns_empty_list():
    assert search_catalog("zzzz-mot-improbable-zzzz") == []


def test_search_catalog_respects_limit():
    results = search_catalog("e", limit=5)  # "e" matche presque tout
    assert len(results) <= 5
