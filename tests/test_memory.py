"""Tests du Memory Manager (Phase 7)."""

from __future__ import annotations

import pytest

from core import memory


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isole la base SQLite pour ne pas polluer les données réelles du projet (même pattern que
    tests/test_connectors.py et tests/test_cache.py)."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_remember_and_recall_roundtrip():
    memory.remember("persistent", "greeting", {"text": "salut"})
    assert memory.recall("persistent", "greeting") == {"text": "salut"}


def test_recall_missing_key_returns_default():
    assert memory.recall("persistent", "absent", default="valeur par défaut") == "valeur par défaut"
    assert memory.recall("temporary", "absent") is None


def test_remember_overwrites_previous_value_for_same_level_and_key():
    memory.remember("session", "x", 1)
    memory.remember("session", "x", 2)
    assert memory.recall("session", "x") == 2
    # une seule entrée doit rester, pas un historique qui s'accumule
    assert len(memory.list_memory("session")) == 1


def test_forget_removes_the_entry():
    memory.remember("persistent", "note", "à ne pas oublier")
    memory.forget("persistent", "note")
    assert memory.recall("persistent", "note") is None


def test_forget_is_silent_when_key_absent():
    memory.forget("temporary", "ne-existe-pas")  # ne doit pas lever


def test_different_levels_are_isolated():
    memory.remember("temporary", "k", "a")
    memory.remember("persistent", "k", "b")
    assert memory.recall("temporary", "k") == "a"
    assert memory.recall("persistent", "k") == "b"


def test_list_memory_filters_by_level():
    memory.remember("temporary", "a", 1)
    memory.remember("persistent", "b", 2)
    only_persistent = memory.list_memory("persistent")
    assert {e["key"] for e in only_persistent} == {"b"}


def test_invalid_level_raises_clear_error():
    with pytest.raises(ValueError, match="invalide"):
        memory.remember("pas-un-niveau-valide", "k", "v")
    with pytest.raises(ValueError, match="invalide"):
        memory.recall("pas-un-niveau-valide", "k")


# --- Scoping par projet (NEXT_STEPS.md §B.4) ---------------------------------------------------


def test_project_level_requires_project_id():
    with pytest.raises(ValueError, match="project_id"):
        memory.remember("project", "note", "valeur")
    with pytest.raises(ValueError, match="project_id"):
        memory.recall("project", "note")
    with pytest.raises(ValueError, match="project_id"):
        memory.forget("project", "note")


def test_non_project_level_rejects_project_id():
    with pytest.raises(ValueError, match="project_id"):
        memory.remember("persistent", "note", "valeur", project_id="abc")


def test_project_scoped_memory_roundtrip():
    memory.remember("project", "note", "contenu", project_id="projet-1")
    assert memory.recall("project", "note", project_id="projet-1") == "contenu"
    assert memory.recall("project", "note", project_id="projet-2") is None


def test_project_scoped_memory_isolated_between_projects():
    memory.remember("project", "k", "valeur-1", project_id="projet-1")
    memory.remember("project", "k", "valeur-2", project_id="projet-2")
    assert memory.recall("project", "k", project_id="projet-1") == "valeur-1"
    assert memory.recall("project", "k", project_id="projet-2") == "valeur-2"


def test_project_scoped_forget_only_affects_its_project():
    memory.remember("project", "k", "v1", project_id="projet-1")
    memory.remember("project", "k", "v2", project_id="projet-2")
    memory.forget("project", "k", project_id="projet-1")
    assert memory.recall("project", "k", project_id="projet-1") is None
    assert memory.recall("project", "k", project_id="projet-2") == "v2"


def test_list_memory_project_level_exposes_project_id_and_clean_key():
    memory.remember("project", "chat_history", ["a"], project_id="projet-1")
    entries = memory.list_memory("project")
    assert len(entries) == 1
    assert entries[0]["project_id"] == "projet-1"
    assert entries[0]["key"] == "chat_history"  # préfixe technique retiré


def test_list_memory_filter_by_project_id():
    memory.remember("project", "k", "v1", project_id="projet-1")
    memory.remember("project", "k", "v2", project_id="projet-2")
    entries = memory.list_memory(project_id="projet-1")
    assert len(entries) == 1
    assert entries[0]["project_id"] == "projet-1"


def test_list_memory_project_id_filter_requires_project_level():
    with pytest.raises(ValueError, match="project_id"):
        memory.list_memory(level="persistent", project_id="projet-1")


# --- Recherche plein texte (Catégorie D, "et plus encore" post-NEXT_STEPS.md) -------------------


def test_list_memory_query_matches_key():
    memory.remember("temporary", "shopping_list", "lait, pain")
    memory.remember("temporary", "other", "rien à voir")
    entries = memory.list_memory(query="shopping")
    assert len(entries) == 1
    assert entries[0]["key"] == "shopping_list"


def test_list_memory_query_matches_value():
    memory.remember("temporary", "note1", "penser à arroser les plantes")
    memory.remember("temporary", "note2", "rendez-vous chez le dentiste")
    entries = memory.list_memory(query="plantes")
    assert len(entries) == 1
    assert entries[0]["key"] == "note1"


def test_list_memory_query_is_case_insensitive():
    memory.remember("temporary", "greeting", "Bonjour Tout Le Monde")
    entries = memory.list_memory(query="bonjour")
    assert len(entries) == 1


def test_list_memory_query_no_match_returns_empty():
    memory.remember("temporary", "note", "valeur quelconque")
    assert memory.list_memory(query="introuvable") == []


def test_list_memory_query_combines_with_level_and_project_filters():
    memory.remember("project", "todo", "acheter du pain", project_id="projet-1")
    memory.remember("project", "todo", "acheter du pain", project_id="projet-2")
    entries = memory.list_memory(level="project", project_id="projet-1", query="pain")
    assert len(entries) == 1
    assert entries[0]["project_id"] == "projet-1"


def test_list_memory_empty_query_string_is_ignored():
    memory.remember("temporary", "note", "valeur")
    assert len(memory.list_memory(query="   ")) == 1
    assert len(memory.list_memory(query="")) == 1
