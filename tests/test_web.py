"""Tests du Web Gateway (Phase 2)."""

from fastapi.testclient import TestClient

from web.app import ALLOWED_WEB_COMMANDS, app

client = TestClient(app)


def test_dashboard_page_loads():
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_terminal_page_loads_and_lists_allowed_commands():
    r = client.get("/terminal")
    assert r.status_code == 200
    for cmd in ALLOWED_WEB_COMMANDS:
        assert cmd in r.text


def test_api_health_matches_cli_healthcheck():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "overall_ok" in body
    assert "checks" in body


def test_api_system_returns_resources():
    r = client.get("/api/system")
    assert r.status_code == 200
    body = r.json()
    assert body["resources"]["ram_total_gb"] > 0
    assert body["resource_level"] in {"NORMAL", "WARNING", "CRITICAL"}


def test_api_cli_allows_whitelisted_command():
    r = client.get("/api/cli/version")
    assert r.status_code == 200
    assert r.json()["command"] == "version"


def test_api_cli_rejects_non_whitelisted_command():
    # Sécurité : une commande arbitraire (ex: "rm") ne doit jamais être exécutée via le web.
    r = client.get("/api/cli/rm")
    assert r.status_code == 403


def test_partials_render_html_fragments():
    r1 = client.get("/partials/system")
    assert r1.status_code == 200
    assert "Ressources système" in r1.text

    r2 = client.get("/partials/health")
    assert r2.status_code == 200
    assert "Diagnostic" in r2.text
