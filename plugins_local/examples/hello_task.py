"""
Exemple de plugin S1M0NE (Phase 8) : ajoute un type de tâche factice ("echo").

Pour l'activer : copie ce fichier dans plugins_local/ (le dossier parent), puis relance S1M0NE.
Vérifie avec `s1mone plugin list` puis :
    s1mone task submit echo --params '{"message": "salut"}'
"""

from __future__ import annotations

from typing import Any

from plugins.manager import hookimpl


async def _handle_echo(parameters: dict[str, Any]) -> dict[str, Any]:
    """Renvoie tel quel le message reçu — démonstration minimale d'un handler de tâche."""
    return {"echo": parameters.get("message", "")}


@hookimpl
def s1mone_task_handlers() -> dict:
    return {"echo": _handle_echo}
