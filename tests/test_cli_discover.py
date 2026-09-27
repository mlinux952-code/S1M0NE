"""Tests de la CLI 's1mone discover list/search/sites' (Catégorie G)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_discover_sites_lists_seven_sites():
    result = runner.invoke(app, ["discover", "sites"])
    assert result.exit_code == 0
    assert "npm" in result.stdout
    assert "codeberg" in result.stdout


def test_discover_list_shows_entries_and_metadata():
    result = runner.invoke(app, ["discover", "list"])
    assert result.exit_code == 0
    assert "100" in result.stdout
    assert "compilé le" in result.stdout


def test_discover_list_filters_by_site():
    result = runner.invoke(app, ["discover", "list", "--site", "sourceforge"])
    assert result.exit_code == 0
    assert "sourceforge" in result.stdout
    assert "npm" not in result.stdout.split("compilé")[0]  # pas de faux positifs d'autres sites


def test_discover_search_finds_a_known_entry():
    result = runner.invoke(app, ["discover", "search", "lodash"])
    assert result.exit_code == 0
    assert "lodash" in result.stdout
    assert "npmjs.com" in result.stdout


def test_discover_search_no_match():
    result = runner.invoke(app, ["discover", "search", "zzzz-improbable-zzzz"])
    assert result.exit_code == 0
    assert "Aucun résultat" in result.stdout


def test_discover_works_without_any_database():
    """Le catalogue est un fichier JSON statique : aucune base SQLite n'est nécessaire, donc pas
    de risque de reproduire le bug _COMMANDS_NEEDING_DB (D21) ici."""
    result = runner.invoke(app, ["discover", "list"])
    assert result.exit_code == 0
