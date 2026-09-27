"""core/memory.py — Memory Manager de S1M0NE (Phase 7).

La table `memory` existe depuis la Phase 1 (core/db.py, mega-prompt §12) avec 4 niveaux :
- temporary  : bloc-notes éphémère (durée de vie courte, à vider souvent — usage libre).
- session    : propre à une session (terminal ou navigateur). Consommé depuis la Catégorie D
  (D.3) par les "notes de session" de la page web /memory, scopées par un cookie anonyme propre
  à chaque navigateur (voir web/app.py, BROWSER_SESSION_COOKIE) — pas de producteur CLI (aucune
  notion de "session terminal" stable entre deux invocations séparées de `s1mone`, contrairement
  à un onglet de navigateur qui persiste un cookie).
- project    : lié à un projet précis (table `projects`) — consommé depuis B.4.
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

# Séparateur utilisé pour scoper une clé des niveaux "project" (NEXT_STEPS §B.4) et "session"
# (Catégorie D §D.3) à un id précis, sans migration de schéma : la clé stockée en base reste
# "<scope_id>::<clé>", mais l'appelant continue de manipuler une clé "propre" (ex: "chat_history")
# + un id de scope séparé (project_id ou session_id selon le niveau).
_SCOPE_KEY_SEPARATOR = "::"

# Pour chaque niveau qui exige un id de scope : le nom du paramètre attendu (utilisé pour générer
# des messages d'erreur clairs et cohérents entre "project" et "session").
_SCOPE_PARAM_BY_LEVEL = {"project": "project_id", "session": "session_id"}


def _check_level(level: str) -> None:
    if level not in VALID_LEVELS:
        raise ValueError(f"Niveau de mémoire invalide : '{level}'. Attendu : {VALID_LEVELS}.")


def _storage_key(
    level: str, key: str, project_id: str | None = None, session_id: str | None = None
) -> str:
    """Traduit (level, key, project_id, session_id) en la clé réellement stockée en base.

    Règle stricte et sans ambiguïté, identique pour "project" et "session" : l'id de scope
    attendu par ce niveau est OBLIGATOIRE (sinon deux projets/sessions différents écraseraient la
    même clé sans le savoir), et tout id de scope non pertinent pour ce niveau est INTERDIT
    (évite un faux sentiment de scoping qui ne serait pas réellement appliqué)."""
    scopes = {"project": project_id, "session": session_id}
    expected_param = _SCOPE_PARAM_BY_LEVEL.get(level)

    for other_level, other_param in _SCOPE_PARAM_BY_LEVEL.items():
        if other_level != level and scopes[other_level] is not None:
            raise ValueError(f"{other_param} n'est utilisable qu'avec le niveau '{other_level}'.")

    if expected_param is None:
        return key

    scope_id = scopes[level]
    if not scope_id:
        hint = "'s1mone project list'/'s1mone project create'" if level == "project" else (
            "un cookie de session web (voir /memory)"
        )
        raise ValueError(f"Le niveau '{level}' exige un {expected_param} (voir {hint}).")
    return f"{scope_id}{_SCOPE_KEY_SEPARATOR}{key}"


def remember(
    level: str,
    key: str,
    value: Any,
    project_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Enregistre `value` sous (`level`, `key`), en remplaçant toute valeur précédente.

    `project_id` est requis quand `level == "project"` (voir core/projects.py). `session_id` est
    requis quand `level == "session"` (voir web/app.py, notes de session)."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id, session_id)
    serialized = json.dumps(value, ensure_ascii=False)
    now = time.time()
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, storage_key))
        conn.execute(
            "INSERT INTO memory (id, level, key, value, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), level, storage_key, serialized, now),
        )


def recall(
    level: str,
    key: str,
    default: Any = None,
    project_id: str | None = None,
    session_id: str | None = None,
) -> Any:
    """Relit la valeur enregistrée sous (`level`, `key`), ou `default` si absente/corrompue."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id, session_id)
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


def forget(
    level: str, key: str, project_id: str | None = None, session_id: str | None = None
) -> None:
    """Supprime la valeur enregistrée sous (`level`, `key`). Ne lève jamais si elle est absente."""
    _check_level(level)
    storage_key = _storage_key(level, key, project_id, session_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM memory WHERE level = ? AND key = ?", (level, storage_key))


def list_memory(
    level: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Liste les entrées mémoire (métadonnées uniquement, sans la valeur complète) — pour le
    debug/l'inspection (`s1mone memory list`).

    Pour les niveaux "project" et "session", chaque entrée expose en plus "project_id"/
    "session_id" et une "key" débarrassée de son préfixe technique. `project_id`/`session_id`
    filtrent sur un scope précis (impliquent le niveau correspondant, ou aucun niveau précisé).
    `query` (Catégorie D, "recherche plein texte dans la mémoire") filtre par sous-chaîne
    insensible à la casse/accents dans la clé (débarrassée de son préfixe de scope) OU dans la
    valeur JSON sérialisée — une recherche honnête et simple plutôt qu'un vrai moteur
    d'indexation, largement suffisante vu le volume de données personnelles concerné ici."""
    if level is not None:
        _check_level(level)
    for scope_level, scope_id, param_name in (
        ("project", project_id, "project_id"),
        ("session", session_id, "session_id"),
    ):
        if scope_id is not None and level not in (None, scope_level):
            raise ValueError(
                f"{param_name} n'est utilisable qu'avec le niveau '{scope_level}' "
                "(ou sans niveau précisé)."
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
        if entry["level"] in _SCOPE_PARAM_BY_LEVEL and _SCOPE_KEY_SEPARATOR in entry["key"]:
            scope_value, short_key = entry["key"].split(_SCOPE_KEY_SEPARATOR, 1)
            entry[_SCOPE_PARAM_BY_LEVEL[entry["level"]]] = scope_value
            entry["key"] = short_key
        if needle is not None:
            haystack = f"{entry['key']}\n{r['value'] or ''}".casefold()
            if needle not in haystack:
                continue
        entries.append(entry)

    if project_id is not None:
        entries = [e for e in entries if e.get("project_id") == project_id]
    if session_id is not None:
        entries = [e for e in entries if e.get("session_id") == session_id]
    return entries
