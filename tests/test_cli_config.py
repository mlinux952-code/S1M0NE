"""Tests de la CLI 's1mone config show' (Catégorie E, post-NEXT_STEPS.md)."""

from __future__ import annotations

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_config_show_runs_and_lists_sections():
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "security" in result.stdout
    assert "cli_permission_level" in result.stdout


def test_config_show_lists_active_env_keys(monkeypatch, tmp_path):
    secret_file = tmp_path / ".env"
    secret_file.write_text("GITHUB_TOKEN=abcd1234superSecret\n", encoding="utf-8")
    from core.config import load_settings

    monkeypatch.setattr("cli.main.settings", load_settings(env_path=secret_file))

    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "GITHUB_TOKEN" in result.stdout
    assert "abcd1234superSecret" not in result.stdout
