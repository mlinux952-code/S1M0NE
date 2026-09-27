"""Tests du Web Gateway - endpoints de chat IA (Phase 6 - AI Gateway)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app_module
from ai.base import ProviderError
from web.app import app

client = TestClient(app)


async def _fake_ai_chat(messages, provider=None, model=None):
    return {"provider": provider or "groq", "model": "fake-model", "reply": "réponse factice"}


async def _fake_ai_chat_error(messages, provider=None, model=None):
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
    monkeypatch.setattr(web_app_module, "ai_chat", _fake_ai_chat)
    r = client.post("/api/chat", json={"message": "salut"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "réponse factice"


def test_api_chat_forwards_history(monkeypatch):
    captured = {}

    async def spy(messages, provider=None, model=None):
        captured["messages"] = messages
        return {"provider": "groq", "model": "m", "reply": "ok"}

    monkeypatch.setattr(web_app_module, "ai_chat", spy)
    r = client.post(
        "/api/chat",
        json={
            "message": "et toi ?",
            "history": [{"role": "user", "content": "salut"}, {"role": "assistant", "content": "bonjour"}],
        },
    )
    assert r.status_code == 200
    assert len(captured["messages"]) == 3
    assert captured["messages"][-1].content == "et toi ?"


def test_api_chat_empty_message_returns_400():
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 400


def test_api_chat_provider_error_returns_502_with_clear_detail(monkeypatch):
    monkeypatch.setattr(web_app_module, "ai_chat", _fake_ai_chat_error)
    r = client.post("/api/chat", json={"message": "salut"})
    assert r.status_code == 502
    assert "non configuré" in r.json()["detail"]
