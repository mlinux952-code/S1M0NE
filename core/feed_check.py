"""core/feed_check.py — Veille RSS/Atom (Catégorie F : recherche large, inspirée des lecteurs de
flux self-hosted, réduite au strict nécessaire pour un usage personnel).

Choix (même logique que D5/D17 pour le scheduler) : parseur XML minimal via `xml.etree`
(stdlib), PAS de dépendance `feedparser` — un flux RSS 2.0 ou Atom se réduit, pour notre besoin
(détecter les nouveaux articles), à extraire id/titre/lien de chaque entrée. Un flux mal formé
dégrade gracieusement (liste vide) plutôt que de faire planter la tâche planifiée.

Se programme comme n'importe quel type de tâche via le scheduler déjà en place
(`s1mone schedule create rss_check --interval 30m --param url=... --param name=...`).
L'ensemble des identifiants déjà vus est stocké en mémoire persistante (core.memory), pas dans
une nouvelle table — réutilise ce qui existe déjà, avec une fenêtre bornée (200 ids) pour ne
jamais faire grossir la mémoire indéfiniment même sur un flux très actif.
"""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

import httpx

from core import memory, notifications
from core.logging_setup import get_logger

logger = get_logger("s1mone.feed_check")

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_MAX_KNOWN_IDS = 200


def _state_key(url: str) -> str:
    return f"rss_check:{url}"


def parse_feed_items(xml_text: str) -> list[dict[str, str]]:
    """Extrait (id, titre, lien) de chaque entrée d'un flux RSS 2.0 ou Atom.

    Retourne une liste vide si le XML est invalide ou ne ressemble à aucun des deux formats —
    jamais d'exception propagée (une tâche planifiée ne doit jamais planter sur un flux externe
    mal formé, mega-prompt : robustesse avant tout).
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    items: list[dict[str, str]] = []

    # RSS 2.0 : <rss><channel><item>...</item></channel></rss>
    for item in root.findall(".//item"):
        guid = item.findtext("guid") or item.findtext("link") or item.findtext("title")
        if not guid:
            continue
        items.append(
            {
                "id": guid.strip(),
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
            }
        )
    if items:
        return items

    # Atom : <feed xmlns="..."><entry>...</entry></feed>
    for entry in root.findall(".//atom:entry", _ATOM_NS):
        entry_id = entry.findtext("atom:id", namespaces=_ATOM_NS)
        if not entry_id:
            continue
        title = entry.findtext("atom:title", namespaces=_ATOM_NS) or ""
        link_el = entry.find("atom:link", _ATOM_NS)
        link = link_el.get("href", "") if link_el is not None else ""
        items.append({"id": entry_id.strip(), "title": title.strip(), "link": link.strip()})
    return items


async def check_feed(
    url: str,
    name: str | None = None,
    timeout: float = 15.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Récupère `url`, détecte les entrées jamais vues, notifie chacune d'elles (une notification
    par nouvel article, ordre chronologique du plus ancien au plus récent).

    `client` est injectable pour les tests (httpx.MockTransport), même pattern que les
    connecteurs de recherche (connectors/npm.py etc., Phase 5) — aucun appel réseau réel en test.
    """
    if not url:
        raise ValueError("Paramètre requis manquant : 'url'.")
    display_name = name or url

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        response = await active_client.get(url)
        response.raise_for_status()
        xml_text = response.text
    finally:
        if owns_client:
            await active_client.aclose()

    items = parse_feed_items(xml_text)

    state_key = _state_key(url)
    known_ids_raw = memory.recall("persistent", state_key, default=None)
    first_check = known_ids_raw is None
    known_ids = set(known_ids_raw or [])
    new_items = [] if first_check else [item for item in items if item["id"] not in known_ids]
    # Au tout premier contrôle, on ne notifie jamais l'intégralité du flux existant comme
    # "nouveau" (spam garanti) : on se contente d'enregistrer l'état de départ, exactement comme
    # core/url_check.py qui ne notifie jamais au premier contrôle (pas d'état précédent connu).

    # Ordre chronologique probable dans un flux RSS/Atom : le plus récent en premier -> on
    # notifie du plus ancien au plus récent pour respecter l'ordre de publication.
    for item in reversed(new_items):
        title = item["title"] or "(sans titre)"
        link_part = f" — {item['link']}" if item["link"] else ""
        notifications.notify(f"Nouveau sur « {display_name} » : {title}{link_part}", level="info")

    if new_items:
        logger.info(f"{len(new_items)} nouvel(le)(s) entrée(s) détectée(s) sur {url}.")

    all_ids = [item["id"] for item in items][:_MAX_KNOWN_IDS]
    memory.remember("persistent", state_key, all_ids)

    return {"url": url, "name": display_name, "items_total": len(items), "new_items": len(new_items)}
