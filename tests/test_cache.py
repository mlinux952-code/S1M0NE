"""Tests du Cache Manager (Phase 4)."""

import time

import pytest

from core.cache import cache_cleanup, cache_delete, cache_get, cache_set, make_key


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Chaque test utilise sa propre base SQLite isolée (DATA_DIR temporaire)."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_make_key_joins_parts_with_colon():
    assert make_key("search", "npm", "react", "10") == "search:npm:react:10"


def test_cache_set_then_get_returns_same_value():
    cache_set("k1", {"hello": "world"}, source="test")
    assert cache_get("k1") == {"hello": "world"}


def test_cache_get_missing_key_returns_none():
    assert cache_get("does-not-exist") is None


def test_cache_entry_expires_after_ttl():
    cache_set("k2", "valeur", ttl=0)  # expire immédiatement (created_at == now, ttl == 0)
    time.sleep(0.05)
    assert cache_get("k2") is None


def test_cache_set_overwrites_existing_key():
    cache_set("k3", "premiere valeur", ttl=300)
    cache_set("k3", "deuxieme valeur", ttl=300)
    assert cache_get("k3") == "deuxieme valeur"


def test_cache_delete_removes_entry():
    cache_set("k4", "a-supprimer", ttl=300)
    cache_delete("k4")
    assert cache_get("k4") is None


def test_cache_cleanup_removes_only_expired_entries():
    cache_set("still-fresh", "ok", ttl=300)
    cache_set("expired", "trop-vieux", ttl=10)

    removed = cache_cleanup(now=time.time() + 20)  # simule 20s plus tard

    assert removed == 1
    assert cache_get("still-fresh") == "ok"
    # note : cache_get lui-même filtrerait déjà l'entrée expirée si on ne l'avait pas nettoyée,
    # donc on vérifie surtout que cleanup ne supprime pas la fraîche.


def test_cache_uses_default_ttl_when_not_specified():
    cache_set("k5", "valeur-defaut")  # pas de ttl explicite -> settings.cache_default_ttl_seconds
    assert cache_get("k5") == "valeur-defaut"
