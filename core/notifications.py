"""core/notifications.py — Notifications locales de S1M0NE (NEXT_STEPS.md §B.3).

Objectif : prévenir l'utilisateur quand quelque chose se termine (tâche réussie/échouée) sans
qu'il ait besoin de garder un œil sur `s1mone task list` en permanence.

Deux canaux, comme prévu dans NEXT_STEPS.md ("bureau ou dashboard") :
- **Dashboard** (fiable, toujours disponible) : chaque notification est stockée en SQLite
  (table `notifications`, Phase 1 + cette extension) et consultable via `s1mone notify` ou
  l'API web/dashboard (petite pastille "non lues").
- **Bureau** (best-effort) : tentative d'appel à `notify-send` (paquet `libnotify`, présent par
  défaut sur la plupart des environnements de bureau Linux) si disponible. Échoue silencieusement
  si absent ou si aucun environnement graphique n'est accessible (ex: service systemd --user sans
  session graphique, ou machine purement headless) — jamais une erreur bloquante, une
  notification manquée n'est jamais grave.

Même principe qu'ailleurs (core/cache.py, core/memory.py) : la table vit dans core/db.py
(Storage Manager), ce module ajoute la logique métier par-dessus.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from typing import Any

from core.db import get_connection
from core.logging_setup import get_logger

logger = get_logger("s1mone.notifications")

VALID_LEVELS = ("info", "success", "error")


def _check_level(level: str) -> None:
    if level not in VALID_LEVELS:
        raise ValueError(f"Niveau de notification invalide : '{level}'. Attendu : {VALID_LEVELS}.")


def notify(message: str, level: str = "info", task_id: str | None = None, desktop: bool = True) -> str:
    """Crée une notification (toujours enregistrée en base) et tente en plus un affichage
    bureau best-effort si `desktop=True`. Retourne l'id de la notification créée."""
    _check_level(level)
    notif_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO notifications (id, level, message, task_id, created_at, read) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (notif_id, level, message, task_id, time.time()),
        )
    if desktop:
        _try_desktop_notification("S1M0NE", message)
    return notif_id


def _try_desktop_notification(title: str, message: str) -> None:
    """Best-effort uniquement : ne lève jamais, ne bloque jamais le reste de S1M0NE."""
    notify_send = shutil.which("notify-send")
    if not notify_send:
        return
    try:
        subprocess.run(
            [notify_send, title, message],
            timeout=3,
            capture_output=True,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - un échec de notification bureau n'est jamais fatal
        logger.debug(f"Notification bureau non envoyée (best-effort) : {exc}")


def list_notifications(unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    """Liste les notifications les plus récentes d'abord."""
    with get_connection() as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def count_unread() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM notifications WHERE read = 0").fetchone()
        return int(row["n"]) if row else 0


def mark_read(notification_id: str) -> bool:
    """Marque une notification comme lue. Retourne False si elle n'existe pas."""
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,)
        )
        return cursor.rowcount > 0


def mark_all_read() -> int:
    """Marque toutes les notifications comme lues. Retourne le nombre affecté."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        return cursor.rowcount


def clear_all() -> int:
    """Supprime toutes les notifications (lues et non lues). Retourne le nombre supprimé."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM notifications")
        return cursor.rowcount
