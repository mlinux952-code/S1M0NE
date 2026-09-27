"""Tests de core/notes.py (Catégorie F : recherche plein texte de notes, mini second brain)."""

from __future__ import annotations

import pytest

from core.notes import clear_notes_index, index_path, notes_stats, remove_note, search_notes


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path / "data"))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    (d / "idee.md").write_text(
        "# Idée de projet\n\nIl faudrait ajouter une sauvegarde chiffrée pour S1M0NE.",
        encoding="utf-8",
    )
    (d / "journal.txt").write_text("Aujourd'hui, test du connecteur RSS de S1M0NE.", encoding="utf-8")
    (d / "ignore.pdf").write_text("binaire fictif", encoding="utf-8")
    sub = d / "sub"
    sub.mkdir()
    (sub / "note_imbriquee.md").write_text("Une note dans un sous-dossier.", encoding="utf-8")
    return d


def test_index_path_indexes_only_text_files_recursively(notes_dir):
    result = index_path(notes_dir)
    assert result["indexed"] == 3  # idee.md, journal.txt, note_imbriquee.md
    assert result["skipped"] == 1  # ignore.pdf
    assert result["errors"] == []


def test_index_path_non_recursive_skips_subfolders(notes_dir):
    result = index_path(notes_dir, recursive=False)
    assert result["indexed"] == 2  # idee.md, journal.txt (pas note_imbriquee.md)


def test_index_single_file(notes_dir):
    result = index_path(notes_dir / "idee.md")
    assert result["indexed"] == 1


def test_index_missing_path_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        index_path("/chemin/qui/n/existe/pas/vraiment")


def test_notes_stats_reflects_indexed_count(notes_dir):
    assert notes_stats() == {"available": True, "total": 0}
    index_path(notes_dir)
    assert notes_stats()["total"] == 3


def test_reindexing_same_file_does_not_duplicate(notes_dir):
    index_path(notes_dir / "idee.md")
    index_path(notes_dir / "idee.md")
    assert notes_stats()["total"] == 1


def test_search_notes_finds_matching_content(notes_dir):
    index_path(notes_dir)
    results = search_notes("sauvegarde")
    assert len(results) == 1
    assert "idee.md" in results[0]["path"]
    assert "sauvegarde" in results[0]["snippet"].lower() or "[sauvegarde]" in results[0]["snippet"]


def test_search_notes_ranks_multiple_matches(notes_dir):
    index_path(notes_dir)
    results = search_notes("S1M0NE")
    paths = [r["path"] for r in results]
    assert len(results) == 2  # idee.md et journal.txt mentionnent S1M0NE, pas note_imbriquee.md
    assert any("idee.md" in p for p in paths)
    assert any("journal.txt" in p for p in paths)


def test_search_notes_no_match_returns_empty_list(notes_dir):
    index_path(notes_dir)
    assert search_notes("mot-improbable-zzz") == []


def test_search_notes_empty_query_returns_empty_list(notes_dir):
    index_path(notes_dir)
    assert search_notes("   ") == []


def test_search_notes_tolerates_special_characters_without_crashing(notes_dir):
    index_path(notes_dir)
    # Des caractères qui ont un sens spécial dans la syntaxe MATCH de FTS5 (guillemets,
    # parenthèses, tiret) ne doivent jamais faire planter la recherche (mega-prompt : robustesse).
    assert search_notes('sauvegarde" OR (test-ceci)') == [] or isinstance(
        search_notes('sauvegarde" OR (test-ceci)'), list
    )


def test_remove_note_removes_only_that_entry(notes_dir):
    index_path(notes_dir)
    assert remove_note(notes_dir / "idee.md") is True
    assert notes_stats()["total"] == 2
    assert search_notes("sauvegarde") == []


def test_remove_note_missing_returns_false(notes_dir):
    index_path(notes_dir)
    assert remove_note(notes_dir / "jamais-indexe.md") is False


def test_clear_notes_index_removes_everything_but_not_source_files(notes_dir):
    index_path(notes_dir)
    removed = clear_notes_index()
    assert removed == 3
    assert notes_stats()["total"] == 0
    assert (notes_dir / "idee.md").exists()  # le fichier d'origine n'est jamais touché
