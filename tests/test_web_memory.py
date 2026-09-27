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


def test_partial_memory_list_query_filters_results():
    from core import memory as memory_module

    memory_module.remember("temporary", "shopping_list", "lait, pain")
    memory_module.remember("temporary", "other", "rien à voir")

    r = client.get("/partials/memory-list", params={"q": "pain"})
    assert r.status_code == 200
    assert "shopping_list" in r.text
    assert "other" not in r.text


def test_partial_memory_list_query_no_match_mentions_the_query():
    from core import memory as memory_module

    memory_module.remember("temporary", "note", "valeur")
    r = client.get("/partials/memory-list", params={"q": "introuvable"})
    assert r.status_code == 200
    assert "introuvable" in r.text


def test_memory_page_has_search_field():
    r = client.get("/memory")
    assert r.status_code == 200
    assert 'name="q"' in r.text


# --- Notes de session (Catégorie D §D.3) --------------------------------------------------------


def test_memory_page_sets_browser_session_cookie():
    r = client.get("/memory")
    assert r.status_code == 200
    assert "s1mone_browser_session" in r.cookies


def test_memory_page_shows_session_notes_section():
    r = client.get("/memory")
    assert "Notes de session" in r.text


def test_partial_session_notes_empty_by_default():
    local_client = TestClient(app)
    local_client.get("/memory")  # obtient le cookie de session
    r = local_client.get("/partials/session-notes")
    assert r.status_code == 200
    assert "Aucune note de session" in r.text


def test_saving_a_session_note_makes_it_appear():
    local_client = TestClient(app)
    local_client.get("/memory")
    r = local_client.post("/partials/session-notes", data={"key": "rappel", "value": "acheter du pain"})
    assert r.status_code == 200
    assert "rappel" in r.text
    assert "Aucune note" not in r.text


def test_session_notes_are_isolated_between_browser_sessions():
    client_a = TestClient(app)
    client_b = TestClient(app)
    client_a.get("/memory")
    client_b.get("/memory")
    client_a.post("/partials/session-notes", data={"key": "note-a", "value": "x"})

    r_a = client_a.get("/partials/session-notes")
    r_b = client_b.get("/partials/session-notes")
    assert "note-a" in r_a.text
    assert "note-a" not in r_b.text
    assert "Aucune note" in r_b.text


def test_forgetting_a_session_note_removes_it():
    local_client = TestClient(app)
    local_client.get("/memory")
    local_client.post("/partials/session-notes", data={"key": "rappel", "value": "x"})
    r = local_client.post("/partials/session-notes/forget", data={"key": "rappel"})
    assert r.status_code == 200
    assert "Aucune note de session" in r.text


def test_session_note_value_viewable_via_memory_value_partial():
    local_client = TestClient(app)
    local_client.get("/memory")
    local_client.post("/partials/session-notes", data={"key": "rappel", "value": "acheter du pain"})
    session_id = local_client.cookies.get("s1mone_browser_session")

    r = local_client.get(
        "/partials/memory-value",
        params={"level": "session", "key": "rappel", "session_id": session_id},
    )
    assert r.status_code == 200
    assert "acheter du pain" in r.text


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
