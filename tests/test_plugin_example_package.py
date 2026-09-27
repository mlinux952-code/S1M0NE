"""Tests du paquet pip d'exemple (NEXT_STEPS.md §C.3) : examples/s1mone-plugin-example/.

Deux angles :
1. La logique du plugin elle-même (connecteur + type de tâche), testée comme n'importe quel
   module Python, sans dépendre d'une vraie installation pip.
2. La découverte via un VRAI entry point du groupe "s1mone" (le second mécanisme documenté dans
   plugins/hookspecs.py, jusqu'ici jamais exercé par la suite de tests — seul le chargement de
   fichiers locaux l'était, voir tests/test_plugins.py). On simule un paquet installé SANS
   l'installer réellement dans le venv du projet : une installation permanente ferait apparaître
   "example-pip"/"example-echo" dans absolument toutes les recherches/listes de tâches de la
   suite, cassant par exemple l'assertion à liste fermée de
   tests/test_web_search.py::test_api_search_sources_lists_seven_connectors.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.metadata
import sys
from pathlib import Path

import pytest

EXAMPLE_ROOT = Path(__file__).resolve().parent.parent / "examples" / "s1mone-plugin-example"
EXAMPLE_SRC = EXAMPLE_ROOT / "src"


@pytest.fixture
def example_package_on_path():
    """Rend le paquet d'exemple importable pour la durée du test, sans l'installer (pip) ni
    laisser de trace dans sys.path/sys.modules pour les tests suivants."""
    sys.path.insert(0, str(EXAMPLE_SRC))
    sys.modules.pop("s1mone_plugin_example", None)
    try:
        yield importlib.import_module("s1mone_plugin_example")
    finally:
        sys.path.remove(str(EXAMPLE_SRC))
        sys.modules.pop("s1mone_plugin_example", None)


class _FakeDistribution:
    """Objet minimal imitant ce que `pluggy.load_setuptools_entrypoints` attend de
    `importlib.metadata.distributions()` : un `.entry_points` itérable."""

    def __init__(self, entry_points):
        self.entry_points = entry_points


# --- Le paquet existe et déclare bien un entry point du groupe "s1mone" -------------------------


def test_example_package_pyproject_declares_s1mone_entry_point():
    pyproject = (EXAMPLE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.entry-points.s1mone]" in pyproject
    assert 'example = "s1mone_plugin_example"' in pyproject


def test_example_package_readme_documents_installation():
    readme = (EXAMPLE_ROOT / "README.md").read_text(encoding="utf-8")
    assert "pip install -e examples/s1mone-plugin-example" in readme


# --- Logique du plugin, indépendamment de pluggy ------------------------------------------------


def test_example_connector_returns_labeled_demo_result(example_package_on_path):
    mod = example_package_on_path
    connector = mod.ExamplePipConnector()
    results = asyncio.run(connector.search("bonjour", limit=3))
    assert len(results) == 1
    assert "bonjour" in results[0].name
    assert connector.name == "example-pip"
    assert results[0].source == "example-pip"


def test_example_connector_respects_limit_zero(example_package_on_path):
    mod = example_package_on_path
    connector = mod.ExamplePipConnector()
    results = asyncio.run(connector.search("x", limit=0))
    assert results == []


def test_example_connector_never_claims_to_be_a_real_external_source(example_package_on_path):
    mod = example_package_on_path
    connector = mod.ExamplePipConnector()
    results = asyncio.run(connector.search("x"))
    assert "démonstration" in results[0].description or "factice" in results[0].description


def test_example_task_handler_echoes_message(example_package_on_path):
    mod = example_package_on_path
    result = asyncio.run(mod._handle_example_echo({"message": "salut"}))
    assert result == {"echo": "salut"}


def test_example_task_handler_missing_message_returns_empty_string(example_package_on_path):
    mod = example_package_on_path
    result = asyncio.run(mod._handle_example_echo({}))
    assert result == {"echo": ""}


def test_example_hooks_carry_the_pluggy_hookimpl_marker(example_package_on_path):
    mod = example_package_on_path
    assert hasattr(mod.s1mone_connectors, "s1mone_impl")
    assert hasattr(mod.s1mone_task_handlers, "s1mone_impl")


# --- Découverte via un vrai entry point pip (jamais installé dans le venv principal) -----------


def test_pluggy_discovers_the_example_package_via_a_real_entry_point(
    example_package_on_path, monkeypatch
):
    """Preuve que le mécanisme documenté dans plugins/hookspecs.py (paquet pip + entry point du
    groupe 's1mone') fonctionne réellement de bout en bout avec le vrai code du paquet
    d'exemple."""
    import pluggy

    from plugins.hookspecs import HOOK_NAMESPACE, S1moneHookSpecs

    entry_point = importlib.metadata.EntryPoint(
        name="example", value="s1mone_plugin_example", group=HOOK_NAMESPACE
    )
    monkeypatch.setattr(
        importlib.metadata, "distributions", lambda: [_FakeDistribution([entry_point])]
    )

    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.add_hookspecs(S1moneHookSpecs)
    count = pm.load_setuptools_entrypoints(HOOK_NAMESPACE)

    assert count == 1
    connectors = [c for batch in pm.hook.s1mone_connectors() for c in batch]
    assert any(c.name == "example-pip" for c in connectors)

    handlers: dict = {}
    for batch in pm.hook.s1mone_task_handlers():
        handlers.update(batch)
    assert "example-echo" in handlers


def test_plugins_manager_discovers_example_package_end_to_end(
    example_package_on_path, monkeypatch, tmp_path
):
    """Même preuve, mais via le vrai point d'entrée de S1M0NE (plugins.manager), celui utilisé
    par 's1mone plugin list', 's1mone search' et 's1mone task submit'."""
    import plugins.manager as manager_module

    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path))  # aucun plugin fichier local ici
    entry_point = importlib.metadata.EntryPoint(
        name="example", value="s1mone_plugin_example", group="s1mone"
    )
    monkeypatch.setattr(
        importlib.metadata, "distributions", lambda: [_FakeDistribution([entry_point])]
    )
    manager_module.reset_plugin_manager()
    try:
        plugins = manager_module.list_plugins()
        assert any(p["name"] == "example" and p["source"] == "paquet installé" for p in plugins)

        connectors = manager_module.plugin_connectors()
        assert any(c.name == "example-pip" for c in connectors)

        handlers = manager_module.plugin_task_handlers()
        assert "example-echo" in handlers
    finally:
        manager_module.reset_plugin_manager()
