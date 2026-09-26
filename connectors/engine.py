"""connectors/engine.py — Orchestrateur de recherche multi-source (Phase 5).

Principe clé : la panne ou la lenteur d'un connecteur ne doit JAMAIS empêcher les autres de
répondre (mega-prompt : robustesse, dégradation gracieuse). Chaque connecteur est exécuté en
parallèle (asyncio.gather) et ses erreurs sont capturées individuellement.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.cache import cache_get, cache_set, make_key
from core.logging_setup import get_logger
from connectors.base import Connector
from connectors.npm import NpmConnector
from connectors.huggingface import HuggingFaceConnector
from connectors.github import GitHubConnector
from connectors.gitlab import GitLabConnector
from connectors.codeberg import CodebergConnector
from connectors.pypi import PyPiConnector

logger = get_logger("s1mone.connectors")

# Registre statique des connecteurs disponibles (Phase 5, étape 5 : + PyPI en mode dégradé).
# Le prochain (Bitbucket/Gitee/SourceForge) s'ajoutera ici, testé individuellement avant
# d'être branché, comme convenu.
_CONNECTORS: dict[str, Connector] = {
    "npm": NpmConnector(),
    "huggingface": HuggingFaceConnector(),
    "github": GitHubConnector(),
    "gitlab": GitLabConnector(),
    "codeberg": CodebergConnector(),
    "pypi": PyPiConnector(),
}


def available_connectors() -> list[dict[str, str]]:
    """Liste des connecteurs enregistrés (nom + description), pour l'UI/API."""
    return [{"name": c.name, "description": c.description} for c in _CONNECTORS.values()]


@dataclass
class SourceOutcome:
    """Résultat de l'exécution d'un connecteur : soit des résultats, soit une erreur explicite."""

    source: str
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    from_cache: bool = False


async def _run_one(source_name: str, connector: Connector, query: str, limit: int) -> SourceOutcome:
    # Cache Manager (Phase 4) : évite de re-solliciter une source pour une requête identique
    # dans la fenêtre de TTL — essentiel pour les connecteurs à quota strict (GitHub : 30
    # req/min), et une simple politesse pour les autres.
    cache_key = make_key("search", source_name, query.lower(), str(limit))
    cached = cache_get(cache_key)
    if cached is not None:
        return SourceOutcome(source=source_name, results=cached, from_cache=True)

    try:
        results = await connector.search(query, limit=limit)
        result_dicts = [r.as_dict() for r in results]
        cache_set(cache_key, result_dicts, source=source_name)
        return SourceOutcome(source=source_name, results=result_dicts)
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
        return {"results": [], "errors": {}, "cache_hits": []}

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
    cache_hits: list[str] = []
    for outcome in outcomes:
        if outcome.error is not None:
            errors[outcome.source] = outcome.error
        if outcome.from_cache:
            cache_hits.append(outcome.source)
        results.extend(outcome.results)

    return {"results": results, "errors": errors, "cache_hits": cache_hits}
