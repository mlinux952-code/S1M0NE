"""core/discover.py — Catalogue statique de découverte (Catégorie G).

Demande explicite de l'utilisateur : compiler une recherche (une fois) de projets réels et
notables sur les 7 sites déjà connectés à S1M0NE (npm, PyPI, GitHub, GitLab, Codeberg,
Hugging Face, SourceForge) et l'embarquer DANS S1M0NE, consultable "sans un seul mise à jour"
(hors-ligne, aucun appel réseau requis pour parcourir le catalogue).

Choix assumé (honnêteté avant tout, mega-prompt) : ceci N'EST PAS une recherche en direct — les
100 entrées sont un instantané figé (voir `compiled_on` dans le JSON), sourcé sur de vraies pages
(classements npm/PyPI officiels, listes GitHub par étoiles, téléchargements Hugging Face,
dépôts confirmés sur GitLab/Codeberg/SourceForge). Les chiffres de popularité datent de la
compilation et ne sont jamais rafraîchis automatiquement. Pour une recherche à jour, l'utilisateur
dispose déjà de `s1mone search` (Phase 5) qui interroge les vraies API en direct — le catalogue de
découverte est un complément (inspiration, parcours par catégorie), pas un remplacement.

Zéro nouvelle dépendance : lecture d'un fichier JSON statique via la stdlib.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


# Volontairement PAS dans data/ (dossier gitignoré, réservé aux données runtime — base SQLite de
# l'utilisateur, jamais poussées sur GitHub) : ce catalogue est un fichier livré AVEC S1M0NE,
# comme le code lui-même, donc rangé dans resources/ et bien versionné.
CATALOG_PATH = Path(__file__).resolve().parent.parent / "resources" / "discover_catalog.json"


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    """Charge le catalogue une seule fois par processus (fichier statique, jamais modifié à
    l'exécution) — évite de re-parser le JSON à chaque appel."""
    with CATALOG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def catalog_metadata() -> dict[str, Any]:
    """Date de compilation + note d'honnêteté, à toujours afficher à côté des résultats."""
    data = _load_catalog()
    return {"compiled_on": data["compiled_on"], "note": data["note"], "total": len(data["entries"])}


def available_sites() -> list[str]:
    """Sites présents dans le catalogue, triés — mêmes noms que connectors.engine (Phase 5)."""
    data = _load_catalog()
    return sorted({e["site"] for e in data["entries"]})


def list_entries(site: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
    """Liste les entrées du catalogue, filtrées par site et/ou catégorie (insensible à la casse).
    Sans filtre, retourne les 100 entrées."""
    data = _load_catalog()
    entries = data["entries"]
    if site:
        entries = [e for e in entries if e["site"].lower() == site.lower()]
    if category:
        entries = [e for e in entries if e["category"].lower() == category.lower()]
    return entries


def search_catalog(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Recherche par mot-clé (nom, description, catégorie) — simple sous-chaîne insensible à la
    casse, cohérent avec un catalogue de 100 entrées (pas besoin de FTS5 ici, contrairement à
    core/notes.py qui doit passer à l'échelle sur un vrai corpus de notes personnelles)."""
    if not query.strip():
        return []
    needle = query.strip().lower()
    data = _load_catalog()
    matches = [
        e
        for e in data["entries"]
        if needle in e["name"].lower() or needle in e["description"].lower() or needle in e["category"].lower()
    ]
    return matches[:limit]
