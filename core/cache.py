"""core/cache.py — Cache Manager de S1M0NE (Phase 4).

Objectif (mega-prompt §14) : une table clé/valeur avec expiration (TTL), réutilisable par
n'importe quel composant qui a besoin d'éviter de refaire un appel coûteux/limité en fréquence
(en premier lieu : les connecteurs de recherche, Phase 5 — en particulier GitHub dont l'API de
recherche est plafonnée à 30 requêtes/minute).

Principes appliqués :
- La table `cache` existe déjà dans le schéma SQLite depuis la Phase 1 (core/db.py) : ce module
  ne fait qu'ajouter la logique métier par-dessus (get/set/delete/cleanup), sans dupliquer le
  Storage Manager (mega-prompt §5 : un seul cerveau, plusieurs façades).
- Une entrée expirée n'est jamais retournée comme valide : `cache_get` vérifie le TTL à la
  lecture (pas besoin d'un job de fond pour que le cache soit correct, même si `cache_cleanup`
  existe pour purger périodiquement les lignes mortes et ne pas laisser la table grossir).
- La valeur est sérialisée en JSON : n'importe quelle structure Python simple (dict, liste,
  str, nombre) peut être mise en cache telle quelle.
"""

from __future__ import annotations

import json
import time
from typing import Any

from core.config import settings
from core.db import get_connection
from core.logging_setup import get_logger

logger = get_logger("s1mone.cache")


def make_key(*parts: str) -> str:
    """Construit une clé de cache déterministe à partir de plusieurs segments.

    Exemple : make_key("search", "npm", "react", "10") -> "search:npm:react:10"
    """
    return ":".join(str(p) for p in parts)


def cache_set(key: str, value: Any, source: str = "", ttl: int | None = None) -> None:
    """Enregistre `value` sous `key`, valide pendant `ttl` secondes (défaut : config.toml)."""
    ttl = ttl if ttl is not None else settings.cache_default_ttl_seconds
    serialized = json.dumps(value, ensure_ascii=False)
    now = time.time()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cache (key, value, source, created_at, ttl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                created_at = excluded.created_at,
                ttl = excluded.ttl
            """,
            (key, serialized, source, now, ttl),
        )


def cache_get(key: str) -> Any | None:
    """Retourne la valeur en cache pour `key`, ou None si absente ou expirée.

    Une entrée expirée n'est jamais renvoyée (même si elle n'a pas encore été purgée par
    `cache_cleanup`) : la fraîcheur des données prime sur l'optimisation du ménage.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value, created_at, ttl FROM cache WHERE key = ?", (key,)
        ).fetchone()
    if row is None:
        return None
    if time.time() - row["created_at"] > row["ttl"]:
        return None  # expirée : on ne la supprime pas ici, cache_cleanup s'en chargera
    try:
        return json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Entrée de cache corrompue ignorée pour la clé '{key}'.")
        return None


def cache_delete(key: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))


def cache_cleanup(now: float | None = None) -> int:
    """Supprime toutes les entrées expirées. Retourne le nombre de lignes supprimées.

    Pensé pour être appelé périodiquement (ex. par le worker de tâches ou une tâche dédiée),
    pas obligatoire pour la correction du cache (cache_get filtre déjà les entrées expirées),
    seulement pour éviter que la table ne grossisse indéfiniment.
    """
    now = now if now is not None else time.time()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM cache WHERE (? - created_at) > ttl", (now,))
        return cursor.rowcount
