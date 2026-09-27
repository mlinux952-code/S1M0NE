"""Tests de la page web Paramètres (Catégorie E, post-NEXT_STEPS.md)."""

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


def test_settings_page_loads():
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Paramètres" in r.text


def test_settings_nav_link_is_enabled():
    r = client.get("/")
    assert '<a href="/settings">Paramètres</a>' in r.text
    assert "Bientôt" not in r.text


def test_settings_page_shows_config_sections():
    r = client.get("/settings")
    assert "[security]" in r.text
    assert "cli_permission_level" in r.text


def test_settings_page_never_leaks_a_secret_value(monkeypatch, tmp_path):
    secret_file = tmp_path / ".env"
    secret_file.write_text("GITHUB_TOKEN=abcd1234superSecret\n", encoding="utf-8")
    monkeypatch.setattr("core.config.DEFAULT_ENV_PATH", secret_file)
    monkeypatch.setattr("web.app.DEFAULT_ENV_PATH", secret_file)
    from core.config import load_settings

    monkeypatch.setattr("web.app.settings", load_settings(env_path=secret_file))

    r = client.get("/settings")
    assert r.status_code == 200
    assert "abcd1234superSecret" not in r.text
    assert "GITHUB_TOKEN" in r.text  # le NOM de la clé peut apparaître, jamais sa valeur


def test_api_settings_shape():
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "security" in body
    assert "_env_keys_present" in body


def test_api_settings_never_leaks_a_secret_value(monkeypatch, tmp_path):
    secret_file = tmp_path / ".env"
    secret_file.write_text("GROQ_API_KEY=sekrit-value-xyz\n", encoding="utf-8")
    from core.config import load_settings

    monkeypatch.setattr("web.app.settings", load_settings(env_path=secret_file))

    r = client.get("/api/settings")
    assert "sekrit-value-xyz" not in r.text
    assert "GROQ_API_KEY" in r.json()["_env_keys_present"]
