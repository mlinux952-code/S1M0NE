"""Tests du Permission Manager (Phase 9 - Sécurité)."""

from __future__ import annotations

import pytest

from core import permissions
from core.permissions import Permission


def test_permission_order():
    assert Permission.READ < Permission.WRITE < Permission.EXECUTE < Permission.ADMIN


def test_parse_level_valid_case_insensitive():
    assert permissions.parse_level("read") is Permission.READ
    assert permissions.parse_level("ADMIN") is Permission.ADMIN
    assert permissions.parse_level("Write") is Permission.WRITE


def test_parse_level_invalid_raises_value_error():
    with pytest.raises(ValueError):
        permissions.parse_level("SUPERUSER")


def test_check_access_allows_sufficient_level():
    spec = permissions.check_access("pwd", Permission.READ)
    assert spec.name == "pwd"


def test_check_access_denies_insufficient_level():
    with pytest.raises(permissions.PermissionError_):
        permissions.check_access("mkdir", Permission.READ)


def test_check_access_unknown_command():
    with pytest.raises(permissions.UnknownCommandError):
        permissions.check_access("shutdown", Permission.ADMIN)


def test_destructive_commands_require_admin():
    for name in ("rm", "rmdir"):
        spec = permissions.get_command(name)
        assert spec.destructive is True
        assert spec.permission is Permission.ADMIN


def test_no_dangerous_system_commands_in_catalog():
    """Garde-fou explicite (DECISIONS.md D10) : shutdown/reboot/dd/mkfs ne sont jamais dans la
    liste blanche, quel que soit le niveau de permission."""
    forbidden = {"shutdown", "reboot", "dd", "mkfs", "chmod", "chown", "kill", "sudo"}
    assert forbidden.isdisjoint(permissions.CATALOG.keys())


def test_available_commands_filters_by_level():
    read_only = permissions.available_commands(Permission.READ)
    assert all(s.permission == Permission.READ for s in read_only)
    everything = permissions.available_commands(Permission.ADMIN)
    assert len(everything) == len(permissions.CATALOG)


def test_cli_and_web_level_from_settings(monkeypatch):
    monkeypatch.setenv("S1MONE_CLI_PERMISSION_LEVEL", "write")
    monkeypatch.setenv("S1MONE_WEB_PERMISSION_LEVEL", "execute")
    assert permissions.cli_level() is Permission.WRITE
    assert permissions.web_level() is Permission.EXECUTE
