"""ai/base.py — Interface commune à tous les fournisseurs d'IA conversationnelle (Phase 6).

Décision (voir DECISIONS.md §D10, qui révise la piste "LiteLLM SDK" envisagée en Phase 0) :
un fournisseur = une petite classe qui parle directement l'API REST du service (httpx, déjà une
dépendance du projet), sur le même principe que `connectors.base.Connector` en Phase 5. On évite
ainsi d'ajouter une dépendance lourde (LiteLLM traîne des dizaines de sous-dépendances, dont
tiktoken) pour un besoin qui se résume à "POST un JSON, lire un JSON" sur 2-3 fournisseurs.

Règle anti-hallucination (mega-prompt §10/§25), déjà appliquée aux connecteurs de recherche :
si un fournisseur ne peut pas répondre (clé absente, service injoignable, erreur API), il DOIT
lever une `ProviderError` explicite — jamais fabriquer une réponse plausible à la place.

Extension NEXT_STEPS.md §B.2 (assistant agentique / appel d'outils) : `ToolCall` et les champs
`tool_calls`/`tool_call_id`/`name` de `ChatMessage` forment une représentation CANONIQUE, interne
à S1M0NE, des échanges liés aux outils (`arguments` toujours un dict Python). Chaque fournisseur
est responsable de traduire cette forme canonique vers/depuis SON propre dialecte sur le fil
(OpenAI encode les arguments en chaîne JSON, Ollama les transmet en dict natif...) — voir
`chat_with_tools()` de chaque provider. Voir DECISIONS.md D18 pour les règles de sécurité qui
encadrent l'usage de ces outils (jamais dans ce fichier : ce module ne connaît aucun outil
concret, seulement la mécanique générique de transport).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ProviderError(Exception):
    """Erreur explicite et actionnable (clé manquante, service injoignable, quota dépassé...).

    Le message doit toujours dire à l'utilisateur QUOI FAIRE (où mettre une clé, quelle commande
    lancer...), jamais juste "erreur".
    """


@dataclass
class ToolCall:
    """Un appel d'outil demandé par le modèle (NEXT_STEPS §B.2). `arguments` est toujours un
    dict Python déjà décodé, quel que soit le dialecte utilisé par le fournisseur sur le fil."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    #: Rempli uniquement sur un message role="assistant" qui demande l'exécution d'outils.
    tool_calls: list[ToolCall] | None = None
    #: Rempli uniquement sur un message role="tool" : id de l'appel auquel ce résultat répond.
    tool_call_id: str | None = None
    #: Rempli uniquement sur un message role="tool" : nom de l'outil exécuté.
    name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Représentation simple, utilisée pour la MÉMOIRE PERSISTANTE (Phase 7) et les tests —
        jamais pour parler directement à un fournisseur (chaque fournisseur a son propre
        encodage sur le fil, voir `chat_with_tools()`). Identique à l'historique
        {"role", "content"} d'avant B.2 tant qu'aucun champ tool_* n'est renseigné (aucune
        rupture de compatibilité avec la mémoire déjà persistée)."""
        result: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            result["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in self.tool_calls
            ]
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.name:
            result["name"] = self.name
        return result


class AIProvider(ABC):
    """Interface que tout fournisseur d'IA conversationnelle doit implémenter."""

    #: Identifiant court et stable (config.toml, CLI --provider, logs...).
    name: str = "base"

    #: Description humaine courte (affichée dans "s1mone chat --list-providers").
    description: str = ""

    #: Modèle utilisé si aucun n'est précisé explicitement.
    default_model: str = ""

    #: True si `chat_with_tools()` est réellement implémenté (NEXT_STEPS §B.2). Contrôlé au
    #: niveau de chaque sous-classe, jamais deviné dynamiquement.
    supports_tools: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        """True si tout ce qu'il faut (clé API, service local joignable...) est en place.

        Ne doit jamais faire d'appel réseau bloquant : une simple vérification locale (présence
        d'une variable d'environnement, etc.).
        """
        raise NotImplementedError

    @abstractmethod
    def setup_hint(self) -> str:
        """Message expliquant comment configurer ce fournisseur (où obtenir une clé gratuite,
        quelle variable mettre dans .env...). Affiché quand `is_configured()` est False."""
        raise NotImplementedError

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        """Envoie la conversation au fournisseur, retourne la réponse texte de l'assistant.

        Doit lever `ProviderError` (jamais renvoyer de texte inventé) en cas de problème réel :
        clé absente/invalide, service injoignable, réponse HTTP en erreur, quota dépassé, etc.
        """
        raise NotImplementedError

    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]], model: str | None = None
    ) -> ChatMessage:
        """Comme `chat()`, mais annonce `tools` (schémas au format OpenAI "function calling") au
        modèle et retourne le message assistant complet, y compris d'éventuels `tool_calls`
        (NEXT_STEPS §B.2). Retourne toujours role="assistant" ; `tool_calls` est None s'il n'y a
        pas d'appel d'outil demandé (réponse finale).

        Lève `ProviderError` dans les mêmes conditions que `chat()`. Un fournisseur qui n'a pas
        (encore) implémenté cette méthode lève NotImplementedError — vérifié via
        `supports_tools` par l'appelant AVANT d'appeler cette méthode (mega-prompt anti-
        hallucination : ne jamais prétendre qu'un fournisseur sait faire de l'agentique s'il ne
        le peut pas réellement)."""
        raise NotImplementedError(
            f"Le fournisseur '{self.name}' ne supporte pas encore l'appel d'outils (function "
            "calling)."
        )
