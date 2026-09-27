"""ai/base.py — Interface commune à tous les fournisseurs d'IA conversationnelle (Phase 6).

Décision (voir DECISIONS.md §D10, qui révise la piste "LiteLLM SDK" envisagée en Phase 0) :
un fournisseur = une petite classe qui parle directement l'API REST du service (httpx, déjà une
dépendance du projet), sur le même principe que `connectors.base.Connector` en Phase 5. On évite
ainsi d'ajouter une dépendance lourde (LiteLLM traîne des dizaines de sous-dépendances, dont
tiktoken) pour un besoin qui se résume à "POST un JSON, lire un JSON" sur 2-3 fournisseurs.

Règle anti-hallucination (mega-prompt §10/§25), déjà appliquée aux connecteurs de recherche :
si un fournisseur ne peut pas répondre (clé absente, service injoignable, erreur API), il DOIT
lever une `ProviderError` explicite — jamais fabriquer une réponse plausible à la place.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ProviderError(Exception):
    """Erreur explicite et actionnable (clé manquante, service injoignable, quota dépassé...).

    Le message doit toujours dire à l'utilisateur QUOI FAIRE (où mettre une clé, quelle commande
    lancer...), jamais juste "erreur".
    """


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class AIProvider(ABC):
    """Interface que tout fournisseur d'IA conversationnelle doit implémenter."""

    #: Identifiant court et stable (config.toml, CLI --provider, logs...).
    name: str = "base"

    #: Description humaine courte (affichée dans "s1mone chat --list-providers").
    description: str = ""

    #: Modèle utilisé si aucun n'est précisé explicitement.
    default_model: str = ""

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
