"""connectors/sourceforge.py — Connecteur SourceForge, Phase 5 (D9, connecteur n°6, DÉGRADÉ).

SourceForge n'a pas d'API de recherche par mot-clé (vérifié en direct : /rest/search/... n'existe
pas, la recherche HTML classique répond 403 aux requêtes automatisées). La seule option fiable est
un lookup **par nom exact** via `https://sourceforge.net/rest/p/<shortname>` — même principe et
mêmes garanties que le connecteur PyPI (connectors/pypi.py).

Décision D9 mise à jour cette session : Bitbucket et Gitee ont été RETIRÉS du plan (vérifiés en
direct, sans solution viable — voir DECISIONS.md). SourceForge est le seul des trois à offrir un
minimum de valeur réelle, en mode dégradé transparent.
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

SOURCEFORGE_PROJECT_URL = "https://sourceforge.net/rest/p/{shortname}"


class SourceForgeConnector(Connector):
    name = "sourceforge"
    description = (
        "Projets open source (sourceforge.net) — MODE DÉGRADÉ : pas de recherche par mot-clé "
        "disponible, seule une correspondance par nom exact est possible."
    )

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        # `limit` n'a pas de sens ici (un seul résultat possible au mieux), gardé pour respecter
        # l'interface Connector commune.
        candidate = query.strip()
        if not candidate:
            return []

        url = SOURCEFORGE_PROJECT_URL.format(shortname=candidate)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(url)
            if response.status_code == 404:
                # Pas une erreur : aucun projet ne correspond exactement à ce nom.
                # Ne jamais inventer un résultat approché.
                return []
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        shortname = data.get("shortname")
        if not shortname:
            return []  # réponse mal formée : on ignore plutôt que d'inventer

        return [
            SearchResult(
                source=self.name,
                name=data.get("name") or shortname,
                description=data.get("summary") or data.get("short_description") or "",
                url=data.get("url") or f"https://sourceforge.net/projects/{shortname}/",
                extra={
                    "shortname": shortname,
                    "status": data.get("status"),
                    "exact_match_only": True,  # rappel explicite du mode dégradé sur ce résultat
                },
            )
        ]
