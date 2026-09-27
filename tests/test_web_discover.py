"""Tests de la page web /discover (Catégorie G : catalogue statique de découverte)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


def test_discover_page_loads():
    r = client.get("/discover")
    assert r.status_code == 200
    assert "Découverte" in r.text
    assert "100" in r.text


def test_discover_nav_link_is_present():
    r = client.get("/")
    assert '<a href="/discover">Découverte</a>' in r.text


def test_partial_discover_without_filter_lists_everything():
    r = client.get("/partials/discover")
    assert r.status_code == 200
    assert r.text.count("<tr>") == 101  # 100 lignes + la ligne d'en-tête


def test_partial_discover_filters_by_site():
    r = client.get("/partials/discover", params={"site": "gitlab"})
    assert r.status_code == 200
    assert "gitlab-org" in r.text or "gitlab" in r.text.lower()


def test_partial_discover_search_by_query():
    r = client.get("/partials/discover", params={"q": "second brain"})
    assert r.status_code == 200
    assert "khoj" in r.text
    assert "treetime" in r.text


def test_partial_discover_no_match_shows_message():
    r = client.get("/partials/discover", params={"q": "zzzz-improbable-zzzz"})
    assert r.status_code == 200
    assert "Aucun résultat" in r.text


def test_discover_links_open_in_new_tab_safely():
    r = client.get("/partials/discover")
    assert 'target="_blank"' in r.text
    assert 'rel="noopener noreferrer"' in r.text
