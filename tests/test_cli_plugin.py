"""Tests de la CLI 's1mone plugin list' (Phase 8)."""

from __future__ import annotations

import textwrap

from typer.testing import CliRunner

from cli.main import app
from plugins import manager as plugin_manager

runner = CliRunner()


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path / "plugins"))
    (tmp_path / "plugins").mkdir()
    plugin_manager.reset_plugin_manager()


def test_plugin_list_empty(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "Aucun plugin chargé" in result.stdout
    assert "npm" in result.stdout  # connecteurs intégrés listés même sans plugin
    plugin_manager.reset_plugin_manager()


def test_plugin_list_shows_local_plugin(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "plugins" / "demo.py").write_text(
        textwrap.dedent(
            """
            from plugins.manager import hookimpl

            @hookimpl
            def s1mone_task_handlers():
                return {"demo": lambda p: p}
            """
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["plugin", "list"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert "fichier local" in result.stdout
    plugin_manager.reset_plugin_manager()
