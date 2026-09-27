"""ai/gateway.py — AI Gateway de S1M0NE (Phase 6).

Point d'entrée unique utilisé par la CLI et le web : ni l'une ni l'autre ne parle directement à
un fournisseur (mega-prompt §5 : un seul cerveau, plusieurs façades — même principe que pour les
connecteurs de recherche en Phase 5).
"""

from __future__ import annotations

from ai.base import AIProvider, ChatMessage, ProviderError
from ai.providers.groq import GroqProvider
from ai.providers.ollama import OllamaProvider
from ai.providers.openrouter import OpenRouterProvider
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai")

__all__ = ["ChatMessage", "ProviderError", "available_providers", "resolve_provider", "chat"]

# Registre statique des fournisseurs disponibles (même pattern que connectors/engine.py).
_PROVIDERS: dict[str, AIProvider] = {
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
}


def available_providers() -> list[dict[str, object]]:
    """Liste des fournisseurs enregistrés, avec leur statut de configuration (pour l'UI/CLI)."""
    result = []
    for p in _PROVIDERS.values():
        configured = p.is_configured()
        result.append(
            {
                "name": p.name,
                "description": p.description,
                "default_model": p.default_model,
                "configured": configured,
                "setup_hint": None if configured else p.setup_hint(),
            }
        )
    return result


class UnknownProviderError(ProviderError):
    pass


def resolve_provider(provider_name: str | None) -> AIProvider:
    """Choisit le fournisseur : celui demandé explicitement, sinon celui par défaut de
    config.toml/.env. Lève une erreur claire si le nom demandé n'existe pas."""
    chosen_name = (provider_name or settings.ai_default_provider or "groq").strip().lower()
    provider = _PROVIDERS.get(chosen_name)
    if provider is None:
        raise UnknownProviderError(
            f"Fournisseur IA inconnu : '{chosen_name}'. Disponibles : {sorted(_PROVIDERS)} "
            "(voir 's1mone chat --list-providers')."
        )
    return provider


async def chat(
    messages: list[ChatMessage],
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, object]:
    """Envoie une conversation au fournisseur choisi.

    Retourne toujours un dict {"provider", "model", "reply"} en cas de succès, ou lève
    `ProviderError` (jamais de réponse inventée en cas d'échec — même règle que les connecteurs).
    """
    chosen = resolve_provider(provider)
    if not chosen.is_configured():
        raise ProviderError(chosen.setup_hint())

    resolved_model = model or settings.ai_provider_model(chosen.name) or chosen.default_model
    reply = await chosen.chat(messages, model=resolved_model)
    return {"provider": chosen.name, "model": resolved_model, "reply": reply}
