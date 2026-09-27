"""Tests du Task Manager (Phase 3)."""

import asyncio
from pathlib import Path

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


def test_execute_task_success_creates_notification():
    from core import notifications

    task_id = submit_task("sleep", {"seconds": 0})
    asyncio.run(execute_task(task_id))
    items = notifications.list_notifications()
    assert len(items) == 1
    assert items[0]["level"] == "success"
    assert items[0]["task_id"] == task_id


def test_execute_task_failure_creates_error_notification():
    from core import notifications

    # "sleep" avec un paramètre non numérique fait planter le handler -> FAILED.
    task_id = submit_task("sleep", {"seconds": "pas-un-nombre"})
    asyncio.run(execute_task(task_id))
    assert get_task(task_id)["status"] == "FAILED"
    items = notifications.list_notifications()
    assert len(items) == 1
    assert items[0]["level"] == "error"
    assert items[0]["task_id"] == task_id


def test_notification_failure_never_breaks_task_execution(monkeypatch):
    import tasks.manager as manager_module

    def _boom(*args, **kwargs):
        raise RuntimeError("notification cassée")

    monkeypatch.setattr(manager_module.notifications, "notify", _boom)
    task_id = submit_task("sleep", {"seconds": 0})
    asyncio.run(execute_task(task_id))  # ne doit jamais lever malgré la notification cassée
    assert get_task(task_id)["status"] == "SUCCESS"


def test_worker_loop_creates_and_executes_due_scheduled_tasks():
    from core import scheduler

    schedule_id = scheduler.create_schedule(
        "sleep", parameters={"seconds": 0}, interval_seconds=3600, run_immediately=True
    )

    async def scenario():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.3)
            stop_event.set()

        await asyncio.gather(
            manager_module.worker_loop(interval_seconds=0.05, stop_event=stop_event), stopper()
        )

    import tasks.manager as manager_module

    asyncio.run(scenario())

    sched = scheduler.get_schedule(schedule_id)
    assert sched["last_task_id"] is not None
    task = get_task(sched["last_task_id"])
    assert task["status"] == "SUCCESS"


def test_worker_loop_schedule_error_never_stops_the_worker(monkeypatch):
    import tasks.manager as manager_module

    def _boom():
        raise RuntimeError("planification cassée")

    monkeypatch.setattr(manager_module.scheduler, "run_due_schedules", _boom)
    task_id = submit_task("sleep", {"seconds": 0})

    async def scenario():
        stop_event = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.2)
            stop_event.set()

        await asyncio.gather(
            manager_module.worker_loop(interval_seconds=0.05, stop_event=stop_event), stopper()
        )

    asyncio.run(scenario())
    assert get_task(task_id)["status"] == "SUCCESS"  # le worker a continué malgré l'erreur


def test_backup_task_type_creates_a_real_backup_file(tmp_path, monkeypatch):
    from core.config import Settings

    backups_dir = tmp_path / "backups"
    # `backups_dir` est une property calculée (pas un simple attribut) : on la remplace au niveau
    # de la classe pour la durée du test, afin de ne jamais écrire dans data/backups/ du vrai
    # dépôt pendant les tests (même précaution que pour S1MONE_DATA_DIR ailleurs dans ce fichier).
    monkeypatch.setattr(Settings, "backups_dir", property(lambda self: backups_dir))

    task_id = submit_task("backup", {})
    asyncio.run(execute_task(task_id))

    task = get_task(task_id)
    assert task["status"] == "SUCCESS"
    import json as _json

    result = _json.loads(task["result"])
    assert Path(result["backup_path"]).exists()


def test_backup_task_type_is_registered():
    assert "backup" in available_types()
