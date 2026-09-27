"""core/stats.py — Tableau de bord d'usage (NEXT_STEPS.md §D.1, "et plus encore" post-C.3).

Objectif : donner une vue d'ensemble concrète de ce que S1M0NE contient et fait, en agrégeant
des compteurs déjà disponibles dans les modules existants (tasks, memory, cache, projects,
notifications, schedules) — zéro nouvelle table, zéro nouvelle dépendance, même principe que
`system/healthcheck.py` (Phase 9) : ce module ne fait qu'assembler, jamais de logique métier
dupliquée.

Différence avec `s1mone status` (Phase 9) : `status` est un diagnostic de bonne santé
(configuration valide ? disque accessible ? ressources OK ?), `stats` est un instantané d'usage
(combien de tâches, de recherches en cache, de notes en mémoire ...) — les deux se complètent
mais répondent à des questions différentes.
"""

from __future__ import annotations

import time
from typing import Any

from core import memory as memory_module
from core import notifications as notifications_module
from core import projects as projects_module
from core import scheduler as scheduler_module
from core.db import count_tasks_by_status, get_connection

_FINISHED_STATUSES = ("SUCCESS", "FAILED")


def _task_stats() -> dict[str, Any]:
    by_status = count_tasks_by_status()
    total = sum(by_status.values())
    finished = sum(by_status.get(s, 0) for s in _FINISHED_STATUSES)
    success = by_status.get("SUCCESS", 0)
    success_rate = round(100 * success / finished, 1) if finished else None
    return {"total": total, "by_status": by_status, "success_rate_percent": success_rate}


def _memory_stats() -> dict[str, Any]:
    entries = memory_module.list_memory()
    by_level: dict[str, int] = {}
    for entry in entries:
        by_level[entry["level"]] = by_level.get(entry["level"], 0) + 1
    return {"total": len(entries), "by_level": by_level}


def _cache_stats(now: float | None = None) -> dict[str, Any]:
    now = now if now is not None else time.time()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT "
            "COUNT(*) AS total, "
            "SUM(CASE WHEN (? - created_at) > ttl THEN 1 ELSE 0 END) AS expired "
            "FROM cache",
            (now,),
        ).fetchone()
    total = row["total"] or 0
    expired = row["expired"] or 0
    return {"total": total, "valid": total - expired, "expired": expired}


def _notification_stats() -> dict[str, Any]:
    total = len(notifications_module.list_notifications(unread_only=False, limit=1_000_000))
    return {"total": total, "unread": notifications_module.count_unread()}


def _schedule_stats() -> dict[str, Any]:
    schedules = scheduler_module.list_schedules()
    enabled = sum(1 for s in schedules if s.get("enabled"))
    return {"total": len(schedules), "enabled": enabled, "disabled": len(schedules) - enabled}


def usage_stats() -> dict[str, Any]:
    """Instantané complet de l'usage courant de S1M0NE. Ne modifie jamais rien (lecture seule)."""
    return {
        "generated_at": time.time(),
        "tasks": _task_stats(),
        "memory": _memory_stats(),
        "cache": _cache_stats(),
        "projects": {"total": len(projects_module.list_projects())},
        "notifications": _notification_stats(),
        "schedules": _schedule_stats(),
    }
