"""Tests de l'intégration web des notifications (NEXT_STEPS.md §B.3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app


def test_api_notifications_empty_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.get("/api/notifications")
        assert r.status_code == 200
        assert r.json() == {"notifications": [], "unread_count": 0}


def test_api_notifications_lists_created_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app):
        from core import notifications

        notifications.notify("Test", level="info", desktop=False)
        with TestClient(app) as client:
            r = client.get("/api/notifications")
            assert r.status_code == 200
            body = r.json()
            assert body["unread_count"] == 1
            assert len(body["notifications"]) == 1
            assert body["notifications"][0]["message"] == "Test"


def test_api_notifications_mark_read(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        from core import notifications

        notif_id = notifications.notify("Test", desktop=False)
        r = client.post(f"/api/notifications/{notif_id}/read")
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert client.get("/api/notifications").json()["unread_count"] == 0


def test_api_notifications_mark_read_unknown_id_404(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/notifications/id-inconnu/read")
        assert r.status_code == 404


def test_api_notifications_mark_all_read(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        from core import notifications

        notifications.notify("a", desktop=False)
        notifications.notify("b", desktop=False)
        r = client.post("/api/notifications/read-all")
        assert r.status_code == 200
        assert r.json() == {"ok": True, "count": 2}
        assert client.get("/api/notifications").json()["unread_count"] == 0


def test_partial_notifications_renders_bell(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        from core import notifications

        notifications.notify("Une alerte", desktop=False)
        r = client.get("/partials/notifications")
        assert r.status_code == 200
        assert "notif-bell" in r.text
        assert "Une alerte" in r.text


def test_partial_notifications_read_all_marks_and_rerenders(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        from core import notifications

        notifications.notify("a", desktop=False)
        r = client.post("/partials/notifications/read-all")
        assert r.status_code == 200
        assert notifications.count_unread() == 0


def test_dashboard_includes_notification_bell_trigger(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert 'id="notif-bell"' in r.text
        assert "/partials/notifications" in r.text
