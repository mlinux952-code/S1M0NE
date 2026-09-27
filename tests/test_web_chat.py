"""Tests du Web Gateway - endpoints de chat IA (Phase 6 - AI Gateway, Phase 7 - Mémoire)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import web.app as web_app_module
from ai.base import ProviderError
from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """/api/chat s'appuie sur ai.gateway.converse(), qui lit/écrit la mémoire persistante en
    SQLite : on isole la base pour ne pas polluer les données réelles du projet."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


async def _fake_ai_converse(
    message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False
):
    return {"provider": provider or "groq", "model": "fake-model", "reply": "réponse factice"}


async def _fake_ai_converse_error(
    message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False
):
    raise ProviderError("Fournisseur non configuré (test).")


def test_chat_page_loads_and_lists_providers():
    r = client.get("/chat")
    assert r.status_code == 200
    assert "groq" in r.text
    assert "ollama" in r.text


def test_api_chat_providers_lists_three_providers():
    r = client.get("/api/chat/providers")
    assert r.status_code == 200
    names = {p["name"] for p in r.json()["providers"]}
    assert names == {"groq", "openrouter", "ollama"}


def test_api_chat_returns_reply(monkeypatch):
    monkeypatch.setattr(web_app_module, "ai_converse", _fake_ai_converse)
    r = client.post("/api/chat", json={"message": "salut"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "réponse factice"


def test_api_chat_forwards_reset_flag(monkeypatch):
    captured = {}

    async def spy(message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False):
        captured["reset"] = reset
        return {"provider": "groq", "model": "m", "reply": "ok"}

    monkeypatch.setattr(web_app_module, "ai_converse", spy)
    r = client.post("/api/chat", json={"message": "nouveau départ", "reset": True})
    assert r.status_code == 200
    assert captured["reset"] is True


def test_api_chat_empty_message_returns_400():
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_api_chat_provider_error_returns_502_with_clear_detail(monkeypatch):
    monkeypatch.setattr(web_app_module, "ai_converse", _fake_ai_converse_error)
    r = client.post("/api/chat", json={"message": "salut"})
    assert r.status_code == 502
    assert "non configuré" in r.json()["detail"]


def test_api_chat_history_reflects_real_persisted_conversation():
    # Pas de mock de ai_converse ici : on vérifie l'intégration réelle avec ai.gateway (mémoire
    # persistante), pas juste que la route existe. Seul le fournisseur IA lui-même est factice.
    import ai.gateway as gateway_module

    class _FakeProvider:
        name = "fake"
        description = "test"
        default_model = "fake-model"

        def is_configured(self):
            return True

        def setup_hint(self):
            return ""

        async def chat(self, messages, model=None):
            return "réponse du fournisseur factice"

    original_providers = dict(gateway_module._PROVIDERS)
    gateway_module._PROVIDERS = {"fake": _FakeProvider()}
    try:
        r1 = client.get("/api/chat/history")
        assert r1.json()["messages"] == []

        r2 = client.post("/api/chat", json={"message": "salut", "provider": "fake"})
        assert r2.status_code == 200

        r3 = client.get("/api/chat/history")
        contents = [m["content"] for m in r3.json()["messages"]]
        assert "salut" in contents
        assert "réponse du fournisseur factice" in contents

        r4 = client.post("/api/chat/reset")
        assert r4.status_code == 200
        r5 = client.get("/api/chat/history")
        assert r5.json()["messages"] == []
    finally:
        gateway_module._PROVIDERS = original_providers


def test_api_projects_list_empty_by_default(tmp_path, monkeypatch):
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == {"projects": []}


def test_api_chat_project_scoped_conversation_is_isolated():
    from core import projects as projects_module
    import ai.gateway as gateway_module

    class _FakeProvider:
        name = "fake"
        description = "test"
        default_model = "fake-model"

        def is_configured(self):
            return True

        def setup_hint(self):
            return ""

        async def chat(self, messages, model=None):
            return "réponse projet"

    project_id = projects_module.create_project("Projet Web")
    original_providers = dict(gateway_module._PROVIDERS)
    gateway_module._PROVIDERS = {"fake": _FakeProvider()}
    try:
        r = client.post(
            "/api/chat",
            json={"message": "salut projet", "provider": "fake", "project_id": project_id},
        )
        assert r.status_code == 200

        global_history = client.get("/api/chat/history").json()["messages"]
        assert global_history == []

        project_history = client.get(
            "/api/chat/history", params={"project_id": project_id}
        ).json()["messages"]
        assert any(m["content"] == "salut projet" for m in project_history)
    finally:
        gateway_module._PROVIDERS = original_providers


def test_api_chat_unknown_project_returns_400():
    r = client.post("/api/chat", json={"message": "salut", "project_id": "id-inconnu"})
    assert r.status_code == 400


def test_api_chat_forwards_agent_flag(monkeypatch):
    captured = {}

    async def spy(message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False):
        captured["agent"] = agent
        return {"provider": "groq", "model": "m", "reply": "ok", "tool_calls": []}

    monkeypatch.setattr(web_app_module, "ai_converse", spy)
    r = client.post("/api/chat", json={"message": "cherche s1mone", "agent": True})
    assert r.status_code == 200
    assert captured["agent"] is True


def test_api_chat_agent_defaults_to_false(monkeypatch):
    captured = {}

    async def spy(message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False):
        captured["agent"] = agent
        return {"provider": "groq", "model": "m", "reply": "ok"}

    monkeypatch.setattr(web_app_module, "ai_converse", spy)
    r = client.post("/api/chat", json={"message": "salut"})
    assert r.status_code == 200
    assert captured["agent"] is False


def test_api_chat_returns_tool_calls_when_agent_mode_used(monkeypatch):
    async def spy(message, provider=None, model=None, reset=False, use_memory=True, project_id=None, agent=False):
        return {
            "provider": "groq",
            "model": "m",
            "reply": "voilà",
            "tool_calls": [{"name": "search", "arguments": {"query": "x"}, "result": {"results": []}}],
        }

    monkeypatch.setattr(web_app_module, "ai_converse", spy)
    r = client.post("/api/chat", json={"message": "cherche x", "agent": True})
    assert r.status_code == 200
    body = r.json()
    assert body["tool_calls"][0]["name"] == "search"
