"""Tests de la page web Plugins (Catégorie E, post-NEXT_STEPS.md)."""

from __future__ import annotations

import textwrap

import pytest
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_plugins_page_loads():
    r = client.get("/plugins")
    assert r.status_code == 200
    assert "Plugins" in r.text


def test_plugins_nav_link_is_enabled():
    r = client.get("/")
    assert '<a href="/plugins">Plugins</a>' in r.text
    assert "Disponible en CLI : s1mone plugin list" not in r.text


def test_partial_plugins_empty_by_default():
    r = client.get("/partials/plugins")
    assert r.status_code == 200
    assert "Aucun plugin chargé" in r.text
    assert "plugins_local" in r.text


def test_partial_plugins_shows_loaded_local_plugin(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path))
    (tmp_path / "demo_connector.py").write_text(
        textwrap.dedent(
            """
            from connectors.base import Connector, SearchResult
            from plugins.manager import hookimpl

            class DemoConnector(Connector):
                name = "demo"
                description = "connecteur de test"
                async def search(self, query, limit=10):
                    return [SearchResult(source="demo", name=query, description="", url="")]

            @hookimpl
            def s1mone_connectors():
                return [DemoConnector()]
            """
        ),
        encoding="utf-8",
    )
    from plugins import manager as plugin_manager

    plugin_manager.reset_plugin_manager()
    try:
        r = client.get("/partials/plugins")
        assert r.status_code == 200
        assert "demo_connector" in r.text
        assert "fichier local" in r.text
        assert "demo" in r.text  # apparaît aussi dans "Effet visible" (connecteurs disponibles)
    finally:
        plugin_manager.reset_plugin_manager()


def test_partial_plugins_lists_connectors_and_task_types():
    r = client.get("/partials/plugins")
    assert "npm" in r.text
    assert "sleep" in r.text  # type de tâche intégré (Phase 3)


def test_api_settings_route_still_separate_from_plugins():
    # garde-fou : /api/plugins (existant) et /plugins (nouveau) coexistent sans se marcher dessus
    r = client.get("/api/plugins")
    assert r.status_code == 200
    assert "plugins" in r.json()
