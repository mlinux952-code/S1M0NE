"""connectors/base.py — Interface commune à tous les connecteurs de recherche (Phase 5).

Décision D9 (DECISIONS.md) : classe abstraite Python + découverte dynamique, sans framework de
plugin externe pour l'instant (Pluggy réévalué en Phase 8 pour les vrais plugins tiers).

Règle anti-hallucination du méga-prompt (§10/§25) : un connecteur ne DOIT JAMAIS inventer un
résultat. S'il ne peut pas répondre correctement (API indisponible, recherche non supportée...),
il doit soit renvoyer une liste vide, soit lever une exception explicite — jamais fabriquer une
donnée plausible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SearchResult:
    """Un résultat de recherche normalisé, quelle que soit sa source d'origine."""

    source: str
    name: str
    description: str = ""
    url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "extra": self.extra,
        }


class Connector(ABC):
    """Interface que tout connecteur de recherche doit implémenter."""

    #: Identifiant court et stable (utilisé dans SearchResult.source, les logs, le cache...).
    name: str = "base"

    #: Description humaine courte, affichée dans l'UI (liste des sources disponibles).
    description: str = ""

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Cherche `query` sur la source, retourne au plus `limit` résultats.

        Ne doit jamais lever pour une simple absence de résultat (retourner [] dans ce cas).
        Peut lever une exception pour une vraie erreur (réseau, API en panne...) : c'est au
        code appelant (le moteur d'orchestration) de décider comment l'afficher/logguer sans
        faire planter les autres connecteurs.
        """
        raise NotImplementedError
