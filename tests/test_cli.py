"""Tests de la CLI (Phase 1, étape 4)."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_version_command_runs():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "S1M0NE" in result.stdout


def test_system_command_runs():
    result = runner.invoke(app, ["system"])
    assert result.exit_code == 0
    assert "RAM" in result.stdout or "CPU" in result.stdout


def test_status_command_runs_and_exits_zero_when_healthy(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "sqlite" in result.stdout
