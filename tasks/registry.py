"""
tasks/registry.py — Registre des types de tâches exécutables par S1M0NE.

Principe (mega-prompt §13) : une tâche a un `type` connu à l'avance. On n'exécute jamais un type
inconnu ou une commande arbitraire — seuls les handlers explicitement enregistrés ici (ou par un
futur plugin, Phase 8) peuvent être exécutés. C'est la même philosophie de liste blanche que pour
le terminal web (Phase 2).

Handlers de démonstration pour la Phase 3 :
- "sleep"            : tâche factice pour tester file d'attente / annulation / concurrence.
- "system_snapshot"  : capture un instantané des ressources (réutilise system.monitor).

Les futurs types réels (recherche multi-source Phase 4, connecteurs Phase 5, etc.) s'enregistreront
de la même façon, sans toucher au moteur d'exécution dans tasks/manager.py.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

TaskHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_HANDLERS: dict[str, TaskHandler] = {}


def register(name: str):
    """Décorateur : enregistre une fonction async comme handler du type de tâche `name`."""

    def decorator(fn: TaskHandler) -> TaskHandler:
        _HANDLERS[name] = fn
        return fn

    return decorator


def get_handler(name: str) -> TaskHandler | None:
    return _HANDLERS.get(name)


def available_types() -> list[str]:
    return sorted(_HANDLERS.keys())


@register("sleep")
async def _handle_sleep(parameters: dict[str, Any]) -> dict[str, Any]:
    """Tâche de démonstration : attend N secondes (plafonné à 60s par sécurité)."""
    seconds = float(parameters.get("seconds", 2))
    seconds = max(0.0, min(seconds, 60.0))
    await asyncio.sleep(seconds)
    return {"slept_seconds": seconds}


@register("system_snapshot")
async def _handle_system_snapshot(parameters: dict[str, Any]) -> dict[str, Any]:
    """Capture un instantané CPU/RAM/disque via system.monitor (aucune logique dupliquée)."""
    from system.monitor import get_snapshot  # import local pour éviter tout cycle d'import

    return get_snapshot().as_dict()
