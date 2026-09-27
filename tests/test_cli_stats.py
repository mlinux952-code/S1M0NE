"""Tests de la CLI 's1mone stats' (Catégorie D, post-NEXT_STEPS.md)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    yield


def test_stats_command_runs_and_shows_sections():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "Tâches" in result.stdout
    assert "Mémoire" in result.stdout
    assert "Cache, projets, notifications, tâches récurrentes" in result.stdout


def test_stats_command_reflects_real_data():
    from core.db import create_task, init_db, mark_task_success
    from core.config import settings

    init_db(settings.db_path)
    task_id = create_task("echo", {})
    mark_task_success(task_id, {"ok": True})

    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "SUCCESS" in result.stdout
    assert "100.0 %" in result.stdout
