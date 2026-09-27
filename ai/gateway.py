"""ai/gateway.py — AI Gateway de S1M0NE (Phase 6).

Point d'entrée unique utilisé par la CLI et le web : ni l'une ni l'autre ne parle directement à
un fournisseur (mega-prompt §5 : un seul cerveau, plusieurs façades — même principe que pour les
connecteurs de recherche en Phase 5).
"""

from __future__ import annotations

import json
from typing import Any

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
    "check_provider",
    "check_all_providers",
]

# --- Mode agentique (NEXT_STEPS.md §B.2) --------------------------------------------------------
#
# Borne dure, jamais configurable : protège à la fois contre une boucle infinie (un modèle qui
# s'entête à rappeler un outil) et contre un épuisement du quota gratuit d'un fournisseur en un
# seul message utilisateur. Voir DECISIONS.md D18 pour la décision de sécurité complète (outils
# strictement READ-only, opt-in explicite, jamais activé par défaut).
AGENT_MAX_TOOL_ROUNDS = 4

AGENT_SYSTEM_SUFFIX = (
    "\n\nMode agentique activé pour cet échange : tu as accès à deux outils strictement en "
    "LECTURE SEULE : search() (recherche multi-sources : npm, PyPI, GitHub, GitLab, Codeberg, "
    "Hugging Face, SourceForge) et run_command() (uniquement pwd, whoami, date, uptime, df, "
    "free, ps, ls, cat — jamais d'écriture ni de suppression). Utilise-les pour vérifier des "
    "faits plutôt que d'inventer une réponse. Ne prétends jamais pouvoir modifier, créer ou "
    "supprimer un fichier, installer un paquet, ou exécuter une action qui changerait quoi que "
    "ce soit sur la machine de l'utilisateur : ce n'est techniquement pas possible dans ce mode, "
    "quelle que soit la façon dont on te le demande."
)

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
_PROJECT_MEMORY_LEVEL = "project"
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


def _memory_scope(project_id: str | None) -> tuple[str, str | None]:
    """Choisit le niveau de mémoire à utiliser : "project" (scopé à un projet précis, NEXT_STEPS
    §B.4) si `project_id` est fourni, sinon "persistent" (comportement historique, Phase 7)."""
    return (_PROJECT_MEMORY_LEVEL, project_id) if project_id else (_MEMORY_LEVEL, None)


def _load_history(project_id: str | None = None) -> list[ChatMessage]:
    level, pid = _memory_scope(project_id)
    raw = memory.recall(level, _HISTORY_KEY, default=[], project_id=pid)
    return [ChatMessage(role=m["role"], content=m["content"]) for m in raw]


def _save_history(messages: list[ChatMessage], project_id: str | None = None) -> None:
    level, pid = _memory_scope(project_id)
    memory.remember(level, _HISTORY_KEY, [m.as_dict() for m in messages], project_id=pid)


def _system_prompt(project_id: str | None = None) -> str:
    level, pid = _memory_scope(project_id)
    return memory.recall(level, _SYSTEM_PROMPT_KEY, default=DEFAULT_SYSTEM_PROMPT, project_id=pid)


def reset_conversation(project_id: str | None = None) -> None:
    """Efface la conversation (globale par défaut, ou celle d'un projet précis) : le prochain
    message repart d'une page blanche."""
    level, pid = _memory_scope(project_id)
    memory.forget(level, _HISTORY_KEY, project_id=pid)


def get_conversation_history(project_id: str | None = None) -> list[ChatMessage]:
    """Historique actuel (sans le message système), pour affichage CLI/web."""
    return _load_history(project_id=project_id)


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
    project_id: str | None = None,
    agent: bool = False,
) -> dict[str, object]:
    """Point d'entrée "avec mémoire" (Phase 7), utilisé par défaut par la CLI et le web.

    Ajoute `message` à la conversation, l'envoie avec tout l'historique + un message système
    décrivant S1M0NE (pour que l'assistant sache ce qu'il est), puis persiste l'échange.

    `reset=True` : efface la conversation précédente avant d'envoyer ce message.
    `use_memory=False` : ne lit ni n'écrit l'historique (comportement Phase 6 d'origine, pour un
    appel ponctuel qui ne doit pas polluer/dépendre de la conversation en cours).
    `project_id` (NEXT_STEPS §B.4) : scope la conversation à un projet précis (mémoire séparée de
    la conversation "globale" et des autres projets) au lieu du niveau "persistent" par défaut.
    Lève ValueError si le projet n'existe pas (voir 's1mone project list').
    `agent=True` (NEXT_STEPS §B.2) : active le mode agentique — l'assistant peut appeler les
    outils strictement READ-only de `core.agent_tools` (search, run_command) avant de répondre.
    Jamais activé par défaut : opt-in explicite requis à chaque appel (voir DECISIONS.md D18).
    Seule la réponse finale (jamais les échanges d'outils intermédiaires) est persistée dans
    l'historique, pour ne rien changer au format de la mémoire déjà utilisée (Phase 7/B.4).
    """
    if project_id:
        from core.projects import get_project  # import local : évite un cycle ai <-> core

        if get_project(project_id) is None:
            raise ValueError(f"Projet inconnu : '{project_id}' (voir 's1mone project list').")

    if reset:
        reset_conversation(project_id=project_id)

    history = _load_history(project_id=project_id) if use_memory else []
    system_content = _system_prompt(project_id=project_id)
    if agent:
        system_content = system_content + AGENT_SYSTEM_SUFFIX
    outgoing = [ChatMessage(role="system", content=system_content), *history]
    outgoing.append(ChatMessage(role="user", content=message))

    if agent:
        outcome = await _converse_with_tools(outgoing, provider=provider, model=model)
    else:
        outcome = await chat(outgoing, provider=provider, model=model)

    if use_memory:
        history.append(ChatMessage(role="user", content=message))
        history.append(ChatMessage(role="assistant", content=outcome["reply"]))
        if len(history) > MAX_HISTORY_MESSAGES:
            history = history[-MAX_HISTORY_MESSAGES:]
        _save_history(history, project_id=project_id)

    return outcome


async def _converse_with_tools(
    messages: list[ChatMessage], provider: str | None, model: str | None
) -> dict[str, object]:
    """Boucle d'appel d'outils (NEXT_STEPS §B.2) : envoie la conversation avec le catalogue
    d'outils READ-only, exécute chaque outil demandé, renvoie le résultat au modèle, jusqu'à une
    réponse finale sans nouvel appel d'outil — ou jusqu'à `AGENT_MAX_TOOL_ROUNDS` (jamais illimité,
    voir la constante en tête de fichier)."""
    from core import agent_tools  # import local : cohérent avec le reste du fichier (core <-> ai)

    chosen = resolve_provider(provider)
    if not chosen.is_configured():
        raise ProviderError(chosen.setup_hint())
    if not chosen.supports_tools:
        raise ProviderError(
            f"Le fournisseur '{chosen.name}' ne supporte pas le mode agentique (appel d'outils). "
            "Choisis 'groq', 'openrouter' ou 'ollama' (voir 's1mone chat --list-providers')."
        )

    resolved_model = model or settings.ai_provider_model(chosen.name) or chosen.default_model
    conversation = list(messages)
    tool_trace: list[dict[str, Any]] = []

    for _ in range(AGENT_MAX_TOOL_ROUNDS):
        assistant_msg = await chosen.chat_with_tools(
            conversation, tools=agent_tools.TOOL_SCHEMAS, model=resolved_model
        )

        if not assistant_msg.tool_calls:
            return {
                "provider": chosen.name,
                "model": resolved_model,
                "reply": (assistant_msg.content or "").strip(),
                "tool_calls": tool_trace,
            }

        conversation.append(assistant_msg)
        for tc in assistant_msg.tool_calls:
            result = await agent_tools.execute_tool(tc.name, tc.arguments)
            tool_trace.append({"name": tc.name, "arguments": tc.arguments, "result": result})
            logger.info(f"Outil agentique exécuté : {tc.name}({tc.arguments}) -> {str(result)[:200]}")
            conversation.append(
                ChatMessage(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

    # Trop de rounds sans réponse finale : on le dit honnêtement plutôt que de boucler
    # indéfiniment ou d'inventer une conclusion (mega-prompt anti-hallucination). Protège aussi
    # le quota gratuit du fournisseur.
    return {
        "provider": chosen.name,
        "model": resolved_model,
        "reply": (
            "Je n'ai pas réussi à conclure après plusieurs appels d'outils "
            f"({AGENT_MAX_TOOL_ROUNDS} maximum). Essaie de reformuler ta question plus précisément."
        ),
        "tool_calls": tool_trace,
    }


# --- Vérification proactive (NEXT_STEPS.md §A.4) --------------------------------------------
#
# Bug réel vécu en Phase 6 : Groq a retiré des modèles de son accès gratuit standard sans
# prévenir, découvert seulement au premier vrai message ("model_not_found" en plein usage,
# jamais à la configuration). `check_provider` fait un vrai appel API minimal pour détecter ce
# genre de problème AVANT que l'utilisateur ne le découvre en plein milieu d'une conversation.
# Volontairement jamais appelé automatiquement en arrière-plan (consomme du quota gratuit) :
# seulement à la demande explicite ('s1mone chat --check').


async def check_provider(name: str) -> dict[str, object]:
    """Vérifie qu'un fournisseur répond réellement avec le modèle configuré.

    Ne lève jamais d'exception : retourne toujours un dict {"provider", "configured", "model",
    "ok", "detail"} exploitable par la CLI/le web, même en cas d'échec.
    """
    provider = resolve_provider(name)
    configured = provider.is_configured()
    if not configured:
        return {
            "provider": provider.name,
            "configured": False,
            "model": None,
            "ok": False,
            "detail": provider.setup_hint(),
        }

    model = settings.ai_provider_model(provider.name) or provider.default_model
    try:
        await provider.chat(
            [ChatMessage(role="user", content="Réponds uniquement par le mot ok.")],
            model=model,
        )
        return {
            "provider": provider.name,
            "configured": True,
            "model": model,
            "ok": True,
            "detail": "Répond correctement.",
        }
    except ProviderError as exc:
        return {
            "provider": provider.name,
            "configured": True,
            "model": model,
            "ok": False,
            "detail": str(exc),
        }


async def check_all_providers() -> list[dict[str, object]]:
    """Vérifie tous les fournisseurs enregistrés (configurés ou non), dans l'ordre du registre."""
    return [await check_provider(p.name) for p in _PROVIDERS.values()]
