"""Tests de l'intégration web des commandes système en liste blanche (Phase 9 - Sécurité)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.app import app


def test_exec_catalog_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.get("/api/exec/catalog")
        assert r.status_code == 200
        body = r.json()
        assert body["level"] == "READ"  # défaut prudent
        names = {c["name"] for c in body["commands"]}
        assert "pwd" in names and "rm" in names
        pwd_entry = next(c for c in body["commands"] if c["name"] == "pwd")
        assert pwd_entry["allowed"] is True
        rm_entry = next(c for c in body["commands"] if c["name"] == "rm")
        assert rm_entry["allowed"] is False


def test_exec_read_command_succeeds_at_default_level(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/exec", json={"command": "pwd"})
        assert r.status_code == 200
        assert str(tmp_path) in r.json()["stdout"]


def test_exec_write_command_forbidden_at_default_level(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/exec", json={"command": "mkdir sous_dossier"})
        assert r.status_code == 403


def test_exec_unknown_command_is_400(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/exec", json={"command": "shutdown now"})
        assert r.status_code == 400


def test_exec_path_escape_is_400(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/exec", json={"command": "cat ../../etc/passwd"})
        assert r.status_code == 400


def test_exec_destructive_requires_confirmation_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("S1MONE_WEB_PERMISSION_LEVEL", "ADMIN")
    (tmp_path / "a.txt").write_text("x")
    with TestClient(app) as client:
        r = client.post("/api/exec", json={"command": "rm a.txt"})
        assert r.status_code == 409
        assert (tmp_path / "a.txt").exists()

        r = client.post("/api/exec", json={"command": "rm a.txt", "confirm": True})
        assert r.status_code == 200
        assert not (tmp_path / "a.txt").exists()


def test_terminal_page_renders_exec_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    with TestClient(app) as client:
        r = client.get("/terminal")
        assert r.status_code == 200
        assert "Commandes système réelles" in r.text
