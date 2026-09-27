"""Tests CLI de 's1mone discover install/installed' (installation réelle confinée)."""

from __future__ import annotations

import subprocess

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isole la base SQLite ET fs_root/installed_apps dans un répertoire temporaire — même pattern
    que tests/test_memory.py (bug d'ordre d'exécution réel détecté et corrigé, voir D23)."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_discover_install_asks_for_confirmation_by_default(monkeypatch):
    result = runner.invoke(app, ["discover", "install", "npm", "is-odd"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout


def test_discover_install_with_yes_runs_and_shows_output(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "added 1 package\n")
    )
    result = runner.invoke(app, ["discover", "install", "npm", "is-odd", "--yes"])
    assert result.exit_code == 0
    assert "réussie" in result.stdout
    assert "added 1 package" in result.stdout


def test_discover_install_sourceforge_is_rejected():
    result = runner.invoke(app, ["discover", "install", "sourceforge", "qbittorrent", "--yes"])
    assert result.exit_code == 1
    assert "Aucune installation automatique" in result.stdout


def test_discover_install_auto_resolves_url_from_catalog(monkeypatch):
    """Pour un dépôt git connu du catalogue statique, l'URL n'a pas besoin d'être précisée à la
    main : elle est retrouvée automatiquement via core.discover."""
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(0, "Cloning...\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.invoke(app, ["discover", "install", "github", "ollama", "--yes"])
    assert result.exit_code == 0, result.output
    assert "https://github.com/ollama/ollama" in captured["cmd"]


def test_discover_installed_lists_history(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    runner.invoke(app, ["discover", "install", "npm", "is-odd", "--yes"])
    result = runner.invoke(app, ["discover", "installed"])
    assert result.exit_code == 0
    assert "is-odd" in result.stdout


def test_discover_installed_empty_by_default():
    result = runner.invoke(app, ["discover", "installed"])
    assert result.exit_code == 0
    assert "Aucune installation" in result.stdout
