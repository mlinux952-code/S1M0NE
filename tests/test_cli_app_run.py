"""Tests CLI de 's1mone discover run/runs' (exécution réelle sandboxée par Firejail)."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from cli.main import app
from core.app_install import install_dir_for

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


@pytest.fixture(autouse=True)
def fake_firejail(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/firejail" if name == "firejail" else None)


@pytest.fixture
def installed_app():
    dest = install_dir_for("npm", "is-odd")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.js").write_text("console.log('ok');\n")
    return dest


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_discover_run_asks_for_confirmation_by_default(installed_app):
    result = runner.invoke(app, ["discover", "run", "npm", "is-odd", "node", "index.js"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout


def test_discover_run_with_yes_executes_and_shows_output(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    result = runner.invoke(app, ["discover", "run", "npm", "is-odd", "node", "index.js", "--yes"])
    assert result.exit_code == 0, result.output
    assert "réussie" in result.stdout
    assert "ok" in result.stdout


def test_discover_run_rejects_app_not_installed():
    result = runner.invoke(app, ["discover", "run", "npm", "jamais-installe", "node", "index.js", "--yes"])
    assert result.exit_code == 1
    assert "n'est pas installé" in result.stdout


def test_discover_run_rejects_unknown_runner(installed_app):
    result = runner.invoke(app, ["discover", "run", "npm", "is-odd", "bash", "index.js", "--yes"])
    assert result.exit_code == 1
    assert "Interpréteur inconnu" in result.stdout


def test_discover_run_without_firejail_is_refused(installed_app, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = runner.invoke(app, ["discover", "run", "npm", "is-odd", "node", "index.js", "--yes"])
    assert result.exit_code == 1
    assert "Firejail n'est pas installé" in result.stdout


def test_discover_runs_lists_history(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    runner.invoke(app, ["discover", "run", "npm", "is-odd", "node", "index.js", "--yes"])
    result = runner.invoke(app, ["discover", "runs"])
    assert result.exit_code == 0
    assert "is-odd" in result.stdout


def test_discover_runs_empty_by_default():
    result = runner.invoke(app, ["discover", "runs"])
    assert result.exit_code == 0
    assert "Aucune exécution" in result.stdout
