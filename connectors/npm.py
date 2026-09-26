"""connectors/npm.py — Connecteur npm (registry.npmjs.org), Phase 5 (D9, connecteur n°1).

Choisi en premier car : API publique, sans clé, sans quota bloquant documenté (voir RESEARCH.md /
External Sources de la session) — le plus simple pour valider tout le pipeline de bout en bout
avant d'attaquer des connecteurs plus contraints (GitHub : 30 req/min, PyPI : pas de recherche
floue officielle).
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"


class NpmConnector(Connector):
    name = "npm"
    description = "Paquets JavaScript/Node.js (registry.npmjs.org, recherche publique sans clé)."

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        limit = max(1, min(limit, 50))  # l'API npm plafonne raisonnablement, on reste prudent
        params = {"text": query, "size": limit}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(NPM_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        results: list[SearchResult] = []
        for obj in data.get("objects", []):
            pkg = obj.get("package", {})
            name = pkg.get("name")
            if not name:
                continue  # jamais inventer un nom : on ignore une entrée mal formée
            links = pkg.get("links", {})
            results.append(
                SearchResult(
                    source=self.name,
                    name=name,
                    description=pkg.get("description") or "",
                    url=links.get("npm") or links.get("homepage") or "",
                    extra={
                        "version": pkg.get("version"),
                        "publisher": (pkg.get("publisher") or {}).get("username"),
                        "score_final": (obj.get("score") or {}).get("final"),
                    },
                )
            )
        return results
