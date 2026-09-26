"""Tests des connecteurs de recherche (Phase 5, étape 1 : npm + moteur d'orchestration)."""

from __future__ import annotations

import asyncio

import httpx

from connectors.base import Connector, SearchResult
from connectors.engine import available_connectors, search_all
from connectors.npm import NpmConnector

NPM_SAMPLE_RESPONSE = {
    "objects": [
        {
            "package": {
                "name": "react",
                "description": "React is a JavaScript library for building user interfaces.",
                "version": "18.3.1",
                "links": {"npm": "https://www.npmjs.com/package/react"},
                "publisher": {"username": "gnoff"},
            },
            "score": {"final": 0.99},
        },
        {
            "package": {
                # entrée volontairement mal formée (pas de nom) : doit être ignorée, jamais inventée
                "description": "paquet cassé",
            },
        },
    ],
    "total": 2,
}


def _mock_npm_client(payload: dict, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_npm_connector_parses_results_and_skips_malformed_entries():
    async def scenario():
        client = _mock_npm_client(NPM_SAMPLE_RESPONSE)
        connector = NpmConnector(client=client)
        try:
            return await connector.search("react", limit=5)
        finally:
            await client.aclose()

    results = asyncio.run(scenario())

    assert len(results) == 1  # l'entrée sans nom a bien été ignorée, pas inventée
    assert results[0].source == "npm"
    assert results[0].name == "react"
    assert results[0].extra["version"] == "18.3.1"


def test_npm_connector_raises_on_http_error():
    async def scenario():
        client = _mock_npm_client({}, status_code=503)
        connector = NpmConnector(client=client)
        try:
            await connector.search("react")
        finally:
            await client.aclose()

    try:
        asyncio.run(scenario())
        raised = False
    except httpx.HTTPStatusError:
        raised = True
    assert raised


class _FailingConnector(Connector):
    name = "broken"
    description = "Connecteur factice qui échoue toujours (pour tester l'isolation des pannes)."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise RuntimeError("panne simulée")


class _WorkingConnector(Connector):
    name = "fake"
    description = "Connecteur factice qui retourne toujours un résultat fixe."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return [SearchResult(source=self.name, name=f"résultat pour {query}")]


def test_search_all_isolates_a_failing_connector(monkeypatch):
    import connectors.engine as engine_module

    monkeypatch.setattr(
        engine_module, "_CONNECTORS", {"broken": _FailingConnector(), "fake": _WorkingConnector()}
    )

    outcome = asyncio.run(engine_module.search_all("test"))

    assert outcome["errors"] == {"broken": "panne simulée"}
    assert len(outcome["results"]) == 1
    assert outcome["results"][0]["source"] == "fake"


def test_search_all_empty_query_returns_nothing_without_calling_connectors():
    outcome = asyncio.run(search_all("   "))
    assert outcome == {"results": [], "errors": {}}


def test_available_connectors_lists_npm():
    names = [c["name"] for c in available_connectors()]
    assert "npm" in names


def test_npm_connector_real_network_smoke_test():
    """Test réel (pas de mock) contre la vraie API npm : vérifie que le pipeline complet
    fonctionne pour de vrai, pas seulement avec des données simulées (règle du projet : toujours
    vérifier réellement plutôt que supposer)."""
    connector = NpmConnector()
    results = asyncio.run(connector.search("react", limit=5))
    assert len(results) > 0
    assert any("react" in r.name.lower() for r in results)
    assert all(r.source == "npm" for r in results)
