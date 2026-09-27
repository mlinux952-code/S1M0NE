"""Tests des notifications locales (NEXT_STEPS.md §B.3)."""

from __future__ import annotations

import pytest

from core import notifications


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_notify_creates_entry_without_desktop_call(monkeypatch):
    called = []
    monkeypatch.setattr(notifications, "_try_desktop_notification", lambda t, m: called.append((t, m)))
    notif_id = notifications.notify("Tâche terminée", level="success", desktop=False)
    assert notif_id
    items = notifications.list_notifications()
    assert len(items) == 1
    assert items[0]["message"] == "Tâche terminée"
    assert items[0]["level"] == "success"
    assert items[0]["read"] == 0
    assert called == []  # desktop=False : jamais tenté


def test_notify_invalid_level_raises():
    with pytest.raises(ValueError, match="invalide"):
        notifications.notify("test", level="bogus")


def test_notify_desktop_attempted_when_requested(monkeypatch):
    called = []
    monkeypatch.setattr(notifications, "_try_desktop_notification", lambda t, m: called.append((t, m)))
    notifications.notify("test", desktop=True)
    assert called == [("S1M0NE", "test")]


def test_try_desktop_notification_missing_binary_does_not_raise(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda name: None)
    notifications._try_desktop_notification("Titre", "Message")  # ne doit jamais lever


def test_try_desktop_notification_subprocess_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(notifications.shutil, "which", lambda name: "/usr/bin/notify-send")

    def _boom(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(notifications.subprocess, "run", _boom)
    notifications._try_desktop_notification("Titre", "Message")  # ne doit jamais lever


def test_count_unread():
    notifications.notify("a", desktop=False)
    notifications.notify("b", desktop=False)
    assert notifications.count_unread() == 2


def test_mark_read_single():
    notif_id = notifications.notify("a", desktop=False)
    notifications.notify("b", desktop=False)
    assert notifications.mark_read(notif_id) is True
    assert notifications.count_unread() == 1


def test_mark_read_unknown_id_returns_false():
    assert notifications.mark_read("id-inexistant") is False


def test_mark_all_read():
    notifications.notify("a", desktop=False)
    notifications.notify("b", desktop=False)
    n = notifications.mark_all_read()
    assert n == 2
    assert notifications.count_unread() == 0


def test_list_unread_only():
    id_a = notifications.notify("a", desktop=False)
    notifications.notify("b", desktop=False)
    notifications.mark_read(id_a)
    unread = notifications.list_notifications(unread_only=True)
    assert len(unread) == 1
    assert unread[0]["message"] == "b"


def test_clear_all():
    notifications.notify("a", desktop=False)
    notifications.notify("b", desktop=False)
    n = notifications.clear_all()
    assert n == 2
    assert notifications.list_notifications() == []


def test_notify_with_task_id_stored():
    notif_id = notifications.notify("Tâche X terminée", task_id="abc-123", desktop=False)
    items = notifications.list_notifications()
    assert items[0]["task_id"] == "abc-123"
    assert notif_id
