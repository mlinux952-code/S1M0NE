"""connectors/pypi.py — Connecteur PyPI, Phase 5 (D9, connecteur n°5, MODE DÉGRADÉ TRANSPARENT).

PyPI n'expose plus d'API de recherche officielle (l'ancienne recherche XML-RPC est
dépréciée/désactivée côté serveur — vérifié via pip.pypa.io / discuss.python.org, voir
External Sources de la session). La seule option fiable qui reste est un lookup **par nom exact**
via `https://pypi.org/pypi/<nom>/json`.

Conséquence assumée et documentée (règle anti-hallucination du méga-prompt, §10/§25) : ce
connecteur ne fait PAS de recherche floue. Si `query` correspond exactement à un nom de paquet
existant, on retourne cette unique fiche. Sinon (paquet inexistant, ou l'utilisateur cherchait
un mot-clé plutôt qu'un nom exact), on retourne une liste vide — jamais une liste de résultats
inventés ou approximatifs. `description` du connecteur rend cette limite explicite pour l'UI.
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

PYPI_PROJECT_URL = "https://pypi.org/pypi/{name}/json"


class PyPiConnector(Connector):
    name = "pypi"
    description = (
        "Paquets Python (pypi.org) — MODE DÉGRADÉ : PyPI ne propose plus de recherche floue "
        "officielle, seule une correspondance par nom exact est possible."
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

        url = PYPI_PROJECT_URL.format(name=candidate)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(url)
            if response.status_code == 404:
                # Pas une erreur : simplement aucun paquet ne correspond exactement à ce nom.
                # Ne jamais inventer un résultat approché.
                return []
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        info = data.get("info") or {}
        name = info.get("name")
        if not name:
            return []  # réponse mal formée : on ignore plutôt que d'inventer

        return [
            SearchResult(
                source=self.name,
                name=name,
                description=info.get("summary") or "",
                url=info.get("project_url") or f"https://pypi.org/project/{name}/",
                extra={
                    "version": info.get("version"),
                    "author": info.get("author") or info.get("author_email"),
                    "exact_match_only": True,  # rappel explicite du mode dégradé sur ce résultat
                },
            )
        ]
