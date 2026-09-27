"""Tests du système de plugins tiers (Phase 8 - Pluggy)."""

from __future__ import annotations

import textwrap

import pytest

from plugins import manager as plugin_manager


@pytest.fixture(autouse=True)
def isolated_plugins(tmp_path, monkeypatch):
    """Chaque test a son propre dossier de plugins vide, et le PluginManager est rechargé pour
    ne jamais laisser un plugin d'un test précédent polluer le suivant (singleton process-wide)."""
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path))
    plugin_manager.reset_plugin_manager()
    yield tmp_path
    plugin_manager.reset_plugin_manager()


def _write_plugin(directory, filename: str, content: str) -> None:
    (directory / filename).write_text(textwrap.dedent(content), encoding="utf-8")


def test_no_plugins_by_default(isolated_plugins):
    assert plugin_manager.list_plugins() == []
    assert plugin_manager.plugin_connectors() == []
    assert plugin_manager.plugin_task_handlers() == {}


def test_local_connector_plugin_is_loaded(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "demo_connector.py",
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
        """,
    )
    plugins = plugin_manager.list_plugins()
    assert len(plugins) == 1
    assert plugins[0]["name"] == "demo_connector"
    assert plugins[0]["source"] == "fichier local"
    assert plugins[0]["hooks"] == ["s1mone_connectors"]

    connectors = plugin_manager.plugin_connectors()
    assert len(connectors) == 1
    assert connectors[0].name == "demo"


def test_local_task_handler_plugin_is_loaded(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "demo_task.py",
        """
        from plugins.manager import hookimpl

        async def _handle(parameters):
            return {"ok": True}

        @hookimpl
        def s1mone_task_handlers():
            return {"demo_task_type": _handle}
        """,
    )
    handlers = plugin_manager.plugin_task_handlers()
    assert "demo_task_type" in handlers


def test_plugin_prefixed_with_underscore_is_disabled(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "_disabled.py",
        """
        from plugins.manager import hookimpl

        @hookimpl
        def s1mone_task_handlers():
            return {"should_not_appear": lambda p: p}
        """,
    )
    assert plugin_manager.list_plugins() == []
    assert plugin_manager.plugin_task_handlers() == {}


def test_broken_plugin_does_not_crash_loading(isolated_plugins):
    _write_plugin(isolated_plugins, "broken.py", "raise RuntimeError('plugin cassé exprès')")
    # Ne doit jamais lever : le chargement capture l'erreur et continue.
    assert plugin_manager.list_plugins() == []


def test_connectors_engine_merges_plugin_connectors(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "demo_connector.py",
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
        """,
    )
    from connectors.engine import available_connectors

    names = {c["name"] for c in available_connectors()}
    assert "demo" in names
    assert "npm" in names  # les connecteurs intégrés restent présents


def test_connectors_engine_ignores_plugin_conflicting_with_builtin(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "fake_npm.py",
        """
        from connectors.base import Connector, SearchResult
        from plugins.manager import hookimpl

        class FakeNpm(Connector):
            name = "npm"
            description = "usurpation"
            async def search(self, query, limit=10):
                return [SearchResult(source="npm", name="usurpé", description="", url="")]

        @hookimpl
        def s1mone_connectors():
            return [FakeNpm()]
        """,
    )
    from connectors.engine import _effective_connectors
    from connectors.npm import NpmConnector

    merged = _effective_connectors()
    assert isinstance(merged["npm"], NpmConnector)  # le connecteur intégré n'a pas été écrasé


def test_task_registry_merges_plugin_handlers(isolated_plugins, tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))
    _write_plugin(
        isolated_plugins,
        "demo_task.py",
        """
        from plugins.manager import hookimpl

        async def _handle(parameters):
            return {"echo": parameters.get("message")}

        @hookimpl
        def s1mone_task_handlers():
            return {"demo_echo": _handle}
        """,
    )
    from tasks.registry import available_types, get_handler

    assert "demo_echo" in available_types()
    assert "sleep" in available_types()  # types intégrés toujours présents
    handler = get_handler("demo_echo")
    assert handler is not None


def test_task_registry_builtin_wins_over_plugin_conflict(isolated_plugins):
    _write_plugin(
        isolated_plugins,
        "fake_sleep.py",
        """
        from plugins.manager import hookimpl

        async def _handle(parameters):
            return {"fake": True}

        @hookimpl
        def s1mone_task_handlers():
            return {"sleep": _handle}
        """,
    )
    import asyncio

    from tasks.registry import get_handler

    handler = get_handler("sleep")
    assert handler is not None
    result = asyncio.run(handler({"seconds": 0}))
    # Le handler intégré 'sleep' répond avec 'slept_seconds', jamais 'fake' : c'est bien lui
    # qui a gagné, pas celui du plugin.
    assert "slept_seconds" in result
    assert "fake" not in result
