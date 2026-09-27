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

-- Notifications locales (NEXT_STEPS.md §B.3) : évènements à porter à l'attention de
-- l'utilisateur (fin de tâche, erreur...), consultables en CLI et affichées dans le dashboard.
CREATE TABLE IF NOT EXISTS notifications (
    id         TEXT PRIMARY KEY,
    level      TEXT NOT NULL CHECK (level IN ('info','success','error')),
    message    TEXT NOT NULL,
    task_id    TEXT,
    created_at REAL NOT NULL,
    read       INTEGER NOT NULL DEFAULT 0 CHECK (read IN (0,1))
);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(read);

-- Planifications récurrentes (NEXT_STEPS.md §B.1) : répète un type de tâche connu toutes les N
-- secondes, en réutilisant le Task Manager existant (une échéance = une tâche QUEUED normale).
CREATE TABLE IF NOT EXISTS schedules (
    id               TEXT PRIMARY KEY,
    task_type        TEXT NOT NULL,
    parameters       TEXT,
    interval_seconds INTEGER NOT NULL,
    enabled          INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    next_run_at      REAL NOT NULL,
    last_run_at      REAL,
    last_task_id     TEXT,
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled_next_run ON schedules(enabled, next_run_at);
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
            expected = {
                "tasks",
                "memory",
                "cache",
                "projects",
                "schema_meta",
                "notifications",
                "schedules",
            }
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


# --- Sauvegarde (NEXT_STEPS.md §A.2) ---
#
# Toute la mémoire de S1M0NE (conversations IA, tâches, cache) vit dans un seul fichier SQLite.
# `backup_db` en fait une copie datée via l'API de sauvegarde native de sqlite3
# (`sqlite3.Connection.backup`) plutôt qu'une simple copie de fichier : elle reste cohérente même
# si une autre connexion écrit pendant la sauvegarde (mode WAL), contrairement à un `cp` brut qui
# pourrait copier un fichier à moitié écrit.


def backup_db(destination_dir: Path | None = None, keep: int | None = None) -> Path:
    """Crée une sauvegarde horodatée de la base SQLite, puis purge les plus anciennes au-delà de
    `keep` (par défaut `Settings.backups_keep`). Lève FileNotFoundError si la base n'existe pas
    encore (jamais de sauvegarde fantôme d'un fichier inexistant)."""
    source_path = settings.db_path
    if not source_path.exists():
        raise FileNotFoundError(
            f"Base introuvable : {source_path}. Lance 's1mone status' pour l'initialiser d'abord."
        )
    dest_dir = destination_dir or settings.backups_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    dest_path = dest_dir / f"s1mone-{timestamp}.db"
    # Deux sauvegardes dans la même seconde ne doivent jamais s'écraser silencieusement (bug
    # constaté en test manuel : la résolution de strftime est la seconde).
    suffix = 2
    while dest_path.exists():
        dest_path = dest_dir / f"s1mone-{timestamp}-{suffix}.db"
        suffix += 1

    src_conn = sqlite3.connect(source_path)
    try:
        dest_conn = sqlite3.connect(dest_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    logger.info(f"Sauvegarde SQLite créée : {dest_path}")
    _prune_old_backups(dest_dir, settings.backups_keep if keep is None else keep)
    return dest_path


def _prune_old_backups(dest_dir: Path, keep: int) -> list[Path]:
    if keep <= 0:
        return []
    backups = sorted(dest_dir.glob("s1mone-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = backups[keep:]
    for path in to_delete:
        path.unlink(missing_ok=True)
        logger.info(f"Ancienne sauvegarde supprimée (rétention {keep}) : {path}")
    return to_delete


def list_backups(destination_dir: Path | None = None) -> list[dict[str, Any]]:
    """Liste les sauvegardes existantes, les plus récentes d'abord."""
    dest_dir = destination_dir or settings.backups_dir
    if not dest_dir.is_dir():
        return []
    backups = sorted(dest_dir.glob("s1mone-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "path": str(p),
            "size_bytes": p.stat().st_size,
            "created_at": p.stat().st_mtime,
        }
        for p in backups
    ]

