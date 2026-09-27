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
from core import memory
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.ai")

__all__ = [
    "ChatMessage",
    "ProviderError",
    "available_providers",
    "resolve_provider",
    "chat",
    "converse",
    "reset_conversation",
    "get_conversation_history",
]

# Registre statique des fournisseurs disponibles (même pattern que connectors/engine.py).
_PROVIDERS: dict[str, AIProvider] = {
    "groq": GroqProvider(),
    "openrouter": OpenRouterProvider(),
    "ollama": OllamaProvider(),
}

# --- Mémoire de conversation (Phase 7) ----------------------------------------------------------
# La conversation persiste d'une session à l'autre (redémarrage du process, nouveau terminal...)
# via le Memory Manager (core/memory.py, niveau "persistent") — voir DECISIONS.md.

_MEMORY_LEVEL = "persistent"
_HISTORY_KEY = "chat_history"
_SYSTEM_PROMPT_KEY = "ai_system_prompt"

# Borne la taille de l'historique envoyé à chaque appel : les quotas gratuits (Groq/OpenRouter)
# sont comptés en tokens/minute, un historique illimité finirait par tout consommer d'un coup.
MAX_HISTORY_MESSAGES = 40

DEFAULT_SYSTEM_PROMPT = (
    "Tu es l'assistant IA intégré à S1M0NE, une plateforme personnelle intelligente (\"maison "
    "numérique\") développée sur mesure : terminal avancé, interface web légère, moteur de "
    "tâches, moteur de recherche multi-sources (npm, Hugging Face, GitHub, GitLab, Codeberg, "
    "PyPI, SourceForge) et toi-même. Le projet tourne sur une machine modeste (~4 Gio de RAM). "
    "Réponds en français sauf si on te parle dans une autre langue, reste concis, et dis "
    "clairement quand tu ne sais pas plutôt que d'inventer une réponse."
)


def _load_history() -> list[ChatMessage]:
    raw = memory.recall(_MEMORY_LEVEL, _HISTORY_KEY, default=[])
    return [ChatMessage(role=m["role"], content=m["content"]) for m in raw]


def _save_history(messages: list[ChatMessage]) -> None:
    memory.remember(_MEMORY_LEVEL, _HISTORY_KEY, [m.as_dict() for m in messages])


def _system_prompt() -> str:
    return memory.recall(_MEMORY_LEVEL, _SYSTEM_PROMPT_KEY, default=DEFAULT_SYSTEM_PROMPT)


def reset_conversation() -> None:
    """Efface la conversation persistante : le prochain message repart d'une page blanche."""
    memory.forget(_MEMORY_LEVEL, _HISTORY_KEY)


def get_conversation_history() -> list[ChatMessage]:
    """Historique persistant actuel (sans le message système), pour affichage CLI/web."""
    return _load_history()


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


async def converse(
    message: str,
    provider: str | None = None,
    model: str | None = None,
    reset: bool = False,
    use_memory: bool = True,
) -> dict[str, object]:
    """Point d'entrée "avec mémoire" (Phase 7), utilisé par défaut par la CLI et le web.

    Ajoute `message` à la conversation persistante, l'envoie avec tout l'historique + un message
    système décrivant S1M0NE (pour que l'assistant sache ce qu'il est), puis persiste l'échange.

    `reset=True` : efface la conversation précédente avant d'envoyer ce message.
    `use_memory=False` : ne lit ni n'écrit l'historique (comportement Phase 6 d'origine, pour un
    appel ponctuel qui ne doit pas polluer/dépendre de la conversation en cours).
    """
    if reset:
        reset_conversation()

    history = _load_history() if use_memory else []
    outgoing = [ChatMessage(role="system", content=_system_prompt()), *history]
    outgoing.append(ChatMessage(role="user", content=message))

    outcome = await chat(outgoing, provider=provider, model=model)

    if use_memory:
        history.append(ChatMessage(role="user", content=message))
        history.append(ChatMessage(role="assistant", content=outcome["reply"]))
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        _save_history(history)

    return outcome
