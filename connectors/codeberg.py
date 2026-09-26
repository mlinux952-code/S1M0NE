"""connectors/codeberg.py — Connecteur Codeberg (Forgejo), Phase 5 (D9, connecteur n°4b).

API publique Codeberg.org (compatible Gitea/Forgejo), sans clé requise pour rechercher des
dépôts publics (vérifié en direct : quota généreux ~200 req/heure en anonyme, largement
suffisant avec le Cache Manager).
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

CODEBERG_SEARCH_URL = "https://codeberg.org/api/v1/repos/search"


class CodebergConnector(Connector):
    name = "codeberg"
    description = "Dépôts de code (codeberg.org, Forgejo, recherche publique sans clé)."

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        limit = max(1, min(limit, 50))
        params = {"q": query, "limit": limit}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(CODEBERG_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        results: list[SearchResult] = []
        for item in data.get("data", []):
            full_name = item.get("full_name")
            if not full_name:
                continue  # jamais inventer un nom : on ignore une entrée mal formée
            results.append(
                SearchResult(
                    source=self.name,
                    name=full_name,
                    description=item.get("description") or "",
                    url=item.get("html_url") or "",
                    extra={
                        "stars": item.get("stars_count"),
                        "forks": item.get("forks_count"),
                        "language": item.get("language"),
                    },
                )
            )
        return results
