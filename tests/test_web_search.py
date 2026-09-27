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
