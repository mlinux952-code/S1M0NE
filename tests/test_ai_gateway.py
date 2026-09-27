"""Tests de l'AI Gateway (Phase 6) : providers Groq/OpenRouter/Ollama + orchestrateur.

Aucun appel réseau réel, aucune clé API requise (httpx.MockTransport, même pattern que les
connecteurs de recherche en Phase 5 — voir tests/test_connectors.py).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import ai.gateway as gateway_module
from ai.base import AIProvider, ChatMessage, ProviderError
from ai.providers.groq import GroqProvider
from ai.providers.ollama import OllamaProvider
from ai.providers.openrouter import OpenRouterProvider


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


OPENAI_STYLE_SUCCESS = {"choices": [{"message": {"content": "  Bonjour ! Je vais bien.  "}}]}


# --- GroqProvider -----------------------------------------------------------------------------


def test_groq_not_configured_without_key(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: None)
    provider = GroqProvider()
    assert provider.is_configured() is False
    assert "console.groq.com" in provider.setup_hint()


def test_groq_chat_raises_clear_error_without_key(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: None)
    provider = GroqProvider()
    with pytest.raises(ProviderError, match="non configuré"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="salut")]))


def test_groq_chat_success(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer fake-key"
        return httpx.Response(200, json=OPENAI_STYLE_SUCCESS)

    provider = GroqProvider(client=_mock_client(handler))
    reply = asyncio.run(provider.chat([ChatMessage(role="user", content="ça va ?")]))
    assert reply == "Bonjour ! Je vais bien."


def test_groq_chat_401_raises_clear_error(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "bad-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    provider = GroqProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="refusée"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="salut")]))


def test_groq_chat_429_raises_quota_error(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    provider = GroqProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="Quota gratuit"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="salut")]))


def test_groq_chat_404_model_gone_gives_actionable_error(monkeypatch):
    """Bug réel signalé par l'utilisateur (sept. 2026) : Groq a fait passer llama-3.3-70b-versatile
    en accès Enterprise, une clé développeur gratuite reçoit un 404 dessus. Le message doit dire
    où trouver le catalogue à jour, pas juste planter."""
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})

    provider = GroqProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="console.groq.com/docs/models"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="salut")]))


def test_groq_chat_unexpected_format_never_hallucinates(monkeypatch):
    """Anti-hallucination : une réponse mal formée doit lever une erreur explicite, jamais un
    texte inventé (même règle que les connecteurs de recherche, Phase 5)."""
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = GroqProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="inattendue"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="salut")]))


# --- OpenRouterProvider -------------------------------------------------------------------------


def test_openrouter_chat_success(monkeypatch):
    import ai.providers.openrouter as or_module

    monkeypatch.setattr(or_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=OPENAI_STYLE_SUCCESS)

    provider = OpenRouterProvider(client=_mock_client(handler))
    reply = asyncio.run(provider.chat([ChatMessage(role="user", content="hello")]))
    assert reply == "Bonjour ! Je vais bien."


def test_openrouter_free_model_gone_gives_actionable_error(monkeypatch):
    """Le catalogue ':free' d'OpenRouter change souvent (vérifié en recherche, sept. 2026) :
    un modèle disparu doit donner un message actionnable, pas un crash générique."""
    import ai.providers.openrouter as or_module

    monkeypatch.setattr(or_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    provider = OpenRouterProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="openrouter.ai/models"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="hello")]))


# --- OllamaProvider ------------------------------------------------------------------------------


def test_ollama_is_always_considered_configured():
    # Pas de clé à vérifier : la vraie vérification se fait à l'appel (voir docstring du module).
    assert OllamaProvider().is_configured() is True


def test_ollama_chat_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "  Salut !  "}})

    provider = OllamaProvider(client=_mock_client(handler))
    reply = asyncio.run(provider.chat([ChatMessage(role="user", content="hello")]))
    assert reply == "Salut !"


def test_ollama_connect_error_gives_install_instructions():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider(client=_mock_client(handler))
    with pytest.raises(ProviderError, match="ollama.com"):
        asyncio.run(provider.chat([ChatMessage(role="user", content="hello")]))


# --- Gateway (orchestrateur) ---------------------------------------------------------------------


class _FakeProvider(AIProvider):
    name = "fake"
    description = "Fournisseur factice pour les tests."
    default_model = "fake-model"

    def __init__(self, configured: bool = True, reply: str = "réponse factice") -> None:
        self._configured = configured
        self._reply = reply
        self.received_messages: list[ChatMessage] = []

    def is_configured(self) -> bool:
        return self._configured

    def setup_hint(self) -> str:
        return "Configure le fournisseur factice (test uniquement)."

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        self.received_messages = messages
        return self._reply


def test_available_providers_lists_all_registered():
    names = {p["name"] for p in gateway_module.available_providers()}
    assert names == {"groq", "openrouter", "ollama"}


def test_resolve_provider_unknown_name_raises_clear_error():
    with pytest.raises(ProviderError, match="inconnu"):
        gateway_module.resolve_provider("ce-fournisseur-n-existe-pas")


def test_gateway_chat_uses_requested_provider(monkeypatch):
    fake = _FakeProvider(reply="ça marche")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    outcome = asyncio.run(
        gateway_module.chat([ChatMessage(role="user", content="salut")], provider="fake")
    )
    assert outcome == {"provider": "fake", "model": "fake-model", "reply": "ça marche"}


def test_gateway_chat_unconfigured_provider_raises_setup_hint(monkeypatch):
    fake = _FakeProvider(configured=False)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    with pytest.raises(ProviderError, match="factice"):
        asyncio.run(gateway_module.chat([ChatMessage(role="user", content="salut")], provider="fake"))


def test_gateway_chat_defaults_to_configured_provider(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})
    # ai_default_provider est une @property (lecture depuis .env puis config.toml) : on la
    # remplace au niveau de la classe plutôt que de l'instance (pas de setter défini).
    monkeypatch.setattr(
        type(gateway_module.settings), "ai_default_provider", property(lambda self: "fake")
    )

    outcome = asyncio.run(gateway_module.chat([ChatMessage(role="user", content="salut")]))
    assert outcome["provider"] == "fake"
