"""Tests web de l'installation réelle d'apps (/api/discover/install, /partials/installed-apps)."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from core.config import settings
from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_installed_apps():
    from core import memory

    installed_root = settings.fs_root / "installed_apps"
    shutil.rmtree(installed_root, ignore_errors=True)
    memory.remember("persistent", "installed_apps_log", [])
    yield
    shutil.rmtree(installed_root, ignore_errors=True)
    memory.remember("persistent", "installed_apps_log", [])


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_discover_page_has_install_output_zone_and_installed_apps_section():
    r = client.get("/discover")
    assert r.status_code == 200
    assert 'id="install-output"' in r.text
    assert "/partials/installed-apps" in r.text


def test_discover_results_have_install_buttons_except_sourceforge():
    r = client.get("/partials/discover", params={"site": "npm"})
    assert "/api/discover/install" in r.text
    r_sf = client.get("/partials/discover", params={"site": "sourceforge"})
    assert "non proposé" in r_sf.text


def test_search_results_also_have_install_buttons(monkeypatch):
    """Demande explicite de l'utilisateur : l'installation doit marcher aussi depuis /search."""
    import connectors.engine as engine

    async def fake_search_all(q, limit_per_source=10, sources=None):
        return {
            "results": [
                {
                    "source": "npm",
                    "name": "lodash",
                    "description": "utility library",
                    "url": "https://npmjs.com/package/lodash",
                    "extra": {},
                }
            ],
            "errors": {},
            "cache_hits": [],
        }

    monkeypatch.setattr("web.app.search_all", fake_search_all)
    r = client.get("/partials/search-results", params={"q": "lodash"})
    assert r.status_code == 200
    assert "/api/discover/install" in r.text


def test_install_without_confirmation_shows_error():
    r = client.post("/api/discover/install", data={"site": "npm", "name": "is-odd"})
    assert r.status_code == 200
    assert "confirmation" in r.text.lower()


def test_install_with_confirmation_executes_and_shows_output(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "added 1 package\n")
    )
    r = client.post(
        "/api/discover/install",
        data={"site": "npm", "name": "is-odd", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "réussie" in r.text
    assert "added 1 package" in r.text


def test_install_sourceforge_refused_with_clear_message():
    r = client.post(
        "/api/discover/install",
        data={"site": "sourceforge", "name": "qbittorrent", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "Aucune installation automatique" in r.text


def test_install_untrusted_url_is_refused():
    r = client.post(
        "/api/discover/install",
        data={
            "site": "github",
            "name": "x",
            "url": "https://evil.example.com/x",
            "confirmed": "true",
        },
    )
    assert r.status_code == 200
    assert "invalide" in r.text.lower()


def test_installed_apps_partial_lists_history(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    client.post("/api/discover/install", data={"site": "npm", "name": "is-odd", "confirmed": "true"})
    r = client.get("/partials/installed-apps")
    assert r.status_code == 200
    assert "is-odd" in r.text


def test_installed_apps_partial_empty_by_default():
    r = client.get("/partials/installed-apps")
    assert "Aucune installation" in r.text
