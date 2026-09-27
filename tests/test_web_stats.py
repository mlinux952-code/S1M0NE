"""Tests de la page web Statistiques (Catégorie D, post-NEXT_STEPS.md)."""

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


def test_stats_page_loads():
    r = client.get("/stats")
    assert r.status_code == 200
    assert "Statistiques" in r.text


def test_stats_nav_link_present():
    r = client.get("/")
    assert '<a href="/stats">Statistiques</a>' in r.text


def test_api_stats_shape():
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    for key in ("tasks", "memory", "cache", "projects", "notifications", "schedules", "generated_at"):
        assert key in body


def test_api_stats_reflects_real_memory_entries():
    from core import memory as memory_module

    memory_module.remember("temporary", "note", "hello")
    r = client.get("/api/stats")
    body = r.json()
    assert body["memory"]["total"] == 1
    assert body["memory"]["by_level"] == {"temporary": 1}


def test_partial_stats_renders_cards():
    r = client.get("/partials/stats")
    assert r.status_code == 200
    assert "Tâches" in r.text
    assert "Mémoire" in r.text
    assert "Cache de recherche" in r.text
