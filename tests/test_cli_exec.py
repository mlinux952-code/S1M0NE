"""Tests de la CLI 's1mone exec ...' (Phase 9 - Sécurité)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_exec_list_shows_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["exec", "list"])
    assert result.exit_code == 0
    assert "pwd" in result.stdout
    assert "rm" in result.stdout
    assert "ADMIN" in result.stdout


def test_exec_run_read_command(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["exec", "run", "pwd"])
    assert result.exit_code == 0
    assert str(tmp_path) in result.stdout


def test_exec_run_insufficient_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_CLI_PERMISSION_LEVEL", "READ")
    result = runner.invoke(app, ["exec", "run", "mkdir sous_dossier"])
    assert result.exit_code == 1
    assert "niveau" in result.stdout.lower() or "READ" in result.stdout


def test_exec_run_unknown_command(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["exec", "run", "shutdown now"])
    assert result.exit_code == 1
    assert "inconnue" in result.stdout.lower()


def test_exec_run_path_escape_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["exec", "run", "cat ../../etc/passwd"])
    assert result.exit_code == 1
    assert "hors du périmètre" in result.stdout


def test_exec_run_destructive_declined_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    result = runner.invoke(app, ["exec", "run", "rm a.txt"], input="n\n")
    assert result.exit_code == 0
    assert "Annulé" in result.stdout
    assert (tmp_path / "a.txt").exists()


def test_exec_run_destructive_confirmed_interactively(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    result = runner.invoke(app, ["exec", "run", "rm a.txt"], input="y\n")
    assert result.exit_code == 0
    assert not (tmp_path / "a.txt").exists()


def test_exec_run_destructive_with_yes_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    (tmp_path / "a.txt").write_text("x")
    result = runner.invoke(app, ["exec", "run", "rm a.txt", "--yes"])
    assert result.exit_code == 0
    assert not (tmp_path / "a.txt").exists()
