"""
core/db.py — Storage Manager (SQLite) de S1M0NE.

Schéma initial conforme au méga-prompt :
- tasks    (§13) : id, status, created_at, started_at, finished_at, type, parameters, result, error
- memory   (§12) : niveaux temporary / session / project / persistent
- cache    (§14) : clé/valeur avec TTL
- projects (§19) : id, name, description, path, created_at, updated_at, configuration

Choix : SQLite pur (module stdlib `sqlite3`), pas d'ORM, pas de serveur.
Un seul fichier .db, chemin défini par Settings.db_path (dans DATA_DIR).
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','SUCCESS','FAILED','CANCELLED')),
    type        TEXT NOT NULL,
    parameters  TEXT,
    result      TEXT,
    error       TEXT,
    created_at  REAL NOT NULL,
    started_at  REAL,
    finished_at REAL
);

CREATE TABLE IF NOT EXISTS memory (
    id         TEXT PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('temporary','session','project','persistent')),
    key        TEXT NOT NULL,
    value      TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_level_key ON memory(level, key);

CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    source     TEXT,
    created_at REAL NOT NULL,
    ttl        INTEGER NOT NULL DEFAULT 3600
);

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    path          TEXT,
    configuration TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

-- Table technique pour suivre la version du schéma (utile pour les futures migrations)
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

SCHEMA_VERSION = "1"


def _ensure_data_dir() -> Path:
    data_dir = settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Connexion SQLite avec fermeture garantie. WAL activé (meilleure tolérance concurrence)."""
    _ensure_data_dir()
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> Path:
    """Crée les tables si absentes. Idempotent : ne détruit jamais de données existantes."""
    path = db_path or settings.db_path
    with get_connection(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
    logger.info(f"Base SQLite initialisée : {path}")
    return path


def database_health() -> dict[str, Any]:
    """Vérifie que la base répond, sans jamais supposer qu'elle est déjà initialisée."""
    path = settings.db_path
    try:
        with get_connection(path) as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            expected = {"tasks", "memory", "cache", "projects", "schema_meta"}
            missing = expected - tables
            return {
                "ok": not missing,
                "path": str(path),
                "tables_present": sorted(tables),
                "tables_missing": sorted(missing),
            }
    except sqlite3.Error as exc:
        return {"ok": False, "path": str(path), "error": str(exc)}


# --- Helpers minimalistes pour la Phase 1 (le vrai Task Manager arrive en Phase 3) ---


def create_task(task_type: str, parameters: dict[str, Any] | None = None) -> str:
    task_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (id, status, type, parameters, created_at) VALUES (?,?,?,?,?)",
            (task_id, "QUEUED", task_type, json.dumps(parameters or {}), time.time()),
        )
    return task_id


def count_tasks_by_status() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT status, COUNT(*) as n FROM tasks GROUP BY status").fetchall()
        return {row["status"]: row["n"] for row in rows}


# --- Cycle de vie complet des tâches (Phase 3 — Task Manager) ---


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def fetch_queued_tasks(limit: int) -> list[dict[str, Any]]:
    """Récupère jusqu'à `limit` tâches QUEUED, les plus anciennes d'abord (FIFO)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'QUEUED' ORDER BY created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_task_running(task_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status='RUNNING', started_at=? WHERE id=? AND status='QUEUED'",
            (time.time(), task_id),
        )


def mark_task_success(task_id: str, result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status='SUCCESS', result=?, finished_at=? WHERE id=?",
            (json.dumps(result), time.time(), task_id),
        )


def mark_task_failed(task_id: str, error: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status='FAILED', error=?, finished_at=? WHERE id=?",
            (error, time.time(), task_id),
        )


def mark_task_cancelled(task_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status='CANCELLED', finished_at=? WHERE id=? "
            "AND status IN ('QUEUED','RUNNING')",
            (time.time(), task_id),
        )

