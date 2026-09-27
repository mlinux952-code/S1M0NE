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
    memory.remember("project", "note", "à ne pas oublier")
    memory.forget("project", "note")
    assert memory.recall("project", "note") is None


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
