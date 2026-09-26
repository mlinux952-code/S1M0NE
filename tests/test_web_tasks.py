"""Tests de l'intégration web du Task Manager (Phase 3 - étape 4/4)."""

import time

from fastapi.testclient import TestClient

from web.app import app


def test_task_types_endpoint():
    with TestClient(app) as client:
        r = client.get("/api/task-types")
        assert r.status_code == 200
        assert "sleep" in r.json()["types"]


def test_submit_list_get_task_via_api():
    with TestClient(app) as client:
        r = client.post("/api/tasks", json={"type": "sleep", "parameters": {"seconds": 0}})
        assert r.status_code == 201
        task = r.json()["task"]
        assert task["status"] == "QUEUED"
        task_id = task["id"]

        r = client.get("/api/tasks")
        assert r.status_code == 200
        assert any(t["id"] == task_id for t in r.json()["tasks"])

        r = client.get(f"/api/tasks/{task_id}")
        assert r.status_code == 200
        assert r.json()["task"]["id"] == task_id


def test_submit_unknown_type_returns_400():
    with TestClient(app) as client:
        r = client.post("/api/tasks", json={"type": "inconnu"})
        assert r.status_code == 400


def test_get_unknown_task_returns_404():
    with TestClient(app) as client:
        r = client.get("/api/tasks/does-not-exist")
        assert r.status_code == 404


def test_cancel_task_via_api():
    with TestClient(app) as client:
        r = client.post("/api/tasks", json={"type": "sleep", "parameters": {"seconds": 30}})
        task_id = r.json()["task"]["id"]

        r = client.post(f"/api/tasks/{task_id}/cancel")
        assert r.status_code == 200
        assert r.json()["task"]["status"] == "CANCELLED"


def test_cancel_unknown_task_returns_404():
    with TestClient(app) as client:
        r = client.post("/api/tasks/does-not-exist/cancel")
        assert r.status_code == 404


def test_partial_tasks_html_renders():
    with TestClient(app) as client:
        r = client.get("/partials/tasks")
        assert r.status_code == 200
        assert "Task Manager" in r.text


def test_background_worker_actually_processes_submitted_task():
    """Vérifie que le worker embarqué dans le lifespan traite réellement une tâche soumise
    via l'API, sans qu'on ait besoin d'appeler explicitement 's1mone task worker'."""
    with TestClient(app) as client:
        r = client.post("/api/tasks", json={"type": "sleep", "parameters": {"seconds": 0}})
        task_id = r.json()["task"]["id"]

        deadline = time.time() + 6
        status = "QUEUED"
        while time.time() < deadline:
            status = client.get(f"/api/tasks/{task_id}").json()["task"]["status"]
            if status == "SUCCESS":
                break
            time.sleep(0.3)
        assert status == "SUCCESS"
