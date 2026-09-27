"""core/memory.py — Memory Manager de S1M0NE (Phase 7).

La table `memory` existe depuis la Phase 1 (core/db.py, mega-prompt §12) avec 4 niveaux :
- temporary  : bloc-notes éphémère (durée de vie courte, à vider souvent — usage libre).
- session    : propre à une session (terminal ou navigateur) — pas encore consommé, réservé.
- project    : lié à un projet précis (table `projects`) — pas encore consommé, réservé.
- persistent : survit à tout (redémarrages, mises à jour) — utilisé en premier par le chat IA
  (Phase 6) pour que la conversation continue d'une session à l'autre au lieu de repartir de zéro.

Principe (mega-prompt §5) : ce module ajoute la logique métier par-dessus la table existante,
sans dupliquer le Storage Manager — même pattern que core/cache.py (Phase 4).

Une clé (level, key) est unique en pratique : `remember()` fait un upsert (supprime puis
réinsère) plutôt que de s'appuyer sur une contrainte SQL UNIQUE, pour rester compatible avec les
bases déjà créées par des installations antérieures à la Phase 7 (pas de migration de schéma
nécessaire).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.db import get_connection
from core.logging_setup import get_logger

logger = get_logger("s1mone.memory")

VALID_LEVELS = ("temporary", "session", "project", "persistent")


def _check_level(level: str) -> None:
    if level not in VALID_LEVELS:
        raise ValueError(f"Niveau de mémoire invalide : '{level}'. Attendu : {VALID_LEVELS}.")


def remember(level: str, key: str, value: Any) -> None:
    """Enregistre `value` sous (`level`, `key`), en remplaçant toute valeur précédente."""
    _check_level(level)
    serialized = json.dumps(value, ensure_ascii=False)
    now = time.time()
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, key))
        conn.execute(
            "INSERT INTO memory (id, level, key, value, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), level, key, serialized, now),
        )


def recall(level: str, key: str, default: Any = None) -> Any:
    """Relit la valeur enregistrée sous (`level`, `key`), ou `default` si absente/corrompue."""
    _check_level(level)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM memory WHERE level = ? AND key = ?", (level, key)
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Entrée mémoire corrompue ignorée ({level}/{key}).")
        return default


def forget(level: str, key: str) -> None:
    """Supprime la valeur enregistrée sous (`level`, `key`). Ne lève jamais si elle est absente."""
    _check_level(level)
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, key))


def list_memory(level: str | None = None) -> list[dict[str, Any]]:
    """Liste les entrées mémoire (métadonnées uniquement, sans la valeur complète) — pour le
    debug/l'inspection (`s1mone memory list`)."""
    if level is not None:
        _check_level(level)
    with get_connection() as conn:
        if level is None:
            rows = conn.execute(
                "SELECT level, key, created_at FROM memory ORDER BY level, key"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT level, key, created_at FROM memory WHERE level = ? ORDER BY key", (level,)
            ).fetchall()
    return [{"level": r["level"], "key": r["key"], "created_at": r["created_at"]} for r in rows]
