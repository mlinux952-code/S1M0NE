"""connectors/huggingface.py — Connecteur Hugging Face Hub, Phase 5 (D9, connecteur n°2).

API publique, sans clé (endpoint `https://huggingface.co/api/models`), vérifié en direct contre
le vrai service avant d'écrire ce fichier (règle du projet : toujours vérifier réellement plutôt
que supposer). Recherche les *modèles* du Hub (pas les datasets/spaces pour l'instant — un
connecteur séparé pourrait être ajouté plus tard si besoin, même principe d'API).
"""

from __future__ import annotations

import httpx

from connectors.base import Connector, SearchResult

HF_MODELS_URL = "https://huggingface.co/api/models"


class HuggingFaceConnector(Connector):
    name = "huggingface"
    description = "Modèles IA (huggingface.co, recherche publique sans clé)."

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 8.0) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel.
        self._client = client
        self._timeout = timeout

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        limit = max(1, min(limit, 100))  # l'API accepte jusqu'à 100
        params = {"search": query, "limit": limit}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(HF_MODELS_URL, params=params)
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        results: list[SearchResult] = []
        for entry in data:
            model_id = entry.get("id") or entry.get("modelId")
            if not model_id:
                continue  # jamais inventer un identifiant : on ignore une entrée mal formée
            results.append(
                SearchResult(
                    source=self.name,
                    name=model_id,
                    description=entry.get("pipeline_tag") or "",
                    url=f"https://huggingface.co/{model_id}",
                    extra={
                        "downloads": entry.get("downloads"),
                        "likes": entry.get("likes"),
                        "library_name": entry.get("library_name"),
                        "tags": entry.get("tags") or [],
                    },
                )
            )
        return results
