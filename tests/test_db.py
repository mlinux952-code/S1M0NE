"""Tests du Storage Manager SQLite (Phase 1, étape 2)."""

from core.db import (
    count_tasks_by_status,
    create_task,
    database_health,
    get_connection,
    init_db,
    notes_fts_available,
)


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    with get_connection(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert {"tasks", "memory", "cache", "projects", "schema_meta"}.issubset(tables)


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    init_db(db_path)  # ne doit pas planter ni dupliquer/écraser
    with get_connection(db_path) as conn:
        n = conn.execute("SELECT COUNT(*) as n FROM schema_meta").fetchone()["n"]
    assert n == 1


def test_init_db_creates_notes_fts_table(tmp_path):
    """Catégorie F : la table FTS5 de recherche de notes doit exister après init_db (sauf
    dégradation gracieuse sur un SQLite sans FTS5, testée séparément ci-dessous)."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    assert notes_fts_available(db_path) is True


def test_notes_fts_available_is_false_when_table_absent(tmp_path):
    """Simule une base où la table notes_fts n'a jamais pu être créée (ex : SQLite compilé sans
    FTS5) : notes_fts_available() doit détecter l'absence sans lever d'exception."""
    db_path = tmp_path / "test_no_fts.db"
    with get_connection(db_path) as conn:
        conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
    assert notes_fts_available(db_path) is False


def test_database_health_reports_ok_after_init(monkeypatch, tmp_path):
    # settings.db_path est une propriété calculée à partir de S1MONE_DATA_DIR :
    # on la fait pointer vers un répertoire temporaire isolé pour ce test.
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings

    init_db(settings.db_path)
    health = database_health()
    assert health["ok"] is True
    assert not health["tables_missing"]


def test_create_task_and_count(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings

    init_db(settings.db_path)
    create_task("search", {"query": "fastapi"})
    create_task("search", {"query": "typer"})
    counts = count_tasks_by_status()
    assert counts.get("QUEUED") == 2
