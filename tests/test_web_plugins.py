"""Tests de l'intégration web des plugins (Phase 8)."""

from __future__ import annotations

import textwrap

from fastapi.testclient import TestClient

from plugins import manager as plugin_manager
from web.app import app


def test_api_plugins_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path / "plugins"))
    (tmp_path / "plugins").mkdir()
    plugin_manager.reset_plugin_manager()
    with TestClient(app) as client:
        r = client.get("/api/plugins")
        assert r.status_code == 200
        body = r.json()
        assert body["plugins"] == []
        assert "npm" in body["connectors"]
        assert "sleep" in body["task_types"]
    plugin_manager.reset_plugin_manager()


def test_api_plugins_lists_local_plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path / "plugins"))
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "demo_connector.py").write_text(
        textwrap.dedent(
            """
            from connectors.base import Connector, SearchResult
            from plugins.manager import hookimpl

            class DemoConnector(Connector):
                name = "demo"
                description = "test"
                async def search(self, query, limit=10):
                    return [SearchResult(source="demo", name=query, description="", url="")]

            @hookimpl
            def s1mone_connectors():
                return [DemoConnector()]
            """
        ),
        encoding="utf-8",
    )
    plugin_manager.reset_plugin_manager()
    with TestClient(app) as client:
        r = client.get("/api/plugins")
        assert r.status_code == 200
        body = r.json()
        assert any(p["name"] == "demo_connector" for p in body["plugins"])
        assert "demo" in body["connectors"]
    plugin_manager.reset_plugin_manager()
