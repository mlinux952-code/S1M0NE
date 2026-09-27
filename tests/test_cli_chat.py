"""Tests de la CLI 's1mone chat' (Phase 6 - AI Gateway, Phase 7 - Mémoire)."""

from __future__ import annotations

from typer.testing import CliRunner

import cli.main as cli_main
from ai.base import ProviderError
from cli.main import app

runner = CliRunner()


async def _fake_ai_converse(
    message, provider=None, model=None, reset=False, use_memory=True, project_id=None
):
    return {"provider": provider or "groq", "model": "fake-model", "reply": "réponse factice"}


async def _fake_ai_converse_error(
    message, provider=None, model=None, reset=False, use_memory=True, project_id=None
):
    raise ProviderError("Fournisseur non configuré (test).")


def test_chat_list_providers_shows_all_registered():
    result = runner.invoke(app, ["chat", "--list-providers"])
    assert result.exit_code == 0
    assert "groq" in result.stdout
    assert "openrouter" in result.stdout
    assert "ollama" in result.stdout


def test_chat_one_shot_message_displays_reply(monkeypatch):
    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse)
    result = runner.invoke(app, ["chat", "salut, ça va ?"])
    assert result.exit_code == 0
    assert "réponse factice" in result.stdout


def test_chat_one_shot_shows_clear_error_on_provider_failure(monkeypatch):
    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse_error)
    result = runner.invoke(app, ["chat", "salut"])
    assert result.exit_code == 1
    assert "non configuré" in result.stdout


def test_chat_interactive_exits_cleanly_on_exit_command(monkeypatch):
    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse)
    result = runner.invoke(app, ["chat"], input="exit\n")
    assert result.exit_code == 0
    assert "Fin de la conversation" in result.stdout


def test_chat_interactive_round_trip(monkeypatch):
    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse)
    result = runner.invoke(app, ["chat"], input="salut !\nexit\n")
    assert result.exit_code == 0
    assert "réponse factice" in result.stdout


def test_chat_interactive_slash_reset_calls_reset_conversation(monkeypatch):
    called = {"n": 0}

    def fake_reset(project_id=None):
        called["n"] += 1

    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse)
    monkeypatch.setattr(cli_main, "reset_conversation", fake_reset)
    result = runner.invoke(app, ["chat"], input="/reset\nexit\n")
    assert result.exit_code == 0
    assert called["n"] == 1
    assert "repart de zéro" in result.stdout


def test_chat_reset_flag_calls_reset_conversation_before_interactive_loop(monkeypatch):
    called = {"n": 0}

    def fake_reset(project_id=None):
        called["n"] += 1

    monkeypatch.setattr(cli_main, "ai_converse", _fake_ai_converse)
    monkeypatch.setattr(cli_main, "reset_conversation", fake_reset)
    result = runner.invoke(app, ["chat", "--reset"], input="exit\n")
    assert result.exit_code == 0
    assert called["n"] == 1
