"""connectors/engine.py — Orchestrateur de recherche multi-source (Phase 5).

Principe clé : la panne ou la lenteur d'un connecteur ne doit JAMAIS empêcher les autres de
répondre (mega-prompt : robustesse, dégradation gracieuse). Chaque connecteur est exécuté en
parallèle (asyncio.gather) et ses erreurs sont capturées individuellement.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.logging_setup import get_logger
from connectors.base import Connector, SearchResult
from connectors.npm import NpmConnector

logger = get_logger("s1mone.connectors")

# Registre statique des connecteurs disponibles (Phase 5, étape 1 : npm uniquement).
# Les prochains (Hugging Face, GitHub, GitLab/Codeberg, PyPI...) s'ajouteront ici un par un,
# chacun testé individuellement avant d'être branché, comme convenu.
_CONNECTORS: dict[str, Connector] = {
    "npm": NpmConnector(),
}


def available_connectors() -> list[dict[str, str]]:
    """Liste des connecteurs enregistrés (nom + description), pour l'UI/API."""
    return [{"name": c.name, "description": c.description} for c in _CONNECTORS.values()]


@dataclass
class SourceOutcome:
    """Résultat de l'exécution d'un connecteur : soit des résultats, soit une erreur explicite."""

    source: str
    results: list[SearchResult] = field(default_factory=list)
    error: str | None = None


async def _run_one(source_name: str, connector: Connector, query: str, limit: int) -> SourceOutcome:
    try:
        results = await connector.search(query, limit=limit)
        return SourceOutcome(source=source_name, results=results)
    except Exception as exc:  # noqa: BLE001 - isoler la panne d'un connecteur, jamais tout casser
        logger.error(f"Connecteur '{source_name}' en échec pour la requête {query!r} : {exc}")
        return SourceOutcome(source=source_name, error=str(exc))


async def search_all(
    query: str, limit_per_source: int = 10, sources: list[str] | None = None
) -> dict[str, Any]:
    """Interroge tous les connecteurs demandés (ou tous par défaut) en parallèle.

    Retourne un dict {"results": [...], "errors": {source: message}} : jamais d'exception qui
    remonte jusqu'à l'appelant CLI/web pour une simple panne d'un connecteur.
    """
    query = query.strip()
    if not query:
        return {"results": [], "errors": {}}

    chosen = {
        name: conn
        for name, conn in _CONNECTORS.items()
        if sources is None or name in sources
    }

    outcomes = await asyncio.gather(
        *(_run_one(name, conn, query, limit_per_source) for name, conn in chosen.items())
    )

    results: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for outcome in outcomes:
        if outcome.error is not None:
            errors[outcome.source] = outcome.error
        results.extend(r.as_dict() for r in outcome.results)

    return {"results": results, "errors": errors}
