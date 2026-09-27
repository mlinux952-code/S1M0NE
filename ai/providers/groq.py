"""ai/providers/groq.py — Fournisseur Groq (Phase 6).

Recommandé par défaut : API compatible OpenAI, aucune carte bancaire requise pour créer un
compte. Catalogue de modèles vérifié en direct sur https://console.groq.com/docs/models
(dernière vérification : septembre 2026) — Groq a fait passer ses modèles Llama (3.1 8B,
3.3 70B) en accès "Enterprise" (contact commercial), ils NE sont plus utilisables avec une simple
clé développeur gratuite. Modèle par défaut retenu ici : openai/gpt-oss-20b (modèle "Production",
accessible avec une clé standard, très rapide ~1000 tok/s). Comme pour OpenRouter, ce catalogue
peut encore changer : configurable sans toucher au code via config.toml [ai.groq] model = "...".
Clé gratuite : https://console.groq.com/keys
"""

from __future__ import annotations

import httpx

from ai.base import AIProvider, ChatMessage, ProviderError
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai.groq")

API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(AIProvider):
    name = "groq"
    description = (
        "Groq (console.groq.com) — Llama/Qwen/Gemma hébergés, gratuit sans carte bancaire, "
        "réponses très rapides. Quota : ~30 req/min, jusqu'à 500k tokens/jour selon le modèle."
    )
    default_model = "openai/gpt-oss-20b"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        # `client` injectable pour les tests (httpx.MockTransport) sans appel réseau réel,
        # même pattern que les connecteurs de recherche (Phase 5).
        self._client = client

    def is_configured(self) -> bool:
        return bool(settings.get_secret("GROQ_API_KEY"))

    def setup_hint(self) -> str:
        return (
            "Fournisseur 'groq' non configuré. Crée un compte gratuit (sans carte bancaire) sur "
            "https://console.groq.com/keys, puis ajoute dans ton fichier .env (jamais transmis à "
            "l'agent) : GROQ_API_KEY=ta_clé"
        )

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        api_key = settings.get_secret("GROQ_API_KEY")
        if not api_key:
            raise ProviderError(self.setup_hint())

        payload = {
            "model": model or self.default_model,
            "messages": [m.as_dict() for m in messages],
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            try:
                response = await client.post(API_URL, json=payload, headers=headers)
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.RequestError as exc:
            raise ProviderError(f"Groq injoignable ({exc}). Vérifie ta connexion réseau.") from exc

        if response.status_code == 401:
            raise ProviderError(
                "Clé Groq refusée (401). Vérifie GROQ_API_KEY dans ton .env "
                "(régénère-la sur https://console.groq.com/keys si besoin)."
            )
        if response.status_code == 429:
            raise ProviderError(
                "Quota gratuit Groq dépassé pour l'instant (429). Réessaie dans quelques minutes, "
                "ou change de modèle/fournisseur (voir 's1mone chat --list-providers')."
            )
        if response.status_code == 404:
            raise ProviderError(
                f"Modèle Groq '{model or self.default_model}' introuvable ou réservé aux comptes "
                "Enterprise (404). Le catalogue Groq change régulièrement : vérifie la liste à "
                "jour sur https://console.groq.com/docs/models et ajuste [ai.groq] model dans "
                "config.toml (ou --model sur la ligne de commande)."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Groq a renvoyé une erreur {response.status_code} : {response.text[:300]}")

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise ProviderError(f"Réponse Groq inattendue (format inconnu) : {data!r}") from exc
