"""core/agent_tools.py — Catalogue d'outils exposés à l'assistant IA en mode agentique
(NEXT_STEPS.md §B.2).

RÈGLE DE SÉCURITÉ NON NÉGOCIABLE (voir DECISIONS.md D18) :

Le modèle ne reçoit accès qu'à un sous-ensemble strictement READ-only, choisi ici EN DUR :

- `search()` : lecture seule par nature (interroge des registres publics en ligne, Phase 5).
- `run_command()` : verrouillé au niveau `Permission.READ` du Permission Manager (Phase 9),
  **jamais** dérivé de `settings.cli_permission_level` / `settings.web_permission_level`
  (qui peuvent être configurés plus haut par l'utilisateur pour SES propres usages), et
  **jamais** appelé avec `confirmed=True` — paramètre qui n'est d'ailleurs jamais exposé au
  modèle. Au niveau READ, aucune commande du catalogue n'est marquée destructive (voir
  core/permissions.py CATALOG) : il n'existe donc structurellement aucun chemin par lequel
  l'assistant pourrait écrire, modifier ou supprimer quoi que ce soit sur la machine.

Aucune configuration, aucun flag, aucun futur appelant ne doit pouvoir élever ce niveau : c'est
la garantie centrale qui rend le mode agentique acceptable sans humain dans la boucle pour
confirmer chaque appel d'outil (contrairement à `s1mone exec`, Phase 9, où une commande
destructive exige toujours une confirmation explicite d'un humain).
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging_setup import get_logger
from core.permissions import (
    ConfirmationRequiredError,
    Permission,
    PermissionError_,
    UnknownCommandError,
)
from core.shell_runner import run_command as _run_command_impl

logger = get_logger("s1mone.agent_tools")

# Toujours READ. Voir la docstring du module : ceci ne doit JAMAIS être rendu configurable.
AGENT_SHELL_PERMISSION = Permission.READ

# Borne le volume de résultats de recherche renvoyés au modèle (les quotas gratuits Groq/
# OpenRouter sont comptés en tokens : un outil qui renvoie des méga-octets de JSON les épuiserait
# en un seul appel).
MAX_SEARCH_RESULTS_RETURNED = 20

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Recherche en LECTURE SEULE dans les sources publiques connues de S1M0NE (npm, "
                "PyPI, GitHub, GitLab, Codeberg, Hugging Face, SourceForge). Utilise cet outil "
                "pour vérifier un fait ou trouver une information à jour plutôt que de deviner."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Termes de recherche."},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Sous-ensemble de sources à interroger (ex: ['github', 'pypi']). "
                            "Optionnel : toutes les sources sont interrogées par défaut."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": (
                "Exécute UNE commande système en LECTURE SEULE parmi : pwd, whoami, date, "
                "uptime, df, free, ps, ls [chemin], cat [chemin]. Les chemins sont bornés au "
                "dossier de données de S1M0NE. Aucune écriture ni suppression n'est possible "
                "avec cet outil, quelle que soit la commande demandée : ne propose jamais de "
                "l'utiliser pour modifier, créer ou supprimer quoi que ce soit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Ex: 'ls', 'cat notes.txt', 'df', 'ps'.",
                    }
                },
                "required": ["command"],
            },
        },
    },
]


def tool_names() -> list[str]:
    return [t["function"]["name"] for t in TOOL_SCHEMAS]


async def _tool_search(query: Any = None, sources: Any = None) -> dict[str, Any]:
    from connectors.engine import search_all  # import local : évite un cycle ai <-> connectors

    if not isinstance(query, str) or not query.strip():
        return {"error": "Paramètre 'query' manquant ou vide."}
    if sources is not None and not isinstance(sources, list):
        return {"error": "Paramètre 'sources' doit être une liste de noms de sources."}
    outcome = await search_all(query, limit_per_source=5, sources=sources)
    return {
        "results": outcome["results"][:MAX_SEARCH_RESULTS_RETURNED],
        "errors": outcome["errors"],
    }


def _tool_run_command(command: Any = None) -> dict[str, Any]:
    if not isinstance(command, str) or not command.strip():
        return {"error": "Paramètre 'command' manquant ou vide."}
    try:
        return _run_command_impl(
            command,
            level=AGENT_SHELL_PERMISSION,
            fs_root=settings.fs_root,
            confirmed=False,  # jamais accordé à l'IA (voir docstring du module)
        )
    except UnknownCommandError as exc:
        return {"error": str(exc)}
    except PermissionError_ as exc:
        return {"error": str(exc)}
    except ConfirmationRequiredError as exc:
        # Filet de sécurité : ne devrait jamais se produire, aucune commande READ n'est
        # destructive dans le catalogue (core/permissions.py). Si ce cas survient malgré tout
        # (ex: catalogue modifié par erreur plus tard), on refuse plutôt que de confirmer à la
        # place de l'utilisateur.
        return {"error": f"Refusé (commande destructrice, jamais autorisée pour l'IA) : {exc}"}
    except ValueError as exc:  # chemin hors fs_root, commande vide...
        return {"error": str(exc)}


async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Exécute un outil demandé par le modèle. Ne lève JAMAIS d'exception : toute erreur (outil
    inconnu, arguments invalides, permission refusée...) est renvoyée sous forme de résultat
    `{"error": "..."}`, redonné tel quel au modèle pour qu'il puisse s'ajuster — une panne d'outil
    ne doit jamais interrompre la conversation ni exposer une trace Python à l'utilisateur."""
    if not isinstance(arguments, dict):
        return {"error": f"Arguments invalides pour l'outil '{name}' : attendu un objet JSON."}
    try:
        if name == "search":
            return await _tool_search(**{k: v for k, v in arguments.items() if k in {"query", "sources"}})
        if name == "run_command":
            return _tool_run_command(**{k: v for k, v in arguments.items() if k in {"command"}})
        return {"error": f"Outil inconnu : '{name}'. Outils disponibles : {tool_names()}."}
    except TypeError as exc:
        return {"error": f"Arguments invalides pour l'outil '{name}' : {exc}"}
    except Exception as exc:  # noqa: BLE001 — jamais remonter une trace brute au modèle
        logger.error(f"Erreur inattendue dans l'outil '{name}' ({arguments!r}) : {exc}")
        return {"error": f"Erreur interne lors de l'exécution de l'outil '{name}'."}
