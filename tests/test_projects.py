"""Tests de core/projects.py (NEXT_STEPS.md §B.4)."""

from __future__ import annotations

import pytest

from core import memory, projects


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_create_and_get_project():
    project_id = projects.create_project("Mon Site", description="Un site perso", path="/tmp/x")
    project = projects.get_project(project_id)
    assert project["name"] == "Mon Site"
    assert project["description"] == "Un site perso"
    assert project["path"] == "/tmp/x"
    assert project["configuration"] == {}


def test_create_empty_name_raises():
    with pytest.raises(ValueError, match="vide"):
        projects.create_project("   ")


def test_create_duplicate_name_raises():
    projects.create_project("Doublon")
    with pytest.raises(ValueError, match="existe déjà"):
        projects.create_project("Doublon")


def test_get_project_by_name():
    project_id = projects.create_project("ParNom")
    assert projects.get_project_by_name("ParNom")["id"] == project_id
    assert projects.get_project_by_name("Inexistant") is None


def test_resolve_project_by_id_or_name():
    project_id = projects.create_project("Resolvable")
    assert projects.resolve_project(project_id)["name"] == "Resolvable"
    assert projects.resolve_project("Resolvable")["id"] == project_id
    assert projects.resolve_project("ni-id-ni-nom") is None


def test_list_projects_most_recently_updated_first():
    a = projects.create_project("A")
    b = projects.create_project("B")
    projects.update_project(a, description="mise à jour")
    names = [p["id"] for p in projects.list_projects()]
    assert names[0] == a
    assert b in names


def test_update_project_partial_fields():
    project_id = projects.create_project("Original", description="v1")
    ok = projects.update_project(project_id, description="v2")
    assert ok is True
    project = projects.get_project(project_id)
    assert project["name"] == "Original"  # inchangé
    assert project["description"] == "v2"


def test_update_unknown_project_returns_false():
    assert projects.update_project("id-inexistant", name="x") is False


def test_delete_project_removes_it():
    project_id = projects.create_project("À supprimer")
    assert projects.delete_project(project_id) is True
    assert projects.get_project(project_id) is None


def test_delete_unknown_project_returns_false():
    assert projects.delete_project("id-inexistant") is False


def test_delete_project_cascades_memory_by_default():
    project_id = projects.create_project("AvecMemoire")
    memory.remember("project", "note", "important", project_id=project_id)
    projects.delete_project(project_id)
    assert memory.recall("project", "note", project_id=project_id) is None


def test_delete_project_keep_memory_option():
    project_id = projects.create_project("GardeMemoire")
    memory.remember("project", "note", "important", project_id=project_id)
    projects.delete_project(project_id, delete_memory=False)
    # La mémoire brute existe toujours en base (accès direct par la clé namespacée), même si le
    # projet lui-même n'existe plus.
    from core.db import get_connection

    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM memory WHERE level='project' AND key=?", (f"{project_id}::note",)
        ).fetchone()
    assert row is not None


def test_delete_project_does_not_affect_other_projects_memory():
    p1 = projects.create_project("P1")
    p2 = projects.create_project("P2")
    memory.remember("project", "note", "p1-data", project_id=p1)
    memory.remember("project", "note", "p2-data", project_id=p2)
    projects.delete_project(p1)
    assert memory.recall("project", "note", project_id=p2) == "p2-data"
