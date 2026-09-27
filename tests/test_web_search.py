"""Tests du Web Gateway - endpoints de recherche (Phase 5 -> intégration web)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app_module
from web.app import app

client = TestClient(app)


async def _fake_search_all(query, limit_per_source=10, sources=None):
    if not query.strip():
        return {"results": [], "errors": {}, "cache_hits": []}
    return {
        "results": [
            {
                "source": "npm",
                "name": "react",
                "description": "UI library",
                "url": "https://npmjs.com/package/react",
                "extra": {},
            }
        ],
        "errors": {},
        "cache_hits": ["npm"],
    }


def test_search_page_loads_and_lists_sources():
    r = client.get("/search")
    assert r.status_code == 200
    assert "npm" in r.text
    assert "sourceforge" in r.text


def test_api_search_sources_lists_seven_connectors():
    r = client.get("/api/search/sources")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["sources"]]
    assert set(names) == {
        "npm", "huggingface", "github", "gitlab", "codeberg", "pypi", "sourceforge",
    }


def test_api_search_returns_results(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all)
    r = client.get("/api/search", params={"q": "react"})
    assert r.status_code == 200
    body = r.json()
    assert body["results"][0]["source"] == "npm"
    assert body["cache_hits"] == ["npm"]


def test_partial_search_results_renders_html(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all)
    r = client.get("/partials/search-results", params={"q": "react"})
    assert r.status_code == 200
    assert "react" in r.text


def test_partial_search_results_empty_query_does_not_call_connectors(monkeypatch):
    called = {"n": 0}

    async def spy(*args, **kwargs):
        called["n"] += 1
        return {"results": [], "errors": {}, "cache_hits": []}

    monkeypatch.setattr(web_app_module, "search_all", spy)
    r = client.get("/partials/search-results", params={"q": "   "})
    assert r.status_code == 200
    assert called["n"] == 0  # la fonction dédiée gère elle-même le cas vide, sans appeler search_all


async def _fake_search_all_multi(query, limit_per_source=10, sources=None):
    return {
        "results": [
            {"source": "github", "name": "b-pkg", "description": "", "url": "", "extra": {"stars": 5}},
            {"source": "github", "name": "a-pkg", "description": "", "url": "", "extra": {"stars": 50}},
            {"source": "npm", "name": "c-pkg", "description": "", "url": "", "extra": {}},
        ],
        "errors": {},
        "cache_hits": [],
    }


def test_api_search_sorts_by_stars(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/api/search", params={"q": "pkg", "sort": "stars"})
    assert r.status_code == 200
    names = [item["name"] for item in r.json()["results"]]
    assert names == ["a-pkg", "b-pkg", "c-pkg"]


def test_api_search_paginates(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/api/search", params={"q": "pkg", "page": 1, "page_size": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 2
    assert body["total"] == 3
    assert body["total_pages"] == 2


def test_api_search_invalid_sort_returns_400(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/api/search", params={"q": "pkg", "sort": "date"})
    assert r.status_code == 400
    assert "invalide" in r.json()["detail"].lower()


def test_partial_search_results_shows_pagination_controls_when_multiple_pages(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/partials/search-results", params={"q": "pkg", "page_size": 2})
    assert r.status_code == 200
    assert "Suivant" in r.text
    assert "Page 1 / 2" in r.text


def test_partial_search_results_no_pagination_controls_on_single_page(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all)
    r = client.get("/partials/search-results", params={"q": "react"})
    assert r.status_code == 200
    assert "Suivant" not in r.text


def test_partial_search_results_second_page_via_htmx_vals(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/partials/search-results", params={"q": "pkg", "page_size": 2, "page": 2})
    assert r.status_code == 200
    assert "c-pkg" in r.text
    assert "Page 2 / 2" in r.text


def test_partial_search_results_invalid_sort_shows_clear_error(monkeypatch):
    monkeypatch.setattr(web_app_module, "search_all", _fake_search_all_multi)
    r = client.get("/partials/search-results", params={"q": "pkg", "sort": "date"})
    assert r.status_code == 200
    assert "invalide" in r.text.lower()
