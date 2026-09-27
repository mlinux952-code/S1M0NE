"""s1mone_plugin_example — plugin d'exemple distribué via pip pour S1M0NE (NEXT_STEPS.md §C.3).

Contrairement aux exemples de `plugins_local/examples/` (fichiers `.py` à copier à la main), ce
paquet démontre le second mécanisme documenté dans `plugins/hookspecs.py` : un vrai paquet pip
installé, découvert automatiquement par S1M0NE via l'entry point du groupe `"s1mone"` (voir le
`pyproject.toml` de CE paquet, section `[project.entry-points.s1mone]`) — aucune copie de
fichier, aucune configuration supplémentaire côté S1M0NE.

Installation et usage : voir README.md à côté de ce fichier.
"""

from __future__ import annotations

from typing import Any

from connectors.base import Connector, SearchResult
from plugins.manager import hookimpl


class ExamplePipConnector(Connector):
    """Connecteur de démonstration : montre qu'un paquet pip peut ajouter une source de
    recherche exactement comme un connecteur intégré (Phase 5), sans modifier une seule ligne de
    S1M0NE lui-même.

    Règle anti-hallucination du méga-prompt (§10/§25), valable aussi pour les plugins tiers : ce
    connecteur ne prétend jamais interroger une vraie source externe — le résultat renvoyé le dit
    explicitement.
    """

    name = "example-pip"
    description = "Connecteur de démonstration fourni par le paquet pip s1mone-plugin-example."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if limit <= 0:
            return []
        return [
            SearchResult(
                source=self.name,
                name=f"Résultat de démonstration pour '{query}'",
                description=(
                    "Résultat factice fourni par un vrai paquet pip installé (voir "
                    "examples/s1mone-plugin-example/ dans le dépôt S1M0NE) — jamais une vraie "
                    "donnée externe."
                ),
                url="https://example.com",
            )
        ][:limit]


async def _handle_example_echo(parameters: dict[str, Any]) -> dict[str, Any]:
    """Type de tâche de démonstration : renvoie tel quel le message reçu (aucune logique
    métier réelle — sert uniquement à prouver que le hook `s1mone_task_handlers` fonctionne
    depuis un paquet pip installé)."""
    return {"echo": parameters.get("message", "")}


@hookimpl
def s1mone_connectors() -> list[Connector]:
    return [ExamplePipConnector()]


@hookimpl
def s1mone_task_handlers() -> dict[str, Any]:
    return {"example-echo": _handle_example_echo}
