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

# Séparateur utilisé pour scoper une clé du niveau "project" à un id de projet précis (NEXT_STEPS
# §B.4), sans migration de schéma : la clé stockée en base reste "<project_id>::<clé>", mais
# l'appelant continue de manipuler une clé "propre" (ex: "chat_history") + un project_id séparé.
_PROJECT_KEY_SEPARATOR = "::"


def _check_level(level: str) -> None:
    if level not in VALID_LEVELS:
        raise ValueError(f"Niveau de mémoire invalide : '{level}'. Attendu : {VALID_LEVELS}.")


def _storage_key(level: str, key: str, project_id: str | None) -> str:
    """Traduit (level, key, project_id) en la clé réellement stockée en base.

    Règle stricte et sans ambiguïté : `project_id` est OBLIGATOIRE pour le niveau "project"
    (sinon deux projets différents écraseraient la même clé sans le savoir), et INTERDIT pour
    tout autre niveau (project_id n'aurait aucun sens ailleurs — évite un faux sentiment de
    scoping qui ne serait pas réellement appliqué)."""
    if level == "project":
        if not project_id:
            raise ValueError(
                "Le niveau 'project' exige un project_id (voir 's1mone project list' ou "
                "'s1mone project create')."
            )
        return f"{project_id}{_PROJECT_KEY_SEPARATOR}{key}"
    if project_id is not None:
        raise ValueError("project_id n'est utilisable qu'avec le niveau 'project'.")
    return key


def remember(level: str, key: str, value: Any, project_id: str | None = None) -> None:
    """Enregistre `value` sous (`level`, `key`), en remplaçant toute valeur précédente.

    `project_id` est requis quand `level == "project"` (voir core/projects.py)."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id)
    serialized = json.dumps(value, ensure_ascii=False)
    now = time.time()
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, storage_key))
        conn.execute(
            "INSERT INTO memory (id, level, key, value, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), level, storage_key, serialized, now),
        )


def recall(level: str, key: str, default: Any = None, project_id: str | None = None) -> Any:
    """Relit la valeur enregistrée sous (`level`, `key`), ou `default` si absente/corrompue."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM memory WHERE level = ? AND key = ?", (level, storage_key)
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Entrée mémoire corrompue ignorée ({level}/{storage_key}).")
        return default


def forget(level: str, key: str, project_id: str | None = None) -> None:
    """Supprime la valeur enregistrée sous (`level`, `key`). Ne lève jamais si elle est absente."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, storage_key))


def list_memory(
    level: str | None = None, project_id: str | None = None, query: str | None = None
) -> list[dict[str, Any]]:
    """Liste les entrées mémoire (métadonnées uniquement, sans la valeur complète) — pour le
    debug/l'inspection (`s1mone memory list`).

    Pour le niveau "project", chaque entrée expose en plus "project_id" et une "key" débarrassée
    de son préfixe technique. `project_id` filtre sur un projet précis (implique level="project",
    ou aucun niveau précisé). `query` (Catégorie D, "recherche plein texte dans la mémoire") filtre
    par sous-chaîne insensible à la casse/accents dans la clé (débarrassée de son préfixe projet)
    OU dans la valeur JSON sérialisée — une recherche honnête et simple plutôt qu'un vrai moteur
    d'indexation, largement suffisante vu le volume de données personnelles concerné ici."""
    if level is not None:
        _check_level(level)
    if project_id is not None and level not in (None, "project"):
        raise ValueError(
            "project_id n'est utilisable qu'avec le niveau 'project' (ou sans niveau précisé)."
        )
    with get_connection() as conn:
        if level is None:
            rows = conn.execute(
                "SELECT level, key, value, created_at FROM memory ORDER BY level, key"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT level, key, value, created_at FROM memory WHERE level = ? ORDER BY key",
                (level,),
            ).fetchall()

    needle = query.strip().casefold() if query and query.strip() else None

    entries: list[dict[str, Any]] = []
    for r in rows:
        entry: dict[str, Any] = {"level": r["level"], "key": r["key"], "created_at": r["created_at"]}
        if entry["level"] == "project" and _PROJECT_KEY_SEPARATOR in entry["key"]:
            pid, short_key = entry["key"].split(_PROJECT_KEY_SEPARATOR, 1)
            entry["project_id"] = pid
            entry["key"] = short_key
        if needle is not None:
            haystack = f"{entry['key']}\n{r['value'] or ''}".casefold()
            if needle not in haystack:
                continue
        entries.append(entry)

    if project_id is not None:
        entries = [e for e in entries if e.get("project_id") == project_id]
    return entries
