"""Tests de la CLI 's1mone notes index/search/stats/clear' (Catégorie F)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))


def test_notes_index_and_search_end_to_end(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "idee.md").write_text(
        "# Idée\n\nAjouter une sauvegarde chiffrée.", encoding="utf-8"
    )

    result = runner.invoke(app, ["notes", "index", str(notes_dir)])
    assert result.exit_code == 0
    assert "1 note" in result.stdout

    result = runner.invoke(app, ["notes", "search", "sauvegarde"])
    assert result.exit_code == 0
    assert "Idée" in result.stdout
    assert "idee.md" in result.stdout


def test_notes_index_missing_path_fails_cleanly(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["notes", "index", str(tmp_path / "n-existe-pas")])
    assert result.exit_code == 1


def test_notes_search_with_no_index_returns_no_results(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["notes", "search", "quoi-que-ce-soit"])
    assert result.exit_code == 0
    assert "Aucun résultat" in result.stdout


def test_notes_stats_on_fresh_database_works_without_manual_init(tmp_path, monkeypatch):
    """Régression : avant correctif, 'notes' (comme 'cache') n'étaient pas dans
    _COMMANDS_NEEDING_DB et plantaient sur une base SQLite jamais initialisée auparavant."""
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["notes", "stats"])
    assert result.exit_code == 0
    assert "0 note" in result.stdout


def test_notes_clear_asks_for_confirmation_without_yes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "a.md").write_text("contenu", encoding="utf-8")
    runner.invoke(app, ["notes", "index", str(notes_dir)])

    result = runner.invoke(app, ["notes", "clear"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout

    stats_result = runner.invoke(app, ["notes", "stats"])
    assert "1 note" in stats_result.stdout  # rien supprimé


def test_notes_clear_with_yes_empties_index(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "a.md").write_text("contenu", encoding="utf-8")
    runner.invoke(app, ["notes", "index", str(notes_dir)])

    result = runner.invoke(app, ["notes", "clear", "--yes"])
    assert result.exit_code == 0
    assert "retirée" in result.stdout

    stats_result = runner.invoke(app, ["notes", "stats"])
    assert "0 note" in stats_result.stdout


def test_cache_list_works_on_fresh_database_without_manual_init(tmp_path, monkeypatch):
    """Même régression que ci-dessus, vérifiée aussi pour 'cache' (bug réel introduit à la
    Catégorie E, jamais détecté avant car les tests initialisaient toujours la base à la main)."""
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["cache", "list"])
    assert result.exit_code == 0
    assert "Cache vide" in result.stdout
