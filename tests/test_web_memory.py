"""Tests de la page web Mémoire (NEXT_STEPS.md §C.1)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_memory_page_loads():
    r = client.get("/memory")
    assert r.status_code == 200
    assert "Mémoire" in r.text
    assert "temporary" in r.text


def test_memory_nav_link_is_now_enabled():
    r = client.get("/")
    assert '<a href="/memory">Mémoire</a>' in r.text


def test_partial_memory_list_empty_by_default():
    r = client.get("/partials/memory-list")
    assert r.status_code == 200
    assert "Aucune entrée" in r.text


def test_partial_memory_list_shows_persisted_entries():
    from core import memory

    memory.remember("persistent", "note", "valeur test")
    r = client.get("/partials/memory-list")
    assert r.status_code == 200
    assert "persistent" in r.text
    assert "note" in r.text


def test_partial_memory_list_filters_by_level():
    from core import memory

    memory.remember("persistent", "a", 1)
    memory.remember("temporary", "b", 2)
    r = client.get("/partials/memory-list", params={"level": "temporary"})
    assert r.status_code == 200
    assert ">b<" in r.text
    assert ">a<" not in r.text


def test_partial_memory_list_filters_by_project():
    from core import memory, projects

    p1 = projects.create_project("P1")
    p2 = projects.create_project("P2")
    memory.remember("project", "k", "v1", project_id=p1)
    memory.remember("project", "k", "v2", project_id=p2)

    r = client.get("/partials/memory-list", params={"project_id": p1})
    assert r.status_code == 200
    assert p1 in r.text
    assert p2 not in r.text


def test_partial_memory_list_invalid_level_shows_error_not_500():
    r = client.get("/partials/memory-list", params={"level": "not-a-level"})
    assert r.status_code == 200
    assert "invalide" in r.text.lower()


def test_partial_memory_value_shows_full_content():
    from core import memory

    memory.remember("persistent", "note", {"texte": "bonjour"})
    r = client.get("/partials/memory-value", params={"level": "persistent", "key": "note"})
    assert r.status_code == 200
    assert "bonjour" in r.text


def test_partial_memory_value_project_scoped():
    from core import memory, projects

    p1 = projects.create_project("P1")
    memory.remember("project", "note", "contenu projet", project_id=p1)
    r = client.get(
        "/partials/memory-value", params={"level": "project", "key": "note", "project_id": p1}
    )
    assert r.status_code == 200
    assert "contenu projet" in r.text


def test_partial_memory_value_missing_project_id_shows_clear_error():
    r = client.get("/partials/memory-value", params={"level": "project", "key": "note"})
    assert r.status_code == 200
    assert "project_id" in r.text or "projet" in r.text.lower()


def test_partial_memory_forget_deletes_entry_and_reloads_list():
    from core import memory

    memory.remember("persistent", "note", "à supprimer")
    r = client.post("/partials/memory/forget", data={"level": "persistent", "key": "note"})
    assert r.status_code == 200
    assert "Aucune entrée" in r.text
    assert memory.recall("persistent", "note") is None


def test_partial_memory_forget_project_scoped():
    from core import memory, projects

    p1 = projects.create_project("P1")
    memory.remember("project", "note", "v", project_id=p1)
    r = client.post(
        "/partials/memory/forget", data={"level": "project", "key": "note", "project_id": p1}
    )
    assert r.status_code == 200
    assert memory.recall("project", "note", project_id=p1) is None


def test_partial_memory_forget_nonexistent_entry_is_a_noop_not_an_error():
    r = client.post("/partials/memory/forget", data={"level": "persistent", "key": "jamais-existé"})
    assert r.status_code == 200
    assert "error" not in r.text.lower() or "Aucune entrée" in r.text
