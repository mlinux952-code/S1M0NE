"""ai/providers/ollama.py — Fournisseur local Ollama (Phase 6).

Aucune clé, aucun réseau externe : tourne entièrement sur la machine. Honnêteté requise (mega-
prompt anti-hallucination + SYSTEM_PROFILE.md) : la machine cible (~4 Gio RAM, dual-core) est
modeste. Un petit modèle (1B-3B, quantifié) peut fonctionner mais restera lent (souvent quelques
tokens/seconde). Ce n'est pas fait pour un usage confortable au quotidien, plutôt pour tester le
fonctionnement hors-ligne/privé. Le modèle par défaut ci-dessous (llama3.2:1b) est le plus petit
modèle généraliste raisonnable disponible sur Ollama au moment de l'écriture.
"""

from __future__ import annotations

import httpx

from ai.base import AIProvider, ChatMessage, ProviderError
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai.ollama")

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider(AIProvider):
    name = "ollama"
    description = (
        "Ollama (local, sans clé, sans internet) — 100% privé, mais lent sur une machine modeste "
        "(~4 Gio RAM) : à réserver aux tests, modèle recommandé le plus léger possible (1B)."
    )
    default_model = "llama3.2:1b"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    def _base_url(self) -> str:
        return settings.get_secret("OLLAMA_BASE_URL") or DEFAULT_BASE_URL

    def is_configured(self) -> bool:
        # Pas de clé à vérifier : "configuré" signifie juste "on va essayer de le joindre".
        # La vraie vérification (service up ou non) se fait à l'appel, pour ne jamais bloquer
        # ni faire un appel réseau depuis un simple affichage de statut.
        return True

    def setup_hint(self) -> str:
        return (
            "Fournisseur 'ollama' : installe Ollama (https://ollama.com), lance-le "
            f"('ollama serve' si besoin), puis télécharge un petit modèle : "
            f"'ollama pull {self.default_model}'. Attention : sur une machine modeste (~4 Gio "
            "RAM), même un modèle 1B reste lent — à réserver aux tests."
        )

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        url = f"{self._base_url()}/api/chat"
        payload = {
            "model": model or self.default_model,
            "messages": [m.as_dict() for m in messages],
            "stream": False,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=120.0)
        try:
            try:
                response = await client.post(url, json=payload)
            finally:
                if owns_client:
                    await client.aclose()
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Ollama injoignable sur {self._base_url()} ({exc}). {self.setup_hint()}"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(f"Ollama injoignable ({exc}).") from exc

        if response.status_code == 404:
            raise ProviderError(
                f"Modèle Ollama '{model or self.default_model}' absent. "
                f"Télécharge-le : 'ollama pull {model or self.default_model}'."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Ollama a renvoyé une erreur {response.status_code} : {response.text[:300]}")

        data = response.json()
        try:
            return data["message"]["content"].strip()
        except (KeyError, AttributeError) as exc:
            raise ProviderError(f"Réponse Ollama inattendue (format inconnu) : {data!r}") from exc
