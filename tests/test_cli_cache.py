"""Tests de la CLI 's1mone cache list' / 's1mone cache clear' (Catégorie E.3)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)


def test_cache_list_empty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    assert "Cache vide" in result.stdout


def test_cache_list_shows_entries(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from core.cache import cache_set

    cache_set("search:npm:react:10", {"x": 1}, source="npm", ttl=300)

    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    assert "search:npm:react:10" in result.stdout
    assert "npm" in result.stdout
    assert "valide" in result.stdout


def test_cache_clear_all_asks_for_confirmation_without_yes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from core.cache import cache_get, cache_set

    cache_set("k1", "v1", ttl=300)

    result = runner.invoke(app, ["cache", "clear"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout
    assert cache_get("k1") == "v1"  # rien supprimé


def test_cache_clear_all_with_yes_wipes_everything(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from core.cache import cache_get, cache_set

    cache_set("k1", "v1", ttl=300)
    cache_set("k2", "v2", ttl=300)

    result = runner.invoke(app, ["cache", "clear", "--yes"])
    assert result.exit_code == 0
    assert "2 entrée" in result.stdout
    assert cache_get("k1") is None
    assert cache_get("k2") is None


def test_cache_clear_expired_only_keeps_valid_entries(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from core.cache import cache_get, cache_set

    cache_set("fresh", "ok", ttl=300)
    cache_set("stale", "trop-vieux", ttl=-1)

    result = runner.invoke(app, ["cache", "clear", "--expired-only", "--yes"])
    assert result.exit_code == 0
    assert cache_get("fresh") == "ok"
    assert cache_get("stale") is None


def test_cache_clear_single_key(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from core.cache import cache_get, cache_set

    cache_set("k1", "v1", ttl=300)
    cache_set("k2", "v2", ttl=300)

    result = runner.invoke(app, ["cache", "clear", "--key", "k1", "--yes"])
    assert result.exit_code == 0
    assert cache_get("k1") is None
    assert cache_get("k2") == "v2"
