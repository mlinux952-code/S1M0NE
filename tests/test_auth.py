"""Tests du module d'authentification web (NEXT_STEPS.md §A.1)."""

from __future__ import annotations

import time

from core import auth


def test_roundtrip_valid_cookie():
    cookie = auth.create_session_cookie("motdepasse")
    assert auth.verify_session_cookie(cookie, "motdepasse") is True


def test_wrong_password_rejected():
    cookie = auth.create_session_cookie("motdepasse")
    assert auth.verify_session_cookie(cookie, "autrechose") is False


def test_expired_cookie_rejected():
    expired = f"{int(time.time()) - 10}.deadbeef"
    assert auth.verify_session_cookie(expired, "motdepasse") is False


def test_malformed_cookie_rejected():
    assert auth.verify_session_cookie(None, "x") is False
    assert auth.verify_session_cookie("", "x") is False
    assert auth.verify_session_cookie("sans-point", "x") is False
    assert auth.verify_session_cookie("pasunentier.abcd", "x") is False


def test_check_password(monkeypatch):
    monkeypatch.setenv("S1MONE_WEB_PASSWORD", "secret123")
    assert auth.check_password("secret123") is True
    assert auth.check_password("mauvais") is False


def test_check_password_disabled_by_default(monkeypatch):
    monkeypatch.delenv("S1MONE_WEB_PASSWORD", raising=False)
    assert auth.check_password("peu importe") is False


def test_is_path_exempt():
    assert auth.is_path_exempt("/login") is True
    assert auth.is_path_exempt("/static/css/style.css") is True
    assert auth.is_path_exempt("/") is False
    assert auth.is_path_exempt("/api/exec") is False
