"""Tests de la CLI 's1mone memory ...' (Phase 7, transparence sur ce qui est mémorisé)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app
from core import memory

runner = CliRunner()


def test_memory_list_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["memory", "list"])
    assert result.exit_code == 0
    assert "Aucune entrée" in result.stdout


def test_memory_list_shows_stored_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("persistent", "chat_history", [{"role": "user", "content": "salut"}])

    result = runner.invoke(app, ["memory", "list"])
    assert result.exit_code == 0
    assert "persistent" in result.stdout
    assert "chat_history" in result.stdout


def test_memory_list_filters_by_level(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("temporary", "a", 1)
    memory.remember("persistent", "b", 2)

    result = runner.invoke(app, ["memory", "list", "--level", "persistent"])
    assert result.exit_code == 0
    assert "b" in result.stdout
    assert " a " not in result.stdout  # espacé pour éviter un faux positif sur un autre mot


def test_memory_list_query_filters_by_key_or_value(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("temporary", "shopping_list", "lait, pain")
    memory.remember("temporary", "other", "rien à voir")

    result = runner.invoke(app, ["memory", "list", "--query", "pain"])
    assert result.exit_code == 0
    assert "shopping_list" in result.stdout
    assert "other" not in result.stdout
    assert 'recherche : "pain"' in result.stdout


def test_memory_list_invalid_level_shows_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["memory", "list", "--level", "n-importe-quoi"])
    assert result.exit_code == 1
    assert "invalide" in result.stdout.lower()


def test_memory_show_displays_full_value(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("persistent", "ai_system_prompt", "prompt personnalisé")

    result = runner.invoke(app, ["memory", "show", "persistent", "ai_system_prompt"])
    assert result.exit_code == 0
    assert "prompt personnalisé" in result.stdout


def test_memory_show_missing_entry_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["memory", "show", "persistent", "n-existe-pas"])
    assert result.exit_code == 1
    assert "Aucune entrée" in result.stdout


def test_memory_forget_with_yes_flag_skips_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("persistent", "chat_history", ["quelque chose"])

    result = runner.invoke(app, ["memory", "forget", "persistent", "chat_history", "--yes"])
    assert result.exit_code == 0
    assert "Supprimé" in result.stdout
    assert memory.recall("persistent", "chat_history") is None


def test_memory_forget_without_yes_asks_confirmation_and_respects_no(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.db import init_db

    init_db()
    memory.remember("persistent", "chat_history", ["quelque chose"])

    result = runner.invoke(app, ["memory", "forget", "persistent", "chat_history"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout
    assert memory.recall("persistent", "chat_history") == ["quelque chose"]
