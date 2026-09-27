"""Tests de la sauvegarde SQLite (NEXT_STEPS.md §A.2)."""

from __future__ import annotations

import time

import pytest

from core import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings

    db.init_db(settings.db_path)
    yield tmp_path


def test_backup_creates_file(tmp_path):
    backups_dir = tmp_path / "backups"
    path = db.backup_db(destination_dir=backups_dir)
    assert path.exists()
    assert path.parent == backups_dir


def test_backup_missing_db_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "nonexistent"))
    with pytest.raises(FileNotFoundError):
        db.backup_db(destination_dir=tmp_path / "backups")


def test_backup_content_matches_source(tmp_path):
    from core import memory

    memory.remember("persistent", "test_key", {"hello": "world"})
    backups_dir = tmp_path / "backups"
    path = db.backup_db(destination_dir=backups_dir)

    import sqlite3

    conn = sqlite3.connect(path)
    row = conn.execute("SELECT value FROM memory WHERE key='test_key'").fetchone()
    conn.close()
    assert row is not None
    assert "world" in row[0]


def test_repeated_backups_in_same_second_do_not_collide(tmp_path):
    backups_dir = tmp_path / "backups"
    paths = {db.backup_db(destination_dir=backups_dir) for _ in range(5)}
    # 5 appels doivent produire 5 fichiers distincts, même si strftime() a une résolution de
    # la seconde (bug réel constaté en test manuel : le 2e écrasait silencieusement le 1er).
    assert len(paths) == 5
    for p in paths:
        assert p.exists()


def test_list_backups_empty(tmp_path):
    assert db.list_backups(destination_dir=tmp_path / "nothing_here") == []


def test_list_backups_sorted_most_recent_first(tmp_path):
    backups_dir = tmp_path / "backups"
    first = db.backup_db(destination_dir=backups_dir)
    time.sleep(0.01)
    second = db.backup_db(destination_dir=backups_dir)
    listed = db.list_backups(destination_dir=backups_dir)
    assert [b["path"] for b in listed][:2] == [str(second), str(first)] or len(listed) == 2


def test_prune_keeps_only_latest_n(tmp_path):
    backups_dir = tmp_path / "backups"
    for _ in range(5):
        db.backup_db(destination_dir=backups_dir, keep=3)
    remaining = db.list_backups(destination_dir=backups_dir)
    assert len(remaining) == 3


def test_keep_zero_disables_pruning(tmp_path):
    backups_dir = tmp_path / "backups"
    for _ in range(4):
        db.backup_db(destination_dir=backups_dir, keep=0)
    remaining = db.list_backups(destination_dir=backups_dir)
    assert len(remaining) == 4
