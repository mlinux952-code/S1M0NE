"""core/scheduler.py — Tâches récurrentes (NEXT_STEPS.md §B.1).

Choix (voir DECISIONS.md D17) : intervalle simple exprimé en secondes/minutes/heures/jours
("30s", "5m", "2h", "1d"), pas de syntaxe cron complète — évite d'ajouter une dépendance
(`croniter`) pour un besoin personnel qui se résume à "répéter toutes les N minutes/heures/jours".

Le moteur ne duplique aucune logique d'exécution : une planification arrivée à échéance crée
simplement une tâche QUEUED normale (core.db.create_task), qui suit ensuite exactement le même
chemin que n'importe quelle tâche soumise manuellement (tasks/manager.py, Phase 3) — file
d'attente, limites de ressources, notifications (Phase B.3) comprises.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from core import db
from core.db import get_connection
from core.logging_setup import get_logger
from tasks.registry import available_types, get_handler

logger = get_logger("s1mone.scheduler")

_INTERVAL_RE = re.compile(r"^(\d+)\s*([smhd]?)$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "": 1}


def parse_interval(text: str) -> int:
    """Parse une durée simple ("30s", "5m", "2h", "1d", ou un nombre nu = secondes) en secondes.

    Lève ValueError avec un message actionnable si le format n'est pas reconnu."""
    match = _INTERVAL_RE.match(text.strip())
    if not match:
        raise ValueError(
            f"Intervalle invalide : '{text}'. Formats acceptés : '30s', '5m', '2h', '1d', ou un "
            "nombre de secondes nu (ex: '90')."
        )
    value, unit = match.groups()
    seconds = int(value) * _UNIT_SECONDS[unit.lower()]
    if seconds <= 0:
        raise ValueError("L'intervalle doit être strictement positif.")
    return seconds


def create_schedule(
    task_type: str,
    parameters: dict[str, Any] | None = None,
    interval_seconds: int = 3600,
    run_immediately: bool = False,
) -> str:
    """Crée une planification. Rejette immédiatement un type de tâche inconnu (même liste
    blanche que `tasks.manager.submit_task`) ou un intervalle invalide."""
    if get_handler(task_type) is None:
        raise ValueError(
            f"Type de tâche inconnu : '{task_type}'. Types disponibles : {available_types()}"
        )
    if interval_seconds <= 0:
        raise ValueError("L'intervalle doit être strictement positif (en secondes).")

    schedule_id = str(uuid.uuid4())
    now = time.time()
    next_run_at = now if run_immediately else now + interval_seconds
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO schedules (id, task_type, parameters, interval_seconds, enabled, "
            "next_run_at, created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (schedule_id, task_type, json.dumps(parameters or {}), interval_seconds, next_run_at, now),
        )
    logger.info(
        f"Planification créée : {schedule_id} (type={task_type}, toutes les {interval_seconds}s)"
    )
    return schedule_id


def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return dict(row) if row is not None else None


def list_schedules() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def set_enabled(schedule_id: str, enabled: bool) -> bool:
    """Active/désactive une planification sans la supprimer. False si elle n'existe pas."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE schedules SET enabled = ? WHERE id = ?", (1 if enabled else 0, schedule_id)
        )
        return cursor.rowcount > 0


def delete_schedule(schedule_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        return cursor.rowcount > 0


def due_schedules(now: float | None = None) -> list[dict[str, Any]]:
    """Planifications actives dont l'échéance est arrivée."""
    now = now if now is not None else time.time()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM schedules WHERE enabled = 1 AND next_run_at <= ?", (now,)
        ).fetchall()
    return [dict(r) for r in rows]


def _record_run(schedule_id: str, task_id: str, now: float | None = None) -> None:
    now = now if now is not None else time.time()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT interval_seconds FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        if row is None:
            return
        next_run_at = now + row["interval_seconds"]
        conn.execute(
            "UPDATE schedules SET last_run_at = ?, last_task_id = ?, next_run_at = ? WHERE id = ?",
            (now, task_id, next_run_at, schedule_id),
        )


def run_due_schedules() -> int:
    """Crée une tâche QUEUED pour chaque planification arrivée à échéance. Retourne le nombre de
    tâches créées.

    Une planification dont le type de tâche a disparu entre-temps (ex: plugin désinstallé,
    Phase 8) est désactivée automatiquement avec un avertissement journalisé, plutôt que
    d'échouer silencieusement en boucle à chaque tick pour toujours la même raison."""
    created = 0
    for sched in due_schedules():
        if get_handler(sched["task_type"]) is None:
            logger.warning(
                f"Planification {sched['id']} désactivée : type de tâche "
                f"'{sched['task_type']}' introuvable (plugin désinstallé ?)."
            )
            set_enabled(sched["id"], False)
            continue
        parameters = json.loads(sched["parameters"] or "{}")
        task_id = db.create_task(sched["task_type"], parameters)
        _record_run(sched["id"], task_id)
        logger.info(f"Tâche {task_id} créée automatiquement par la planification {sched['id']}.")
        created += 1
    return created
