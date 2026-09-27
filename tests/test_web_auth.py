"""Tests de l'authentification web optionnelle (NEXT_STEPS.md §A.1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app


def test_no_password_configured_means_open_access(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("S1MONE_WEB_PASSWORD", raising=False)
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        r = client.get("/api/system")
        assert r.status_code == 200


def test_protected_page_redirects_to_login_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/")
        assert r.status_code == 303
        assert r.headers["location"] == "/login"


def test_protected_api_returns_401_without_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/api/system")
        assert r.status_code == 401


def test_login_page_accessible_without_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        r = client.get("/login")
        assert r.status_code == 200


def test_login_wrong_password_no_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/login", data={"password": "mauvais"})
        assert r.status_code == 303
        assert r.headers["location"] == "/login?error=1"
        assert "s1mone_session" not in r.cookies


def test_login_correct_password_grants_access(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        r = client.post("/login", data={"password": "secret123"})
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert "s1mone_session" in client.cookies

        r = client.get("/api/system")
        assert r.status_code == 200

        r = client.get("/")
        assert r.status_code == 200


def test_logout_clears_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    with TestClient(app, follow_redirects=False) as client:
        client.post("/login", data={"password": "secret123"})
        assert "s1mone_session" in client.cookies
        r = client.get("/logout")
        assert r.status_code == 303
        r2 = client.get("/api/system")
        assert r2.status_code == 401
