"""Tests de core/stats.py — tableau de bord d'usage (Catégorie D, post-NEXT_STEPS.md)."""

from __future__ import annotations

import pytest

from core import memory as memory_module
from core import notifications as notifications_module
from core import projects as projects_module
from core.cache import cache_set
from core.db import create_task, mark_task_failed, mark_task_success
from core.stats import usage_stats


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_usage_stats_all_zero_on_empty_database():
    data = usage_stats()
    assert data["tasks"] == {"total": 0, "by_status": {}, "success_rate_percent": None}
    assert data["memory"] == {"total": 0, "by_level": {}}
    assert data["cache"] == {"total": 0, "valid": 0, "expired": 0}
    assert data["projects"] == {"total": 0}
    assert data["notifications"] == {"total": 0, "unread": 0}
    assert data["schedules"] == {"total": 0, "enabled": 0, "disabled": 0}
    assert "generated_at" in data


def test_usage_stats_counts_tasks_by_status_and_success_rate():
    t1 = create_task("echo", {})
    t2 = create_task("echo", {})
    t3 = create_task("echo", {})
    mark_task_success(t1, {"ok": True})
    mark_task_success(t2, {"ok": True})
    mark_task_failed(t3, "boom")

    data = usage_stats()
    assert data["tasks"]["total"] == 3
    assert data["tasks"]["by_status"] == {"SUCCESS": 2, "FAILED": 1}
    assert data["tasks"]["success_rate_percent"] == pytest.approx(66.7, abs=0.1)


def test_usage_stats_ignores_queued_tasks_for_success_rate():
    create_task("echo", {})  # reste QUEUED
    data = usage_stats()
    assert data["tasks"]["total"] == 1
    assert data["tasks"]["success_rate_percent"] is None


def test_usage_stats_counts_memory_by_level():
    memory_module.remember("temporary", "scratch", "x")
    memory_module.remember("persistent", "chat_history", [1, 2, 3])
    data = usage_stats()
    assert data["memory"]["total"] == 2
    assert data["memory"]["by_level"] == {"temporary": 1, "persistent": 1}


def test_usage_stats_counts_cache_valid_and_expired():
    cache_set("fresh", {"a": 1}, ttl=3600)
    cache_set("stale", {"a": 2}, ttl=-1)  # déjà expirée dès sa création
    data = usage_stats()
    assert data["cache"]["total"] == 2
    assert data["cache"]["valid"] == 1
    assert data["cache"]["expired"] == 1


def test_usage_stats_counts_projects():
    projects_module.create_project("Projet A")
    projects_module.create_project("Projet B")
    data = usage_stats()
    assert data["projects"]["total"] == 2


def test_usage_stats_counts_notifications_read_and_unread():
    id1 = notifications_module.notify("Tâche terminée", level="success", desktop=False)
    notifications_module.notify("Erreur", level="error", desktop=False)
    notifications_module.mark_read(id1)
    data = usage_stats()
    assert data["notifications"]["total"] == 2
    assert data["notifications"]["unread"] == 1


def test_usage_stats_never_mutates_data():
    """Un simple instantané ne doit jamais créer/modifier/supprimer quoi que ce soit."""
    memory_module.remember("temporary", "before", "x")
    before = usage_stats()
    usage_stats()
    after = usage_stats()
    assert before["memory"]["total"] == after["memory"]["total"] == 1
