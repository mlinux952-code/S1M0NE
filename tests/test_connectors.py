"""Tests des connecteurs de recherche (Phase 5, étape 1 : npm + moteur d'orchestration)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from connectors.base import Connector, SearchResult
from connectors.engine import available_connectors, search_all
from connectors.github import GitHubConnector
from connectors.huggingface import HuggingFaceConnector
from connectors.npm import NpmConnector


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isole la base SQLite (donc le cache, Phase 4) pour ne pas polluer les données réelles
    du projet ni faire dépendre un test du résultat d'un précédent (cache partagé)."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield

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


HF_SAMPLE_RESPONSE = [
    {
        "id": "google-bert/bert-base-uncased",
        "downloads": 43907375,
        "likes": 3376,
        "pipeline_tag": "fill-mask",
        "library_name": "transformers",
        "tags": ["transformers", "pytorch", "bert"],
    },
    {
        # entrée volontairement mal formée (pas d'id/modelId) : doit être ignorée, jamais inventée
        "downloads": 0,
        "likes": 0,
    },
]


def _mock_hf_client(payload, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_huggingface_connector_parses_results_and_skips_malformed_entries():
    async def scenario():
        client = _mock_hf_client(HF_SAMPLE_RESPONSE)
        connector = HuggingFaceConnector(client=client)
        try:
            return await connector.search("bert", limit=5)
        finally:
            await client.aclose()

    results = asyncio.run(scenario())

    assert len(results) == 1  # l'entrée sans id a bien été ignorée, pas inventée
    assert results[0].source == "huggingface"
    assert results[0].name == "google-bert/bert-base-uncased"
    assert results[0].url == "https://huggingface.co/google-bert/bert-base-uncased"
    assert results[0].extra["downloads"] == 43907375


def test_huggingface_connector_raises_on_http_error():
    async def scenario():
        client = _mock_hf_client([], status_code=503)
        connector = HuggingFaceConnector(client=client)
        try:
            await connector.search("bert")
        finally:
            await client.aclose()

    try:
        asyncio.run(scenario())
        raised = False
    except httpx.HTTPStatusError:
        raised = True
    assert raised


def test_huggingface_connector_real_network_smoke_test():
    """Test réel (pas de mock) contre la vraie API Hugging Face Hub : vérifie que le pipeline
    complet fonctionne pour de vrai (règle du projet : toujours vérifier réellement plutôt que
    supposer)."""
    connector = HuggingFaceConnector()
    results = asyncio.run(connector.search("bert", limit=5))
    assert len(results) > 0
    assert any("bert" in r.name.lower() for r in results)
    assert all(r.source == "huggingface" for r in results)


def test_available_connectors_lists_huggingface():
    names = [c["name"] for c in available_connectors()]
    assert "huggingface" in names


GITHUB_SAMPLE_RESPONSE = {
    "total_count": 1,
    "items": [
        {
            "full_name": "facebook/react",
            "description": "The library for web and native user interfaces.",
            "html_url": "https://github.com/facebook/react",
            "stargazers_count": 250000,
            "forks_count": 51000,
            "language": "JavaScript",
            "owner": {"login": "facebook"},
        },
        {
            # entrée volontairement mal formée (pas de full_name) : doit être ignorée
            "description": "dépôt cassé",
        },
    ],
}


def _mock_github_client(payload, status_code: int = 200, captured_headers: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured_headers is not None:
            captured_headers.update(dict(request.headers))
        return httpx.Response(status_code, json=payload)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_github_connector_parses_results_and_skips_malformed_entries():
    async def scenario():
        client = _mock_github_client(GITHUB_SAMPLE_RESPONSE)
        connector = GitHubConnector(client=client)
        try:
            return await connector.search("react", limit=5)
        finally:
            await client.aclose()

    results = asyncio.run(scenario())

    assert len(results) == 1  # l'entrée sans full_name a bien été ignorée, pas inventée
    assert results[0].source == "github"
    assert results[0].name == "facebook/react"
    assert results[0].extra["stars"] == 250000
    assert results[0].extra["owner"] == "facebook"


def test_github_connector_raises_on_http_error():
    async def scenario():
        client = _mock_github_client({}, status_code=503)
        connector = GitHubConnector(client=client)
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


def test_github_connector_sends_token_when_configured(monkeypatch):
    import connectors.github as github_module

    monkeypatch.setattr(github_module.settings, "get_secret", lambda name, default=None: "fake-token-123")

    captured: dict = {}

    async def scenario():
        client = _mock_github_client(GITHUB_SAMPLE_RESPONSE, captured_headers=captured)
        connector = GitHubConnector(client=client)
        try:
            return await connector.search("react")
        finally:
            await client.aclose()

    asyncio.run(scenario())
    assert captured.get("authorization") == "Bearer fake-token-123"


def test_github_connector_works_without_token(monkeypatch):
    import connectors.github as github_module

    monkeypatch.setattr(github_module.settings, "get_secret", lambda name, default=None: None)

    captured: dict = {}

    async def scenario():
        client = _mock_github_client(GITHUB_SAMPLE_RESPONSE, captured_headers=captured)
        connector = GitHubConnector(client=client)
        try:
            return await connector.search("react")
        finally:
            await client.aclose()

    results = asyncio.run(scenario())
    assert "authorization" not in captured
    assert len(results) == 1


def test_github_connector_real_network_smoke_test():
    """Test réel (pas de mock) contre la vraie API GitHub : vérifie que le pipeline complet
    fonctionne pour de vrai (règle du projet : toujours vérifier réellement plutôt que
    supposer). Volontairement un seul test réseau réel pour ce connecteur (quota le plus
    contraint des trois : 10 req/min sans token)."""
    connector = GitHubConnector()
    results = asyncio.run(connector.search("react", limit=5))
    assert len(results) > 0
    assert any("react" in r.name.lower() for r in results)
    assert all(r.source == "github" for r in results)


def test_available_connectors_lists_github():
    names = [c["name"] for c in available_connectors()]
    assert "github" in names


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
    assert outcome == {"results": [], "errors": {}, "cache_hits": []}


def test_search_all_second_identical_call_hits_cache(monkeypatch):
    import connectors.engine as engine_module

    call_count = {"n": 0}

    class _CountingConnector(Connector):
        name = "counted"
        description = "compte le nombre de fois où search() est vraiment appelé"

        async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
            call_count["n"] += 1
            return [SearchResult(source=self.name, name="résultat unique")]

    monkeypatch.setattr(engine_module, "_CONNECTORS", {"counted": _CountingConnector()})

    first = asyncio.run(engine_module.search_all("même-requete"))
    second = asyncio.run(engine_module.search_all("même-requete"))

    assert call_count["n"] == 1  # le 2e appel est servi par le cache, pas par le connecteur
    assert first["cache_hits"] == []
    assert second["cache_hits"] == ["counted"]
    assert first["results"] == second["results"]


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
