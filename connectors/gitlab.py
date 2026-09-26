"""connectors/gitlab.py — Connecteur GitLab (dépôts), Phase 5 (D9, connecteur n°4a).

API publique GitLab.com, sans clé requise pour rechercher des projets publics (vérifié en
direct : 500 req/min en anonyme — bien plus généreux que GitHub, aucun token nécessaire).
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

GITLAB_PROJECTS_URL = "https://gitlab.com/api/v4/projects"


class GitLabConnector(Connector):
    name = "gitlab"
    description = "Dépôts de code (gitlab.com, recherche publique sans clé, 500 req/min)."

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        limit = max(1, min(limit, 100))  # l'API GitLab plafonne per_page à 100
        params = {
            "search": query,
            "per_page": limit,
            "order_by": "star_count",
            "sort": "desc",
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(GITLAB_PROJECTS_URL, params=params)
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        results: list[SearchResult] = []
        for item in data:
            path = item.get("path_with_namespace")
            if not path:
                continue  # jamais inventer un nom : on ignore une entrée mal formée
            results.append(
                SearchResult(
                    source=self.name,
                    name=path,
                    description=item.get("description") or "",
                    url=item.get("web_url") or "",
                    extra={
                        "stars": item.get("star_count"),
                        "forks": item.get("forks_count"),
                    },
                )
            )
        return results
