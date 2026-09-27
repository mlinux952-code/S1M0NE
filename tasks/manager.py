"""
tasks/manager.py — Task Manager de S1M0NE (Phase 3).

Choix d'architecture (voir DECISIONS.md D5) : moteur maison en asyncio + SQLite, pas de
Celery/RQ/Huey/Redis. Un seul processus (le serveur web, ou la CLI en mode worker) exécute les
tâches ; aucun broker externe, conforme à la règle LOW RESOURCE FIRST.

Intégration Resource Manager (mega-prompt §18) : le nombre de tâches exécutées en parallèle
dépend du niveau de ressources mesuré en direct (system.monitor.resource_level) :
    NORMAL   -> max_parallel_tasks_normal   (défaut 2, un par cœur physique sur le Dell cible)
    WARNING  -> max_parallel_tasks_warning  (défaut 1)
    CRITICAL -> max_parallel_tasks_critical (défaut 0 : aucune nouvelle tâche tant que ça ne va pas mieux)

Note de conception : les appels SQLite sont synchrones (module stdlib `sqlite3`, pas de driver
async). Pour le volume d'un usage personnel (quelques tâches à la fois), le coût est négligeable
(sub-milliseconde) et ne bloque pas significativement la boucle asyncio. À réévaluer si le volume
de tâches augmente fortement (Phase 10 - Optimisation) : passer ces appels dans asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from core import db, notifications, scheduler
from core.config import settings
from core.logging_setup import get_logger
from system.monitor import get_snapshot, resource_level
from tasks.registry import available_types, get_handler

logger = get_logger("s1mone.tasks")

# Suivi des tâches asyncio réellement en cours d'exécution, pour permettre une vraie annulation.
_running_asyncio_tasks: dict[str, asyncio.Task] = {}


def max_concurrent_tasks() -> int:
    """Combien de tâches peuvent démarrer maintenant, selon l'état réel des ressources."""
    level = resource_level(get_snapshot())
    limits = settings.resource_limits
    mapping = {
        "NORMAL": int(limits.get("max_parallel_tasks_normal", 2)),
        "WARNING": int(limits.get("max_parallel_tasks_warning", 1)),
        "CRITICAL": int(limits.get("max_parallel_tasks_critical", 0)),
    }
    return mapping.get(level, 1)


def submit_task(task_type: str, parameters: dict[str, Any] | None = None) -> str:
    """Crée une tâche QUEUED. Rejette immédiatement un type inconnu (liste blanche)."""
    if get_handler(task_type) is None:
        raise ValueError(
            f"Type de tâche inconnu : '{task_type}'. Types disponibles : {available_types()}"
        )
    task_id = db.create_task(task_type, parameters or {})
    logger.info(f"Tâche soumise : {task_id} (type={task_type})")
    return task_id


def list_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return db.list_tasks(status=status, limit=limit)


def get_task(task_id: str) -> dict[str, Any] | None:
    return db.get_task(task_id)


def cancel_task(task_id: str) -> bool:
    """Annule une tâche. QUEUED -> annulée immédiatement. RUNNING -> vraie annulation asyncio."""
    task = db.get_task(task_id)
    if not task:
        return False
    if task["status"] == "QUEUED":
        db.mark_task_cancelled(task_id)
        logger.info(f"Tâche {task_id} annulée (était en attente).")
        return True
    if task["status"] == "RUNNING":
        running = _running_asyncio_tasks.get(task_id)
        if running is not None:
            running.cancel()
            logger.info(f"Annulation demandée pour la tâche {task_id} (en cours d'exécution).")
            return True
        return False
    return False  # déjà SUCCESS / FAILED / CANCELLED : rien à faire


async def execute_task(task_id: str) -> None:
    """Exécute une tâche QUEUED de bout en bout et journalise chaque transition d'état."""
    task = db.get_task(task_id)
    if not task or task["status"] != "QUEUED":
        return

    handler = get_handler(task["type"])
    if handler is None:
        db.mark_task_failed(task_id, f"Type de tâche inconnu : {task['type']}")
        return

    db.mark_task_running(task_id)
    parameters = json.loads(task["parameters"] or "{}")

    current = asyncio.current_task()
    if current is not None:
        _running_asyncio_tasks[task_id] = current

    try:
        result = await handler(parameters)
        db.mark_task_success(task_id, result)
        logger.info(f"Tâche {task_id} ({task['type']}) terminée avec succès.")
        _notify_safely(f"Tâche '{task['type']}' terminée avec succès.", "success", task_id)
    except asyncio.CancelledError:
        db.mark_task_cancelled(task_id)
        logger.warning(f"Tâche {task_id} ({task['type']}) annulée pendant son exécution.")
        raise
    except Exception as exc:  # noqa: BLE001 - toute erreur de handler doit être capturée et stockée
        db.mark_task_failed(task_id, str(exc))
        logger.error(f"Tâche {task_id} ({task['type']}) échouée : {exc}")
        _notify_safely(f"Tâche '{task['type']}' échouée : {exc}", "error", task_id)
    finally:
        _running_asyncio_tasks.pop(task_id, None)


def run_due_schedules_safely() -> int:
    """Crée les tâches dues (NEXT_STEPS.md §B.1). Une erreur ici ne doit jamais arrêter le worker
    de tâches lui-même (même principe que _notify_safely juste en dessous). Public : réutilisé
    par 's1mone task worker --once' pour un comportement cohérent avec le mode continu."""
    try:
        return scheduler.run_due_schedules()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Erreur dans le traitement des planifications récurrentes : {exc}")
        return 0


def _notify_safely(message: str, level: str, task_id: str) -> None:
    """Une notification manquée ne doit jamais faire échouer une tâche par ailleurs réussie
    (NEXT_STEPS.md §B.3) : toute erreur ici est journalée, jamais propagée."""
    try:
        notifications.notify(message, level=level, task_id=task_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Notification non créée pour la tâche {task_id} : {exc}")


async def run_pending_tasks(limit: int | None = None) -> int:
    """Traite un lot de tâches QUEUED, dans la limite du parallélisme autorisé maintenant."""
    max_parallel = max_concurrent_tasks()
    if limit is not None:
        max_parallel = min(max_parallel, limit)
    if max_parallel <= 0:
        logger.warning("Ressources critiques : aucune nouvelle tâche démarrée ce cycle.")
        return 0

    queued = db.fetch_queued_tasks(limit=max_parallel)
    if not queued:
        return 0

    await asyncio.gather(*(execute_task(t["id"]) for t in queued), return_exceptions=True)
    return len(queued)


async def worker_loop(interval_seconds: float = 2.0, stop_event: asyncio.Event | None = None) -> None:
    """Boucle continue : traite les tâches en attente toutes les `interval_seconds`.

    S'arrête proprement dès que `stop_event` est déclenché (utilisé par le cycle de vie FastAPI
    pour ne garder qu'un seul processus permanent, conforme à la règle low-resource)."""
    logger.info("Task worker démarré.")
    while stop_event is None or not stop_event.is_set():
        try:
            run_due_schedules_safely()
            await run_pending_tasks()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Erreur dans le worker de tâches : {exc}")

        if stop_event is not None:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(interval_seconds)
    logger.info("Task worker arrêté proprement.")
