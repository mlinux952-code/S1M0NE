"""Tests web de l'exécution réelle sandboxée d'apps installées (/api/discover/run,
/partials/installed-apps — bouton "Lancer")."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from core.app_install import install_dir_for
from web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


@pytest.fixture(autouse=True)
def fake_firejail(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/firejail" if name == "firejail" else None)


@pytest.fixture
def installed_app():
    dest = install_dir_for("npm", "is-odd")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.js").write_text("console.log('ok');\n")
    return dest


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_installed_apps_partial_has_run_form_for_ok_entries(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    client.post("/api/discover/install", data={"site": "npm", "name": "is-odd", "confirmed": "true"})
    r = client.get("/partials/installed-apps")
    assert r.status_code == 200
    assert "/api/discover/run" in r.text
    assert "run-output" in r.text


def test_run_without_confirmation_shows_error(installed_app):
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js"},
    )
    assert r.status_code == 200
    assert "confirmation" in r.text.lower()


def test_run_with_confirmation_executes_and_shows_output(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "réussie" in r.text
    assert "ok" in r.text


def test_run_not_installed_shows_clear_error():
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "jamais-installe", "runner": "node", "entry": "index.js", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "est pas install" in r.text


def test_run_unknown_runner_is_refused(installed_app):
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "bash", "entry": "index.js", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "Interpréteur inconnu" in r.text


def test_run_entry_escaping_install_dir_is_refused(installed_app):
    r = client.post(
        "/api/discover/run",
        data={
            "site": "npm", "name": "is-odd", "runner": "node", "entry": "../../etc/passwd",
            "confirmed": "true",
        },
    )
    assert r.status_code == 200
    assert "sort du dossier" in r.text


def test_run_without_firejail_is_refused(installed_app, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js", "confirmed": "true"},
    )
    assert r.status_code == 200
    assert "Firejail n" in r.text and "est pas installé" in r.text


def test_run_extra_args_are_parsed(installed_app, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(0, "ok\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = client.post(
        "/api/discover/run",
        data={
            "site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js",
            "args": "--foo bar", "confirmed": "true",
        },
    )
    assert r.status_code == 200
    assert captured["cmd"][-2:] == ["--foo", "bar"]


def test_run_malformed_args_shows_clear_error(installed_app):
    r = client.post(
        "/api/discover/run",
        data={
            "site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js",
            "args": "\"unclosed quote", "confirmed": "true",
        },
    )
    assert r.status_code == 200
    assert "invalides" in r.text.lower()


def test_discover_page_has_run_history_zone(installed_app):
    r = client.get("/discover")
    assert r.status_code == 200
    assert 'id="run-history-list"' in r.text
    assert "/partials/run-history" in r.text
    assert "runCompleted" in r.text


def test_run_history_partial_empty_by_default():
    r = client.get("/partials/run-history")
    assert r.status_code == 200
    assert "Aucune exécution" in r.text


def test_run_history_persists_output_after_execution(installed_app, monkeypatch):
    """Correctif suite au signalement 'je ne vois rien' : le résultat doit rester visible via
    l'historique persistant, pas seulement dans la réponse htmx éphémère."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "42,7,3\n"))
    client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js", "confirmed": "true"},
    )
    r = client.get("/partials/run-history")
    assert r.status_code == 200
    assert "42,7,3" in r.text
    assert "is-odd" in r.text


def test_successful_run_triggers_history_refresh_via_hx_trigger_header(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js", "confirmed": "true"},
    )
    assert r.headers.get("HX-Trigger") == "runCompleted"


def test_run_refused_before_execution_does_not_trigger_history_refresh(installed_app):
    r = client.post(
        "/api/discover/run",
        data={"site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js"},
    )
    assert "HX-Trigger" not in r.headers


def test_run_network_flag_is_passed_through(installed_app, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(0, "ok\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client.post(
        "/api/discover/run",
        data={
            "site": "npm", "name": "is-odd", "runner": "node", "entry": "index.js",
            "network": "true", "confirmed": "true",
        },
    )
    assert "--net=none" not in captured["cmd"]
