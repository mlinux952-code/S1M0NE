"""ai/providers/ollama.py — Fournisseur local Ollama (Phase 6).

Aucune clé, aucun réseau externe : tourne entièrement sur la machine. Honnêteté requise (mega-
prompt anti-hallucination + SYSTEM_PROFILE.md) : la machine cible (~4 Gio RAM, dual-core) est
modeste. Un petit modèle (1B-3B, quantifié) peut fonctionner mais restera lent (souvent quelques
tokens/seconde). Ce n'est pas fait pour un usage confortable au quotidien, plutôt pour tester le
fonctionnement hors-ligne/privé. Le modèle par défaut ci-dessous (llama3.2:1b) est le plus petit
modèle généraliste raisonnable disponible sur Ollama au moment de l'écriture.

NEXT_STEPS.md §B.2 : Ollama expose nativement un champ "tools" sur `/api/chat` (depuis 0.3, bien
avant la rédaction de ce module) au format proche d'OpenAI, avec une différence clé : les
arguments d'un appel d'outil sont transmis en dict JSON natif, jamais en chaîne encodée — d'où
un `_to_ollama_dict()` dédié plutôt que de réutiliser celui de Groq/OpenRouter. Un petit modèle
1B a rarement été entraîné pour appeler des outils de façon fiable : le mode agentique reste
disponible avec Ollama mais sans garantie de résultat utile sur un modèle aussi réduit — c'est un
choix de l'utilisateur, jamais bloqué ici (mega-prompt : dire la vérité, ne jamais décider à sa
place).
"""

from __future__ import annotations

from typing import Any

import httpx

from ai.base import AIProvider, ChatMessage, ProviderError, ToolCall
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai.ollama")

DEFAULT_BASE_URL = "http://localhost:11434"


def _to_ollama_dict(m: ChatMessage) -> dict[str, Any]:
    """Traduit un ChatMessage canonique (ai/base.py) vers le dialecte natif d'Ollama :
    `tool_calls[].function.arguments` reste un dict (pas de chaîne JSON, contrairement à
    OpenAI/Groq/OpenRouter)."""
    d: dict[str, Any] = {"role": m.role, "content": m.content or ""}
    if m.tool_calls:
        d["tool_calls"] = [
            {"function": {"name": tc.name, "arguments": tc.arguments}} for tc in m.tool_calls
        ]
    return d


class OllamaProvider(AIProvider):
    name = "ollama"
    description = (
        "Ollama (local, sans clé, sans internet) — 100% privé, mais lent sur une machine modeste "
        "(~4 Gio RAM) : à réserver aux tests, modèle recommandé le plus léger possible (1B)."
    )
    default_model = "llama3.2:1b"
    supports_tools = True  # NEXT_STEPS §B.2 : "tools" natif sur /api/chat depuis Ollama 0.3+.

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

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url()}/api/chat"
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
                f"Modèle Ollama '{payload.get('model')}' absent. "
                f"Télécharge-le : 'ollama pull {payload.get('model')}'."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Ollama a renvoyé une erreur {response.status_code} : {response.text[:300]}")

        return response.json()

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        payload = {
            "model": model or self.default_model,
            "messages": [m.as_dict() for m in messages],
            "stream": False,
        }
        data = await self._post(payload)
        try:
            return data["message"]["content"].strip()
        except (KeyError, AttributeError, TypeError) as exc:
            raise ProviderError(f"Réponse Ollama inattendue (format inconnu) : {data!r}") from exc

    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]], model: str | None = None
    ) -> ChatMessage:
        payload = {
            "model": model or self.default_model,
            "messages": [_to_ollama_dict(m) for m in messages],
            "tools": tools,
            "stream": False,
        }
        data = await self._post(payload)
        try:
            message = data["message"]
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Réponse Ollama inattendue (format inconnu) : {data!r}") from exc

        content = message.get("content")
        tool_calls: list[ToolCall] = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                import json

                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw_arguments": args, "_error": "arguments JSON invalides"}
            # Ollama ne fournit pas toujours d'id d'appel : on en génère un stable et local,
            # suffisant pour faire correspondre le résultat au bon appel dans la même boucle.
            tool_calls.append(
                ToolCall(id=tc.get("id") or f"ollama-call-{i}", name=fn.get("name", ""), arguments=args)
            )

        return ChatMessage(role="assistant", content=content, tool_calls=tool_calls or None)
