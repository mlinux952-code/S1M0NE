"""Tests de la CLI 's1mone search' (Phase 5 -> intégration CLI)."""

from __future__ import annotations

from typer.testing import CliRunner

import cli.main as cli_main
from cli.main import app

runner = CliRunner()


async def _fake_search_all(query, limit_per_source=10, sources=None):
    return {
        "results": [
            {
                "source": "npm",
                "name": "react",
                "description": "UI library",
                "url": "https://npmjs.com/package/react",
                "extra": {},
            },
            {
                "source": "pypi",
                "name": "Flask",
                "description": "web framework",
                "url": "https://pypi.org/project/Flask/",
                "extra": {"exact_match_only": True},
            },
        ],
        "errors": {},
        "cache_hits": [],
    }


def test_search_list_sources_shows_all_connectors():
    result = runner.invoke(app, ["search", "peu-importe", "--list-sources"])
    assert result.exit_code == 0
    assert "npm" in result.stdout
    assert "github" in result.stdout
    assert "sourceforge" in result.stdout


def test_search_list_sources_works_without_any_query():
    """Bug réel signalé par l'utilisateur : 's1mone search --list-sources' (sans terme de
    recherche) plantait avec 'Missing argument query' car l'argument était obligatoire."""
    result = runner.invoke(app, ["search", "--list-sources"])
    assert result.exit_code == 0
    assert "npm" in result.stdout


def test_search_without_query_and_without_list_sources_shows_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["search"])
    assert result.exit_code == 1
    assert "manquant" in result.stdout.lower() or "manquant" in str(result.exception)


def test_search_command_displays_results(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli_main, "search_all", _fake_search_all)

    result = runner.invoke(app, ["search", "react"])
    assert result.exit_code == 0
    assert "react" in result.stdout
    assert "Flask" in result.stdout
    assert "nom exact" in result.stdout  # marqueur du mode dégradé (pypi)


def test_search_command_shows_errors_when_a_connector_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))

    async def fake_with_error(query, limit_per_source=10, sources=None):
        return {"results": [], "errors": {"github": "panne simulée"}, "cache_hits": []}

    monkeypatch.setattr(cli_main, "search_all", fake_with_error)

    result = runner.invoke(app, ["search", "test"])
    assert result.exit_code == 0
    assert "panne simulée" in result.stdout
    assert "Aucun résultat" in result.stdout


def test_search_command_sort_by_name(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli_main, "search_all", _fake_search_all)

    result = runner.invoke(app, ["search", "react", "--sort", "name"])
    assert result.exit_code == 0
    # "Flask" (F) doit apparaître avant la ligne "npm" (source du résultat "react", r) : tri
    # alphabétique insensible à la casse (le titre du tableau contient déjà "react", donc on
    # compare sur les lignes de résultats plutôt que sur le mot "react" lui-même).
    assert result.stdout.index("Flask") < result.stdout.index("npm")


def test_search_command_invalid_sort_shows_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli_main, "search_all", _fake_search_all)

    result = runner.invoke(app, ["search", "react", "--sort", "date"])
    assert result.exit_code == 1
    assert "invalide" in result.stdout.lower()


def test_search_command_pagination_shows_page_info(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli_main, "search_all", _fake_search_all)

    result = runner.invoke(app, ["search", "react", "--page-size", "1"])
    assert result.exit_code == 0
    assert "page 1/2" in result.stdout.lower()
    assert "--page 2" in result.stdout


def test_search_command_page_two_shows_second_result_only(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cli_main, "search_all", _fake_search_all)

    result = runner.invoke(app, ["search", "react", "--page-size", "1", "--page", "2"])
    assert result.exit_code == 0
    assert "Flask" in result.stdout
    assert "npm" not in result.stdout  # le résultat "react" (source npm) est sur la page 1
