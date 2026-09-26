"""connectors/github.py — Connecteur GitHub (dépôts), Phase 5 (D9, connecteur n°3).

Le plus contraint des connecteurs : l'API de recherche GitHub limite à 10 req/min en anonyme,
30 req/min avec un token (vérifié en direct sur l'API réelle avant d'écrire ce fichier — règle
du projet : toujours vérifier réellement plutôt que supposer). C'est justement la raison d'être
du Cache Manager (Phase 4), construit spécifiquement en prévision de ce connecteur.

Sécurité / vie privée du token : le token GITHUB_TOKEN (si présent) est lu depuis .env via
`Settings.get_secret` — jamais commité, jamais loggué en clair (voir SENSITIVE_KEY_HINTS dans
core/config.py). Le connecteur fonctionne sans token (mode dégradé mais fonctionnel : 10 req/min
au lieu de 30) — jamais bloquant si l'utilisateur n'en configure pas.
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult
from core.config import settings

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


class GitHubConnector(Connector):
    name = "github"
    description = "Dépôts de code (api.github.com, recherche publique — 10 req/min sans token, 30 avec)."

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            # GitHub rejette les requêtes sans User-Agent identifiable.
            "User-Agent": "S1MONE-search-connector",
        }
        token = settings.get_secret("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        limit = max(1, min(limit, 100))  # l'API GitHub plafonne per_page à 100
        params = {"q": query, "per_page": limit}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(GITHUB_SEARCH_URL, params=params, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        results: list[SearchResult] = []
        for item in data.get("items", []):
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
                        "stars": item.get("stargazers_count"),
                        "forks": item.get("forks_count"),
                        "language": item.get("language"),
                        "owner": (item.get("owner") or {}).get("login"),
                    },
                )
            )
        return results
