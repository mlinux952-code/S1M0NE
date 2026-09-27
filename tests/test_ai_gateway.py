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


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """converse() (Phase 7) lit/écrit la mémoire persistante en SQLite : on isole la base pour
    ne pas polluer les données réelles ni faire dépendre un test d'un précédent."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


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

    def __init__(
        self,
        configured: bool = True,
        reply: str = "réponse factice",
        raise_error: str | None = None,
    ) -> None:
        self._configured = configured
        self._reply = reply
        self._raise_error = raise_error
        self.received_messages: list[ChatMessage] = []

    def is_configured(self) -> bool:
        return self._configured

    def setup_hint(self) -> str:
        return "Configure le fournisseur factice (test uniquement)."

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        self.received_messages = messages
        if self._raise_error:
            raise ProviderError(self._raise_error)
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


# --- converse() : mémoire persistante (Phase 7) -------------------------------------------------


def test_converse_injects_system_prompt_describing_s1mone(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("salut", provider="fake"))

    assert fake.received_messages[0].role == "system"
    assert "S1M0NE" in fake.received_messages[0].content
    assert fake.received_messages[-1] == ChatMessage(role="user", content="salut")


def test_converse_remembers_across_calls(monkeypatch):
    fake = _FakeProvider(reply="je me souviens")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("je m'appelle Omrane", provider="fake"))
    asyncio.run(gateway_module.converse("comment je m'appelle ?", provider="fake"))

    # Le 2e appel doit recevoir tout l'historique : système + tour 1 (user+assistant) + tour 2 (user)
    contents = [m.content for m in fake.received_messages]
    assert "je m'appelle Omrane" in contents
    assert "je me souviens" in contents
    assert "comment je m'appelle ?" in contents


def test_converse_reset_clears_previous_history(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("premier message", provider="fake"))
    asyncio.run(gateway_module.converse("deuxième message", provider="fake", reset=True))

    contents = [m.content for m in fake.received_messages]
    assert "premier message" not in contents
    assert "deuxième message" in contents


def test_converse_no_memory_never_reads_or_writes_history(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("message oublié", provider="fake", use_memory=False))
    asyncio.run(gateway_module.converse("message suivant", provider="fake", use_memory=False))

    # Rien n'a été persisté : le 2e appel ne voit que le message système + son propre message.
    assert len(fake.received_messages) == 2
    assert gateway_module.get_conversation_history() == []


def test_reset_conversation_and_get_conversation_history(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("bonjour", provider="fake"))
    history = gateway_module.get_conversation_history()
    assert [m.content for m in history] == ["bonjour", "ok"]

    gateway_module.reset_conversation()
    assert gateway_module.get_conversation_history() == []


def test_converse_trims_history_beyond_max_length(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})
    monkeypatch.setattr(gateway_module, "MAX_HISTORY_MESSAGES", 4)

    for i in range(5):
        asyncio.run(gateway_module.converse(f"message {i}", provider="fake"))

    history = gateway_module.get_conversation_history()
    assert len(history) == 4  # borné, pas 10 (5 tours x 2 messages)
    assert history[-1].content == "ok"


# --- check_provider / check_all_providers (NEXT_STEPS.md §A.4) ---------------------------------


def test_check_provider_not_configured_does_not_call_api(monkeypatch):
    fake = _FakeProvider(configured=False)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    result = asyncio.run(gateway_module.check_provider("fake"))
    assert result == {
        "provider": "fake",
        "configured": False,
        "model": None,
        "ok": False,
        "detail": "Configure le fournisseur factice (test uniquement).",
    }
    assert fake.received_messages == []  # aucun appel réseau tenté


def test_check_provider_success(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    result = asyncio.run(gateway_module.check_provider("fake"))

    assert result["provider"] == "fake"
    assert result["configured"] is True
    assert result["model"] == "fake-model"
    assert result["ok"] is True
    assert "correctement" in result["detail"]
    # Vérifie qu'un vrai message minimal a été envoyé (pas juste un ping local).
    assert len(fake.received_messages) == 1
    assert fake.received_messages[0].role == "user"


def test_check_provider_reports_provider_error_without_raising(monkeypatch):
    fake = _FakeProvider(raise_error="Modèle introuvable (404) : retiré du catalogue gratuit.")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    result = asyncio.run(gateway_module.check_provider("fake"))
    assert result["ok"] is False
    assert result["configured"] is True
    assert "retiré du catalogue" in result["detail"]


def test_check_provider_uses_configured_model_override(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})
    monkeypatch.setattr(gateway_module.settings, "ai_provider_model", lambda name: "custom-model")

    result = asyncio.run(gateway_module.check_provider("fake"))
    assert result["model"] == "custom-model"


def test_check_all_providers_checks_every_registered_provider(monkeypatch):
    ok_provider = _FakeProvider(reply="ok")
    ok_provider.name = "ok-one"
    broken_provider = _FakeProvider(raise_error="cassé")
    broken_provider.name = "broken-one"
    unconfigured = _FakeProvider(configured=False)
    unconfigured.name = "unconfigured-one"
    monkeypatch.setattr(
        gateway_module,
        "_PROVIDERS",
        {"ok-one": ok_provider, "broken-one": broken_provider, "unconfigured-one": unconfigured},
    )

    results = asyncio.run(gateway_module.check_all_providers())
    by_name = {r["provider"]: r for r in results}
    assert by_name["ok-one"]["ok"] is True
    assert by_name["broken-one"]["ok"] is False
    assert by_name["unconfigured-one"]["configured"] is False


# --- Conversation scopée par projet (NEXT_STEPS.md §B.4) ----------------------------------------


def test_converse_with_unknown_project_raises_clear_error(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})
    with pytest.raises(ValueError, match="Projet inconnu"):
        asyncio.run(gateway_module.converse("salut", provider="fake", project_id="id-inexistant"))


def test_converse_project_scoped_history_is_isolated_from_global(monkeypatch):
    from core import projects

    project_id = projects.create_project("Projet Test")
    fake = _FakeProvider(reply="réponse projet")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("dans le projet", provider="fake", project_id=project_id))
    asyncio.run(gateway_module.converse("hors projet", provider="fake"))

    project_history = gateway_module.get_conversation_history(project_id=project_id)
    global_history = gateway_module.get_conversation_history()

    assert [m.content for m in project_history] == ["dans le projet", "réponse projet"]
    assert [m.content for m in global_history] == ["hors projet", "réponse projet"]


def test_converse_project_scoped_isolated_between_two_projects(monkeypatch):
    from core import projects

    p1 = projects.create_project("P1")
    p2 = projects.create_project("P2")
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("message p1", provider="fake", project_id=p1))
    history_p2 = gateway_module.get_conversation_history(project_id=p2)
    assert history_p2 == []


def test_reset_conversation_with_project_id_only_clears_that_project(monkeypatch):
    from core import projects

    project_id = projects.create_project("À réinitialiser")
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("msg", provider="fake", project_id=project_id))
    asyncio.run(gateway_module.converse("msg global", provider="fake"))

    gateway_module.reset_conversation(project_id=project_id)

    assert gateway_module.get_conversation_history(project_id=project_id) == []
    assert len(gateway_module.get_conversation_history()) == 2


# --- Mode agentique (NEXT_STEPS §B.2) -----------------------------------------------------------


class _FakeAgentProvider(AIProvider):
    """Fournisseur factice qui supporte chat_with_tools() : rejoue une séquence de réponses
    scriptées (une par appel), pour tester la boucle d'appel d'outils de ai/gateway.py sans
    dépendre d'un vrai fournisseur ni d'un vrai modèle."""

    name = "fake-agent"
    description = "Fournisseur factice agentique (test uniquement)."
    default_model = "fake-agent-model"
    supports_tools = True

    def __init__(self, scripted_responses, configured: bool = True) -> None:
        self._responses = list(scripted_responses)
        self._configured = configured
        self.calls: list[list] = []

    def is_configured(self) -> bool:
        return self._configured

    def setup_hint(self) -> str:
        return "Configure le fournisseur factice agentique (test uniquement)."

    async def chat(self, messages, model=None) -> str:
        raise NotImplementedError

    async def chat_with_tools(self, messages, tools, model=None):
        self.calls.append(list(messages))
        return self._responses.pop(0)


def test_chat_with_tools_no_tool_call_returns_final_reply_immediately(monkeypatch):
    from ai.base import ToolCall  # noqa: F401  (import vérifie juste la dispo pour ce module)

    fake = _FakeAgentProvider([ChatMessage(role="assistant", content="  Bonjour !  ")])
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    outcome = asyncio.run(gateway_module.converse("salut", provider="fake-agent", agent=True))
    assert outcome["reply"] == "Bonjour !"
    assert outcome["tool_calls"] == []
    assert len(fake.calls) == 1


def test_agent_mode_executes_tool_call_then_returns_final_reply(monkeypatch):
    from ai.base import ToolCall

    async def fake_search_all(query, limit_per_source=10, sources=None):
        return {"results": [{"name": "s1mone"}], "errors": {}}

    import connectors.engine as engine_module

    monkeypatch.setattr(engine_module, "search_all", fake_search_all)

    responses = [
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="call-1", name="search", arguments={"query": "s1mone"})],
        ),
        ChatMessage(role="assistant", content="J'ai trouvé s1mone."),
    ]
    fake = _FakeAgentProvider(responses)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    outcome = asyncio.run(
        gateway_module.converse("cherche s1mone", provider="fake-agent", agent=True)
    )
    assert outcome["reply"] == "J'ai trouvé s1mone."
    assert len(outcome["tool_calls"]) == 1
    assert outcome["tool_calls"][0]["name"] == "search"
    assert outcome["tool_calls"][0]["result"]["results"] == [{"name": "s1mone"}]
    # Deuxième appel au fournisseur : la conversation doit contenir le message tool avec le
    # résultat, pour que le modèle puisse s'en servir.
    second_call_messages = fake.calls[1]
    assert any(m.role == "tool" and m.tool_call_id == "call-1" for m in second_call_messages)


def test_agent_mode_stops_after_max_rounds_without_fabricating_an_answer(monkeypatch):
    from ai.base import ToolCall

    async def fake_search_all(query, limit_per_source=10, sources=None):
        return {"results": [], "errors": {}}

    import connectors.engine as engine_module

    monkeypatch.setattr(engine_module, "search_all", fake_search_all)

    # Le modèle rappelle toujours un outil, jamais de réponse finale : la boucle doit s'arrêter
    # honnêtement à AGENT_MAX_TOOL_ROUNDS plutôt que de tourner indéfiniment ou d'inventer.
    always_tool_call = ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[ToolCall(id="call-x", name="search", arguments={"query": "x"})],
    )
    fake = _FakeAgentProvider([always_tool_call] * gateway_module.AGENT_MAX_TOOL_ROUNDS)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    outcome = asyncio.run(gateway_module.converse("boucle", provider="fake-agent", agent=True))
    assert "n'ai pas réussi à conclure" in outcome["reply"]
    assert len(outcome["tool_calls"]) == gateway_module.AGENT_MAX_TOOL_ROUNDS
    assert len(fake.calls) == gateway_module.AGENT_MAX_TOOL_ROUNDS


def test_agent_mode_rejects_provider_without_tool_support(monkeypatch):
    fake = _FakeProvider(reply="peu importe")  # supports_tools=False par défaut
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    with pytest.raises(ProviderError, match="ne supporte pas le mode agentique"):
        asyncio.run(gateway_module.converse("salut", provider="fake", agent=True))


def test_agent_mode_requires_configured_provider(monkeypatch):
    fake = _FakeAgentProvider([ChatMessage(role="assistant", content="ok")], configured=False)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    with pytest.raises(ProviderError, match="factice agentique"):
        asyncio.run(gateway_module.converse("salut", provider="fake-agent", agent=True))


def test_agent_mode_only_persists_final_reply_not_tool_exchanges(monkeypatch):
    from ai.base import ToolCall

    async def fake_search_all(query, limit_per_source=10, sources=None):
        return {"results": [], "errors": {}}

    import connectors.engine as engine_module

    monkeypatch.setattr(engine_module, "search_all", fake_search_all)

    responses = [
        ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="call-1", name="search", arguments={"query": "x"})],
        ),
        ChatMessage(role="assistant", content="Réponse finale."),
    ]
    fake = _FakeAgentProvider(responses)
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    asyncio.run(gateway_module.converse("cherche x", provider="fake-agent", agent=True))
    history = gateway_module.get_conversation_history()
    assert [m.content for m in history] == ["cherche x", "Réponse finale."]
    assert all(m.tool_calls is None for m in history)


def test_agent_system_prompt_mentions_read_only_tools(monkeypatch):
    fake = _FakeAgentProvider([ChatMessage(role="assistant", content="ok")])
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake-agent": fake})

    asyncio.run(gateway_module.converse("salut", provider="fake-agent", agent=True))
    system_message = fake.calls[0][0]
    assert system_message.role == "system"
    assert "LECTURE SEULE" in system_message.content


def test_non_agent_mode_never_sends_agent_system_suffix(monkeypatch):
    fake = _FakeProvider(reply="ok")
    monkeypatch.setattr(gateway_module, "_PROVIDERS", {"fake": fake})

    asyncio.run(gateway_module.converse("salut", provider="fake", agent=False))
    system_message = fake.received_messages[0]
    assert "Mode agentique activé" not in system_message.content


# --- chat_with_tools() par fournisseur (aucun appel réseau réel, httpx.MockTransport) -----------


def test_groq_chat_with_tools_parses_tool_call(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    response_json = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-abc",
                            "type": "function",
                            "function": {"name": "search", "arguments": '{"query": "flask"}'},
                        }
                    ],
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        import json as _json

        payload = _json.loads(body)
        assert payload["tools"][0]["function"]["name"] == "search"
        return httpx.Response(200, json=response_json)

    from ai.providers.groq import GroqProvider

    provider = GroqProvider(client=_mock_client(handler))
    from core.agent_tools import TOOL_SCHEMAS

    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="cherche flask")], TOOL_SCHEMAS)
    )
    assert result.role == "assistant"
    assert result.tool_calls is not None
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "flask"}


def test_groq_chat_with_tools_malformed_arguments_never_raises(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    response_json = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-abc",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{pas du json valide"},
                        }
                    ],
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    from ai.providers.groq import GroqProvider
    from core.agent_tools import TOOL_SCHEMAS

    provider = GroqProvider(client=_mock_client(handler))
    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="x")], TOOL_SCHEMAS)
    )
    assert "_error" in result.tool_calls[0].arguments


def test_groq_chat_with_tools_no_tool_call_returns_plain_content(monkeypatch):
    import ai.providers.groq as groq_module

    monkeypatch.setattr(groq_module.settings, "get_secret", lambda name, default=None: "fake-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=OPENAI_STYLE_SUCCESS)

    from ai.providers.groq import GroqProvider
    from core.agent_tools import TOOL_SCHEMAS

    provider = GroqProvider(client=_mock_client(handler))
    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="salut")], TOOL_SCHEMAS)
    )
    assert result.tool_calls is None
    assert result.content.strip() == "Bonjour ! Je vais bien."


def test_openrouter_chat_with_tools_parses_tool_call(monkeypatch):
    import ai.providers.openrouter as or_module

    monkeypatch.setattr(or_module.settings, "get_secret", lambda name, default=None: "fake-key")

    response_json = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "run_command", "arguments": '{"command": "pwd"}'},
                        }
                    ],
                }
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    from ai.providers.openrouter import OpenRouterProvider
    from core.agent_tools import TOOL_SCHEMAS

    provider = OpenRouterProvider(client=_mock_client(handler))
    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="où suis-je ?")], TOOL_SCHEMAS)
    )
    assert result.tool_calls[0].name == "run_command"
    assert result.tool_calls[0].arguments == {"command": "pwd"}


def test_ollama_chat_with_tools_parses_native_dict_arguments(monkeypatch):
    response_json = {
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"function": {"name": "search", "arguments": {"query": "ollama"}}}],
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    from ai.providers.ollama import OllamaProvider
    from core.agent_tools import TOOL_SCHEMAS

    provider = OllamaProvider(client=_mock_client(handler))
    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="cherche ollama")], TOOL_SCHEMAS)
    )
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"query": "ollama"}
    assert result.tool_calls[0].id  # un id local a été généré, même si Ollama n'en fournit pas


def test_ollama_chat_with_tools_no_tool_call_returns_plain_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "Bonjour !"}})

    from ai.providers.ollama import OllamaProvider
    from core.agent_tools import TOOL_SCHEMAS

    provider = OllamaProvider(client=_mock_client(handler))
    result = asyncio.run(
        provider.chat_with_tools([ChatMessage(role="user", content="salut")], TOOL_SCHEMAS)
    )
    assert result.tool_calls is None
    assert result.content == "Bonjour !"


def test_all_three_providers_declare_supports_tools_true():
    assert GroqProvider.supports_tools is True
    assert OpenRouterProvider.supports_tools is True
    assert OllamaProvider.supports_tools is True
