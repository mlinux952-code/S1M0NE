"""tests/conftest.py — Isolation globale des plugins pour TOUTE la suite de tests.

Bug réel constaté sur la machine de l'utilisateur (pas dans le sandbox de développement) : 3
tests en échec (`test_search_all_isolates_a_failing_connector`,
`test_search_all_second_identical_call_hits_cache`,
`test_api_search_sources_lists_seven_connectors`) alors que la suite passe 441/441 ailleurs.
Cause : `connectors.engine._effective_connectors()` fusionne toujours les connecteurs des plugins
tiers (Phase 8, `plugins.manager.plugin_connectors()`), qui lit le VRAI dossier
`Settings.plugins_dir` (par défaut `plugins_local/` à la racine du projet) — sur une machine où
l'exemple `plugins_local/examples/hello_connector.py` a été copié dans `plugins_local/` pour un
essai manuel (suivant exactement les instructions du README, Phase 8), ce connecteur "hello" bien
réel s'ajoute silencieusement aux résultats de recherche de CHAQUE test, faussant les assertions
qui supposent un ensemble fermé de connecteurs. Comportement 100% correct en production (le but
même des plugins) — c'est la suite de tests qui n'était pas hermétique à l'état réel du disque.

Fixture autouse : chaque test tourne avec un `S1MONE_PLUGINS_DIR` pointé vers un dossier tmp
VIDE, quel que soit ce qui est réellement installé sur la machine qui exécute `pytest`. Un test
qui veut explicitement exercer le vrai mécanisme de plugins (`tests/test_plugins.py`,
`tests/test_plugin_example_package.py`) redéfinit sa propre valeur par-dessus (son propre
monkeypatch, appliqué après celui-ci, gagne) : cette fixture ne fait que garantir un état neutre
PAR DÉFAUT, jamais une contrainte qui empêcherait un test spécifique de tester autre chose.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_plugins_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_PLUGINS_DIR", str(tmp_path / "plugins_empty_by_default"))

    from plugins import manager as plugin_manager

    plugin_manager.reset_plugin_manager()
    yield
    plugin_manager.reset_plugin_manager()
