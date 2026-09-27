"""ai/providers/openrouter.py — Fournisseur OpenRouter (Phase 6).

API compatible OpenAI, aucune carte bancaire requise pour le tier gratuit de base (20 req/min,
50 req/jour ; passe à 1000 req/jour après un achat ponctuel facultatif de 10$ de crédit — jamais
requis). Catalogue de modèles ":free" qui change régulièrement : le modèle par défaut ci-dessous
est vérifié au moment de l'écriture, mais peut être remplacé à tout moment sans toucher au code
(voir config.toml, section [ai.openrouter]) — liste à jour : https://openrouter.ai/models?max_price=0
Clé gratuite : https://openrouter.ai/keys
"""

from __future__ import annotations

import httpx

from ai.base import AIProvider, ChatMessage, ProviderError
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(AIProvider):
    name = "openrouter"
    description = (
        "OpenRouter (openrouter.ai) — passerelle vers de nombreux modèles, dont une sélection "
        "':free' à 0$/token, gratuit sans carte bancaire. Quota de base : 20 req/min, 50 req/jour."
    )
    default_model = "openai/gpt-oss-20b:free"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def is_configured(self) -> bool:
        return bool(settings.get_secret("OPENROUTER_API_KEY"))

    def setup_hint(self) -> str:
        return (
            "Fournisseur 'openrouter' non configuré. Crée un compte gratuit (sans carte bancaire) "
            "sur https://openrouter.ai/keys, puis ajoute dans ton fichier .env (jamais transmis à "
            "l'agent) : OPENROUTER_API_KEY=ta_clé"
        )

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        api_key = settings.get_secret("OPENROUTER_API_KEY")
        if not api_key:
            raise ProviderError(self.setup_hint())

        payload = {
            "model": model or self.default_model,
            "messages": [m.as_dict() for m in messages],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/mlinux952-code/S1M0NE",
            "X-Title": "S1M0NE",
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            try:
                response = await client.post(API_URL, json=payload, headers=headers)
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.RequestError as exc:
            raise ProviderError(f"OpenRouter injoignable ({exc}). Vérifie ta connexion réseau.") from exc

        if response.status_code == 401:
            raise ProviderError(
                "Clé OpenRouter refusée (401). Vérifie OPENROUTER_API_KEY dans ton .env."
            )
        if response.status_code == 429:
            raise ProviderError(
                "Quota gratuit OpenRouter dépassé (429). Réessaie plus tard, ou change de "
                "fournisseur (voir 's1mone chat --list-providers')."
            )
        if response.status_code == 404 or response.status_code == 400:
            raise ProviderError(
                f"Modèle OpenRouter '{model or self.default_model}' refusé ({response.status_code}). "
                "Le catalogue ':free' change régulièrement : vérifie la liste à jour sur "
                "https://openrouter.ai/models?max_price=0 et ajuste [ai.openrouter] model dans "
                "config.toml."
            )
        if response.status_code >= 400:
            raise ProviderError(
                f"OpenRouter a renvoyé une erreur {response.status_code} : {response.text[:300]}"
            )

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise ProviderError(f"Réponse OpenRouter inattendue (format inconnu) : {data!r}") from exc
