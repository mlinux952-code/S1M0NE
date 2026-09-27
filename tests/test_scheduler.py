"""Tests de core/scheduler.py (NEXT_STEPS.md §B.1)."""

from __future__ import annotations

import time

import pytest

from core import db, scheduler


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings

    db.init_db(settings.db_path)
    yield


# --- parse_interval ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_seconds",
    [
        ("30s", 30),
        ("5m", 300),
        ("2h", 7200),
        ("1d", 86400),
        ("90", 90),
        ("  10s  ", 10),
    ],
)
def test_parse_interval_accepts_expected_formats(text, expected_seconds):
    assert scheduler.parse_interval(text) == expected_seconds


@pytest.mark.parametrize("text", ["", "abc", "-5s", "5x", "0s"])
def test_parse_interval_rejects_invalid_formats(text):
    with pytest.raises(ValueError):
        scheduler.parse_interval(text)


# --- create_schedule -----------------------------------------------------------------------


def test_create_schedule_unknown_task_type_rejected():
    with pytest.raises(ValueError, match="inconnu"):
        scheduler.create_schedule("type-inexistant", interval_seconds=60)


def test_create_schedule_non_positive_interval_rejected():
    with pytest.raises(ValueError, match="positif"):
        scheduler.create_schedule("sleep", interval_seconds=0)


def test_create_schedule_default_next_run_is_in_the_future():
    before = time.time()
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=3600)
    sched = scheduler.get_schedule(schedule_id)
    assert sched["next_run_at"] > before
    assert sched["enabled"] == 1


def test_create_schedule_run_immediately_is_due_now():
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=3600, run_immediately=True)
    sched = scheduler.get_schedule(schedule_id)
    assert sched["next_run_at"] <= time.time()
    assert any(s["id"] == schedule_id for s in scheduler.due_schedules())


# --- list / get / enable / disable / delete -------------------------------------------------


def test_list_schedules_returns_all():
    scheduler.create_schedule("sleep", interval_seconds=60)
    scheduler.create_schedule("system_snapshot", interval_seconds=120)
    assert len(scheduler.list_schedules()) == 2


def test_get_unknown_schedule_returns_none():
    assert scheduler.get_schedule("id-inexistant") is None


def test_set_enabled_toggle():
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=60)
    assert scheduler.set_enabled(schedule_id, False) is True
    assert scheduler.get_schedule(schedule_id)["enabled"] == 0
    assert scheduler.set_enabled(schedule_id, True) is True
    assert scheduler.get_schedule(schedule_id)["enabled"] == 1


def test_set_enabled_unknown_returns_false():
    assert scheduler.set_enabled("id-inexistant", False) is False


def test_delete_schedule():
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=60)
    assert scheduler.delete_schedule(schedule_id) is True
    assert scheduler.get_schedule(schedule_id) is None


def test_delete_unknown_schedule_returns_false():
    assert scheduler.delete_schedule("id-inexistant") is False


# --- due_schedules / run_due_schedules -------------------------------------------------------


def test_due_schedules_excludes_disabled():
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=60, run_immediately=True)
    scheduler.set_enabled(schedule_id, False)
    assert scheduler.due_schedules() == []


def test_due_schedules_excludes_future_ones():
    scheduler.create_schedule("sleep", interval_seconds=3600, run_immediately=False)
    assert scheduler.due_schedules() == []


def test_run_due_schedules_creates_queued_task_and_reschedules():
    schedule_id = scheduler.create_schedule(
        "sleep", parameters={"seconds": 0}, interval_seconds=100, run_immediately=True
    )
    created = scheduler.run_due_schedules()
    assert created == 1

    sched = scheduler.get_schedule(schedule_id)
    assert sched["last_task_id"] is not None
    assert sched["last_run_at"] is not None
    assert sched["next_run_at"] > time.time()  # replanifié pour dans 100s

    task = db.get_task(sched["last_task_id"])
    assert task is not None
    assert task["type"] == "sleep"
    assert task["status"] == "QUEUED"


def test_run_due_schedules_is_idempotent_within_the_same_tick():
    scheduler.create_schedule("sleep", interval_seconds=100, run_immediately=True)
    first = scheduler.run_due_schedules()
    second = scheduler.run_due_schedules()  # replanifié dans le futur : plus dû immédiatement
    assert first == 1
    assert second == 0


def test_run_due_schedules_disables_schedule_with_vanished_task_type(monkeypatch):
    schedule_id = scheduler.create_schedule("sleep", interval_seconds=60, run_immediately=True)
    monkeypatch.setattr(scheduler, "get_handler", lambda name: None)
    created = scheduler.run_due_schedules()
    assert created == 0
    assert scheduler.get_schedule(schedule_id)["enabled"] == 0
