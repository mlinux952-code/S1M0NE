"""core/url_check.py — Surveillance de disponibilité d'URL (Catégorie F : recherche large,
inspirée des outils d'uptime monitoring self-hosted, mais réduite au strict nécessaire).

Principe : se programme comme n'importe quel type de tâche existant, via le scheduler déjà en
place (NEXT_STEPS.md §B.1) — aucune nouvelle infrastructure de planification, aucune nouvelle
dépendance (httpx est déjà utilisé par les connecteurs, Phase 5).

Ne notifie qu'un CHANGEMENT d'état (accessible -> injoignable, ou l'inverse), jamais à chaque
vérification réussie répétée : sinon un check toutes les 5 minutes noierait les notifications en
quelques heures (mega-prompt : rien d'inutilement bruyant). L'état précédent est stocké en
mémoire persistante (core.memory), pas dans une nouvelle table — réutilise ce qui existe déjà.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from core import memory, notifications
from core.logging_setup import get_logger

logger = get_logger("s1mone.url_check")


def _state_key(url: str) -> str:
    return f"url_check:{url}"


async def check_url(
    url: str,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Vérifie qu'`url` répond avec un code < 400. Retourne un dict décrivant le résultat,
    et notifie SEULEMENT si l'état a changé depuis la dernière vérification.

    `client` est injectable pour les tests (httpx.MockTransport), même pattern que les
    connecteurs de recherche (connectors/npm.py etc., Phase 5) — aucun appel réseau réel en test.
    """
    if not url:
        raise ValueError("Paramètre requis manquant : 'url'.")

    state_key = _state_key(url)
    previous = memory.recall("persistent", state_key, default=None)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    started = time.time()
    status_code: int | None = None
    error: str | None = None
    try:
        try:
            response = await active_client.get(url)
            status_code = response.status_code
            up = status_code < 400
        except Exception as exc:  # noqa: BLE001 - toute erreur réseau = site injoignable
            up = False
            error = str(exc)
    finally:
        if owns_client:
            await active_client.aclose()
    elapsed_ms = int((time.time() - started) * 1000)

    if previous is not None and previous.get("up") != up:
        if up:
            notifications.notify(f"De nouveau accessible : {url}", level="success")
        else:
            detail = f" ({error})" if error else f" (code {status_code})"
            notifications.notify(f"Injoignable : {url}{detail}", level="error")
        logger.info(f"Changement d'état détecté pour {url} : up={up}")

    memory.remember("persistent", state_key, {"up": up, "checked_at": time.time()})

    return {
        "url": url,
        "up": up,
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "error": error,
        "state_changed": previous is not None and previous.get("up") != up,
    }
