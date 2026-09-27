"""Tests de core/agent_tools.py — catalogue d'outils du mode agentique (NEXT_STEPS §B.2).

Priorité absolue de ces tests : prouver que le niveau de permission est bien verrouillé à READ
et ne peut être élevé par aucun moyen (arguments, configuration...), et qu'aucune commande
destructrice n'est jamais exécutable par ce chemin.
"""

from __future__ import annotations

import asyncio

import pytest

from core import agent_tools
from core.permissions import Permission


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    yield


# --- Schémas exposés au modèle ------------------------------------------------------------------


def test_tool_schemas_expose_exactly_search_and_run_command():
    assert agent_tools.tool_names() == ["search", "run_command"]


def test_tool_schemas_are_valid_openai_function_shape():
    for schema in agent_tools.TOOL_SCHEMAS:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn and "description" in fn and "parameters" in fn
        assert fn["parameters"]["type"] == "object"


# --- Verrouillage de sécurité (le plus important) -----------------------------------------------


def test_agent_shell_permission_is_hardcoded_to_read():
    assert agent_tools.AGENT_SHELL_PERMISSION == Permission.READ


def test_run_command_tool_cannot_execute_admin_level_commands():
    """Même si un modèle malveillant/halluciné demande 'rm' (niveau ADMIN, destructif), l'outil
    doit refuser AVANT toute tentative d'exécution — jamais de confirmation demandée à sa place."""
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "rm fichier.txt"}))
    assert "error" in result
    assert "ADMIN" in result["error"] or "niveau requis" in result["error"]


def test_run_command_tool_cannot_execute_write_level_commands():
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "mkdir sous_dossier"}))
    assert "error" in result


def test_run_command_tool_allows_read_level_commands(tmp_path):
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "pwd"}))
    assert "error" not in result
    assert result["returncode"] == 0


def test_run_command_tool_never_receives_confirmation_bypass(monkeypatch):
    """Vérifie que `confirmed` n'est jamais positionné à True nulle part dans le chemin de
    l'outil, même indirectement (defense in depth : le seul appelant de shell_runner ici doit
    toujours transmettre confirmed=False)."""
    captured = {}

    def spy_run_command(command, *, level, fs_root, confirmed=False, timeout=10.0):
        captured["level"] = level
        captured["confirmed"] = confirmed
        return {"command": command, "returncode": 0, "stdout": "", "stderr": "", "timed_out": False}

    monkeypatch.setattr(agent_tools, "_run_command_impl", spy_run_command)
    asyncio.run(agent_tools.execute_tool("run_command", {"command": "pwd"}))
    assert captured["level"] == Permission.READ
    assert captured["confirmed"] is False


def test_run_command_tool_path_escape_is_rejected(tmp_path):
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "cat ../../../etc/passwd"}))
    assert "error" in result


def test_run_command_tool_rejects_unknown_command():
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "shutdown now"}))
    assert "error" in result


def test_run_command_tool_missing_argument_returns_error_not_exception():
    result = asyncio.run(agent_tools.execute_tool("run_command", {}))
    assert "error" in result


# --- Outil search --------------------------------------------------------------------------------


def test_search_tool_calls_search_all_and_bounds_results(monkeypatch):
    async def fake_search_all(query, limit_per_source=10, sources=None):
        return {"results": [{"name": f"pkg-{i}"} for i in range(50)], "errors": {}}

    import connectors.engine as engine_module

    monkeypatch.setattr(engine_module, "search_all", fake_search_all)
    result = asyncio.run(agent_tools.execute_tool("search", {"query": "flask"}))
    assert "error" not in result
    assert len(result["results"]) == agent_tools.MAX_SEARCH_RESULTS_RETURNED


def test_search_tool_missing_query_returns_error():
    result = asyncio.run(agent_tools.execute_tool("search", {}))
    assert "error" in result


def test_search_tool_rejects_non_list_sources():
    result = asyncio.run(agent_tools.execute_tool("search", {"query": "flask", "sources": "github"}))
    assert "error" in result


# --- Outil inconnu / arguments malformés --------------------------------------------------------


def test_execute_tool_unknown_name_returns_error():
    result = asyncio.run(agent_tools.execute_tool("delete_everything", {}))
    assert "error" in result
    assert "inconnu" in result["error"]


def test_execute_tool_non_dict_arguments_returns_error_not_exception():
    result = asyncio.run(agent_tools.execute_tool("search", "pas un dict"))
    assert "error" in result


def test_execute_tool_never_raises_on_internal_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("panne interne simulée")

    monkeypatch.setattr(agent_tools, "_run_command_impl", boom)
    result = asyncio.run(agent_tools.execute_tool("run_command", {"command": "pwd"}))
    assert "error" in result
