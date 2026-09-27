"""ai/providers/groq.py — Fournisseur Groq (Phase 6).

Recommandé par défaut : API compatible OpenAI, aucune carte bancaire requise pour créer un
compte. Catalogue de modèles vérifié en direct sur https://console.groq.com/docs/models
(dernière vérification : septembre 2026) — Groq a fait passer ses modèles Llama (3.1 8B,
3.3 70B) en accès "Enterprise" (contact commercial), ils NE sont plus utilisables avec une simple
clé développeur gratuite. Modèle par défaut retenu ici : openai/gpt-oss-20b (modèle "Production",
accessible avec une clé standard, très rapide ~1000 tok/s). Comme pour OpenRouter, ce catalogue
peut encore changer : configurable sans toucher au code via config.toml [ai.groq] model = "...".
Clé gratuite : https://console.groq.com/keys

NEXT_STEPS.md §B.2 : `chat_with_tools()` utilise l'API "tools" (function calling) native
d'OpenAI, que Groq expose telle quelle sur le même endpoint `/chat/completions`.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ai.base import AIProvider, ChatMessage, ProviderError, ToolCall
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai.groq")

API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _to_openai_dict(m: ChatMessage) -> dict[str, Any]:
    """Traduit un ChatMessage canonique (ai/base.py) vers le dialecte OpenAI attendu par Groq :
    `tool_calls.function.arguments` est une CHAÎNE JSON (pas un dict)."""
    d: dict[str, Any] = {"role": m.role, "content": m.content if m.content is not None else ""}
    if m.tool_calls:
        d["content"] = m.content  # peut être None pour un message assistant qui appelle un outil
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
            }
            for tc in m.tool_calls
        ]
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    if m.name:
        d["name"] = m.name
    return d


class GroqProvider(AIProvider):
    name = "groq"
    description = (
        "Groq (console.groq.com) — Llama/Qwen/Gemma hébergés, gratuit sans carte bancaire, "
        "réponses très rapides. Quota : ~30 req/min, jusqu'à 500k tokens/jour selon le modèle."
    )
    default_model = "openai/gpt-oss-20b"
    supports_tools = True  # NEXT_STEPS §B.2 : API tools native, compatible OpenAI.

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

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Requête + gestion d'erreurs communes à `chat()` et `chat_with_tools()` : un seul
        endroit qui sait traduire les codes HTTP Groq en `ProviderError` actionnables."""
        api_key = settings.get_secret("GROQ_API_KEY")
        if not api_key:
            raise ProviderError(self.setup_hint())
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
                f"Modèle Groq '{payload.get('model')}' introuvable ou réservé aux comptes "
                "Enterprise (404). Le catalogue Groq change régulièrement : vérifie la liste à "
                "jour sur https://console.groq.com/docs/models et ajuste [ai.groq] model dans "
                "config.toml (ou --model sur la ligne de commande)."
            )
        if response.status_code >= 400:
            raise ProviderError(f"Groq a renvoyé une erreur {response.status_code} : {response.text[:300]}")

        return response.json()

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        payload = {
            "model": model or self.default_model,
            "messages": [m.as_dict() for m in messages],
        }
        data = await self._post(payload)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise ProviderError(f"Réponse Groq inattendue (format inconnu) : {data!r}") from exc

    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]], model: str | None = None
    ) -> ChatMessage:
        payload = {
            "model": model or self.default_model,
            "messages": [_to_openai_dict(m) for m in messages],
            "tools": tools,
            "tool_choice": "auto",
        }
        data = await self._post(payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Réponse Groq inattendue (format inconnu) : {data!r}") from exc

        content = message.get("content")
        tool_calls: list[ToolCall] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                # Le modèle a renvoyé des arguments mal formés : on ne devine pas, on transmet
                # l'erreur telle quelle à execute_tool() qui la renverra au modèle pour correction
                # (anti-hallucination : jamais fabriquer une valeur plausible à la place).
                args = {"_raw_arguments": raw_args, "_error": "arguments JSON invalides"}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))

        return ChatMessage(role="assistant", content=content, tool_calls=tool_calls or None)
