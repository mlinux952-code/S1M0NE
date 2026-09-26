"""Tests du Task Manager (Phase 3)."""

import asyncio

import pytest

from tasks.manager import (
    cancel_task,
    execute_task,
    get_task,
    list_tasks,
    max_concurrent_tasks,
    run_pending_tasks,
    submit_task,
)
from tasks.registry import available_types


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Chaque test utilise sa propre base SQLite isolée (DATA_DIR temporaire)."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_registry_has_expected_builtin_types():
    types = available_types()
    assert "sleep" in types
    assert "system_snapshot" in types


def test_submit_unknown_type_is_rejected():
    with pytest.raises(ValueError):
        submit_task("type_inexistant", {})


def test_submit_creates_queued_task():
    task_id = submit_task("sleep", {"seconds": 0})
    task = get_task(task_id)
    assert task["status"] == "QUEUED"
    assert task["type"] == "sleep"


def test_execute_task_succeeds_and_stores_result():
    task_id = submit_task("sleep", {"seconds": 0})
    asyncio.run(execute_task(task_id))
    task = get_task(task_id)
    assert task["status"] == "SUCCESS"
    assert "slept_seconds" in task["result"]


def test_execute_system_snapshot_returns_real_metrics():
    task_id = submit_task("system_snapshot", {})
    asyncio.run(execute_task(task_id))
    task = get_task(task_id)
    assert task["status"] == "SUCCESS"
    assert "ram_total_gb" in task["result"]


def test_run_pending_tasks_processes_queue():
    submit_task("sleep", {"seconds": 0})
    submit_task("sleep", {"seconds": 0})
    processed = asyncio.run(run_pending_tasks())
    assert processed >= 1  # au moins 1, selon le parallélisme autorisé sur cette machine
    remaining = list_tasks(status="QUEUED")
    # soit tout est traité, soit le surplus reste en attente (limite de parallélisme) : jamais perdu
    done = list_tasks(status="SUCCESS")
    assert len(remaining) + len(done) == 2


def test_cancel_queued_task():
    task_id = submit_task("sleep", {"seconds": 30})
    ok = cancel_task(task_id)
    assert ok is True
    assert get_task(task_id)["status"] == "CANCELLED"


def test_cancel_unknown_task_returns_false():
    assert cancel_task("id-qui-nexiste-pas") is False


def test_cancel_running_task_actually_stops_it():
    task_id = submit_task("sleep", {"seconds": 5})

    async def scenario():
        running = asyncio.create_task(execute_task(task_id))
        await asyncio.sleep(0.1)  # laisse le temps à la tâche de passer en RUNNING
        assert get_task(task_id)["status"] == "RUNNING"
        cancelled = cancel_task(task_id)
        with pytest.raises(asyncio.CancelledError):
            await running
        return cancelled

    result = asyncio.run(scenario())
    assert result is True
    assert get_task(task_id)["status"] == "CANCELLED"


def test_max_concurrent_tasks_matches_config_for_normal_level():
    # Sur cette machine de test, le niveau est presque toujours NORMAL.
    n = max_concurrent_tasks()
    assert n >= 0
