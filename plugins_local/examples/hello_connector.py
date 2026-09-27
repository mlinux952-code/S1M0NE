"""
Exemple de plugin S1M0NE (Phase 8) : ajoute un connecteur de recherche factice.

Pour l'activer : copie ce fichier dans plugins_local/ (le dossier parent), puis relance S1M0NE.
Vérifie avec `s1mone plugin list` et `s1mone search <terme> --sources hello`.

Règle anti-hallucination du méga-prompt (§10/§25), valable aussi pour les plugins tiers : un
connecteur ne doit jamais inventer un résultat plausible. Ici, on retourne clairement un
résultat de démonstration, jamais présenté comme une vraie donnée externe.
"""

from __future__ import annotations

from connectors.base import Connector, SearchResult
from plugins.manager import hookimpl


class HelloConnector(Connector):
    name = "hello"
    description = "Connecteur de démonstration ajouté par un plugin (exemple Phase 8)."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        return [
            SearchResult(
                source=self.name,
                name=f"Résultat de démonstration pour '{query}'",
                description=(
                    "Ceci est un connecteur d'exemple (plugins_local/examples/hello_connector.py)"
                    " — copie-le et adapte-le pour interroger une vraie source."
                ),
                url="https://example.com",
            )
        ][:limit]


@hookimpl
def s1mone_connectors() -> list[Connector]:
    return [HelloConnector()]
