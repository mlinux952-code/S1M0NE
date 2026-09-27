"""Tests de la recherche de notes côté web (Catégorie F, section ajoutée à /memory)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


def test_memory_page_shows_notes_search_section():
    r = client.get("/memory")
    assert r.status_code == 200
    assert "Notes personnelles" in r.text
    assert "/partials/notes-search" in r.text


def test_notes_search_partial_with_empty_query_prompts_for_input():
    r = client.get("/partials/notes-search", params={"q": ""})
    assert r.status_code == 200
    assert "Tape une recherche" in r.text


def test_notes_search_partial_with_no_match():
    r = client.get("/partials/notes-search", params={"q": "mot-improbable-zzz"})
    assert r.status_code == 200
    assert "Aucun résultat" in r.text


def test_notes_search_partial_finds_indexed_note(tmp_path):
    from core.notes import index_path

    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "a.md").write_text("# Titre\n\nContenu avec le mot fusée dedans.", encoding="utf-8")
    index_path(notes_dir)

    r = client.get("/partials/notes-search", params={"q": "fusée"})
    assert r.status_code == 200
    assert "Titre" in r.text
    assert "a.md" in r.text


def test_notes_search_never_exposes_an_indexing_form():
    """Garde-fou : indexer un chemin arbitraire doit rester strictement réservé à la CLI, jamais
    exposé comme un formulaire web (voir DECISIONS.md, même logique que 'pas de memory remember
    en CLI', D.3)."""
    r = client.get("/memory")
    assert "notes/index" not in r.text
    assert 'name="path"' not in r.text
