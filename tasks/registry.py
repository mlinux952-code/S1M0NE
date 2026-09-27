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

from core.logging_setup import get_logger
from plugins.manager import plugin_task_handlers

logger = get_logger("s1mone.tasks")

TaskHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

_HANDLERS: dict[str, TaskHandler] = {}


def register(name: str):
    """Décorateur : enregistre une fonction async comme handler du type de tâche `name`."""

    def decorator(fn: TaskHandler) -> TaskHandler:
        _HANDLERS[name] = fn
        return fn

    return decorator


def get_handler(name: str) -> TaskHandler | None:
    """Handler intégré si `name` en est un, sinon handler fourni par un plugin (Phase 8) —
    jamais l'inverse : un plugin ne peut pas redéfinir un type de tâche intégré."""
    handler = _HANDLERS.get(name)
    if handler is not None:
        return handler
    plugin_handlers = plugin_task_handlers()
    if name in plugin_handlers:
        return plugin_handlers[name]
    return None


def available_types() -> list[str]:
    """Types intégrés + types ajoutés par des plugins tiers (Phase 8)."""
    plugin_handlers = plugin_task_handlers()
    conflicts = set(plugin_handlers) & set(_HANDLERS)
    for name in conflicts:
        logger.warning(f"Plugin ignoré : le type de tâche '{name}' existe déjà (intégré).")
    return sorted(set(_HANDLERS) | set(plugin_handlers))


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


@register("backup")
async def _handle_backup(parameters: dict[str, Any]) -> dict[str, Any]:
    """Sauvegarde la base SQLite (core.db.backup_db, Phase A.2) — permet une sauvegarde
    automatique récurrente via 's1mone schedule create backup --interval 1d' (NEXT_STEPS §B.1),
    sans dupliquer la logique déjà utilisée par 's1mone backup create' en CLI."""
    from core.db import backup_db  # import local, même pattern que system_snapshot ci-dessus

    path = backup_db()
    return {"backup_path": str(path)}


@register("url_check")
async def _handle_url_check(parameters: dict[str, Any]) -> dict[str, Any]:
    """Vérifie qu'une URL répond (surveillance de disponibilité perso, Catégorie F). Se
    programme via 's1mone schedule create url_check --interval 5m
    --param url=https://exemple.com'. Logique complète dans core/url_check.py
    (notifie seulement un changement d'état, jamais à chaque vérification réussie)."""
    from core.url_check import check_url  # import local, même pattern que les autres handlers

    return await check_url(
        url=parameters.get("url"),
        timeout=float(parameters.get("timeout", 10.0)),
    )


@register("rss_check")
async def _handle_rss_check(parameters: dict[str, Any]) -> dict[str, Any]:
    """Surveille un flux RSS/Atom et notifie chaque nouvel article (Catégorie F). Se programme
    via 's1mone schedule create rss_check --interval 30m
    --param url=https://exemple.com/feed.xml --param name="Mon flux"'. Logique complète dans
    core/feed_check.py (parseur XML minimal, sans dépendance feedparser)."""
    from core.feed_check import check_feed  # import local, même pattern que les autres handlers

    return await check_feed(
        url=parameters.get("url"),
        name=parameters.get("name"),
        timeout=float(parameters.get("timeout", 15.0)),
    )

