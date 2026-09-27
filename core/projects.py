"""core/projects.py — Gestion des projets (NEXT_STEPS.md §B.4).

La table `projects` existe depuis la Phase 1 (core/db.py, mega-prompt §19) mais n'avait jamais
été peuplée : ce module ajoute enfin son CRUD, et permet au niveau de mémoire "project" (réservé
depuis la Phase 7, jamais consommé) de servir à quelque chose de concret — en particulier une
conversation IA séparée par projet plutôt que tout mélanger dans un seul historique "persistent"
partagé (`s1mone chat --project <id>`, voir ai/gateway.py).

Même principe qu'ailleurs (core/cache.py, core/memory.py) : la table vit dans core/db.py, ce
module ajoute la logique métier par-dessus.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from core.db import get_connection
from core.logging_setup import get_logger

logger = get_logger("s1mone.projects")


def create_project(
    name: str,
    description: str | None = None,
    path: str | None = None,
    configuration: dict[str, Any] | None = None,
) -> str:
    """Crée un projet et retourne son id. Lève ValueError si le nom est vide ou déjà pris."""
    if not name or not name.strip():
        raise ValueError("Le nom du projet ne peut pas être vide.")
    name = name.strip()
    if get_project_by_name(name) is not None:
        raise ValueError(f"Un projet nommé '{name}' existe déjà (voir 's1mone project list').")

    project_id = str(uuid.uuid4())
    now = time.time()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, description, path, configuration, created_at, "
            "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, name, description, path, json.dumps(configuration or {}), now, now),
        )
    logger.info(f"Projet créé : {project_id} ({name})")
    return project_id


def get_project(project_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _deserialize(row) if row is not None else None


def get_project_by_name(name: str) -> dict[str, Any] | None:
    """Pratique pour la CLI/le chat : identifier un projet par son nom plutôt que son id complet."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return _deserialize(row) if row is not None else None


def resolve_project(identifier: str) -> dict[str, Any] | None:
    """Résout un projet par id OU par nom (pratique pour --project sur la CLI)."""
    return get_project(identifier) or get_project_by_name(identifier)


def list_projects() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [_deserialize(r) for r in rows]


def update_project(
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    path: str | None = None,
    configuration: dict[str, Any] | None = None,
) -> bool:
    """Met à jour les champs fournis (les autres restent inchangés). False si le projet n'existe pas."""
    existing = get_project(project_id)
    if existing is None:
        return False
    new_name = name.strip() if name else existing["name"]
    new_description = description if description is not None else existing["description"]
    new_path = path if path is not None else existing["path"]
    new_configuration = configuration if configuration is not None else existing["configuration"]
    with get_connection() as conn:
        conn.execute(
            "UPDATE projects SET name=?, description=?, path=?, configuration=?, updated_at=? "
            "WHERE id=?",
            (
                new_name,
                new_description,
                new_path,
                json.dumps(new_configuration),
                time.time(),
                project_id,
            ),
        )
    return True


def delete_project(project_id: str, delete_memory: bool = True) -> bool:
    """Supprime le projet. Par défaut, supprime aussi toute la mémoire associée (niveau
    "project" scopée à cet id) : un projet supprimé ne doit jamais laisser une mémoire orpheline
    invisible qui continuerait à occuper la base. False si le projet n'existe pas."""
    existing = get_project(project_id)
    if existing is None:
        return False
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if delete_memory:
            conn.execute(
                "DELETE FROM memory WHERE level = 'project' AND key LIKE ?",
                (f"{project_id}::%",),
            )
    suffix = " (mémoire associée effacée)" if delete_memory else " (mémoire conservée)"
    logger.info(f"Projet supprimé : {project_id}{suffix}")
    return True


def _deserialize(row: Any) -> dict[str, Any]:
    data = dict(row)
    try:
        data["configuration"] = json.loads(data["configuration"]) if data["configuration"] else {}
    except (json.JSONDecodeError, TypeError):
        data["configuration"] = {}
    return data
