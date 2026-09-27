"""core/notes.py — Recherche plein texte de notes personnelles (Catégorie F : mini "second
brain", inspiré d'outils comme Khoj/Obsidian tout en restant strictement dans l'esprit
LOW RESOURCE FIRST du mega-prompt).

Choix : SQLite FTS5 (extension déjà compilée dans le sqlite3 de la stdlib sur la quasi-totalité
des distributions modernes), PAS de base vectorielle (ChromaDB, pgvector, FAISS...) — S1M0NE
n'indexe pas le SENS des notes (embeddings), seulement leur TEXTE (mots-clés, comme `grep` mais
avec classement par pertinence et recherche par racine de mot). Suffisant pour un usage
personnel, zéro dépendance supplémentaire, zéro modèle à télécharger.

Une note est identifiée par son chemin de fichier absolu (`path`) : ré-indexer un fichier déjà
connu remplace son contenu (jamais de doublon). Rien n'est jamais indexé sans action explicite de
l'utilisateur (`s1mone notes index <chemin>`) : pas de surveillance automatique de dossier.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.db import get_connection, notes_fts_available
from core.logging_setup import get_logger

logger = get_logger("s1mone.notes")

# Extensions traitées comme du texte brut. Volontairement restreint (mega-prompt : jamais
# deviner le contenu d'un format qu'on ne sait pas lire correctement, ex. .docx/.pdf).
_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}


class NotesUnavailableError(RuntimeError):
    """Levée quand FTS5 n'est pas supporté par le SQLite de la machine (cas rare)."""


def _require_available() -> None:
    if not notes_fts_available():
        raise NotesUnavailableError(
            "Recherche de notes indisponible : ce SQLite n'a pas l'extension FTS5 compilée."
        )


def _extract_title(text: str, fallback: str) -> str:
    """Premier titre Markdown (`# ...`) trouvé, sinon la première ligne non vide, sinon le nom
    de fichier — jamais une chaîne vide inventée."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        if stripped:
            return stripped[:120]
    return fallback


def index_path(path: str | Path, recursive: bool = True) -> dict[str, Any]:
    """Indexe un fichier ou un dossier (récursif par défaut). Retourne un résumé
    {indexed, skipped, errors} — ne lève jamais pour un fichier illisible individuel (le
    processus d'indexation continue avec les autres, cohérent avec la robustesse déjà appliquée
    aux connecteurs de recherche, Phase 5)."""
    _require_available()
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Chemin introuvable : {target}")

    if target.is_file():
        candidates = [target]
    else:
        pattern = "**/*" if recursive else "*"
        candidates = [p for p in target.glob(pattern) if p.is_file()]

    indexed = 0
    skipped = 0
    errors: list[str] = []
    with get_connection() as conn:
        for file_path in candidates:
            if file_path.suffix.lower() not in _TEXT_EXTENSIONS:
                skipped += 1
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"{file_path}: {exc}")
                continue
            title = _extract_title(content, fallback=file_path.stem)
            abs_path = str(file_path.resolve())
            conn.execute("DELETE FROM notes_fts WHERE path = ?", (abs_path,))
            conn.execute(
                "INSERT INTO notes_fts (path, title, content) VALUES (?, ?, ?)",
                (abs_path, title, content),
            )
            indexed += 1

    logger.info(f"Notes indexées : {indexed} (ignorées : {skipped}, erreurs : {len(errors)}) depuis {target}")
    return {"indexed": indexed, "skipped": skipped, "errors": errors}


def _sanitize_query(query: str) -> str:
    """Transforme une requête utilisateur libre en expression MATCH FTS5 sûre : chaque mot est
    mis entre guillemets (recherche littérale) et les mots sont implicitement combinés en ET —
    évite qu'un mot contenant '-', '"', '(' etc. ne casse la syntaxe MATCH de FTS5."""
    words = query.split()
    if not words:
        return '""'
    escaped = [w.replace('"', '""') for w in words]
    return " ".join(f'"{w}"' for w in escaped)


def search_notes(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Recherche plein texte (titre + contenu). Retourne path/title/snippet, classés par
    pertinence FTS5 (bm25). Une requête vide retourne une liste vide (jamais tout le corpus)."""
    _require_available()
    if not query.strip():
        return []
    match_expr = _sanitize_query(query)
    with get_connection() as conn:
        try:
            rows = conn.execute(
                "SELECT path, title, snippet(notes_fts, 2, '[', ']', '…', 10) AS snippet "
                "FROM notes_fts WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?",
                (match_expr, limit),
            ).fetchall()
        except Exception as exc:  # noqa: BLE001 - une requête FTS5 malformée ne doit jamais planter
            logger.warning(f"Recherche de notes échouée pour '{query}' : {exc}")
            return []
    return [{"path": r["path"], "title": r["title"], "snippet": r["snippet"]} for r in rows]


def notes_stats() -> dict[str, Any]:
    """Nombre de notes actuellement indexées. {"available": False} si FTS5 n'est pas supporté."""
    if not notes_fts_available():
        return {"available": False, "total": 0}
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM notes_fts").fetchone()["n"]
    return {"available": True, "total": total}


def clear_notes_index() -> int:
    """Vide entièrement l'index de notes (les fichiers d'origine ne sont jamais touchés — on
    supprime seulement leur copie indexée). Retourne le nombre d'entrées supprimées."""
    _require_available()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM notes_fts")
        return cursor.rowcount


def remove_note(path: str | Path) -> bool:
    """Retire une note précise de l'index (ex: fichier supprimé/déplacé). False si absente."""
    _require_available()
    abs_path = str(Path(path).expanduser().resolve())
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM notes_fts WHERE path = ?", (abs_path,))
        return cursor.rowcount > 0
