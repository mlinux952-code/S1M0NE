"""Tests de l'exécution réelle des commandes en liste blanche (Phase 9 - Sécurité)."""

from __future__ import annotations

import pytest

from core import permissions
from core.permissions import Permission
from core.shell_runner import run_command


def test_run_read_command(tmp_path):
    result = run_command("pwd", level=Permission.READ, fs_root=tmp_path)
    assert result["returncode"] == 0
    assert str(tmp_path) in result["stdout"]


def test_run_unknown_command_raises(tmp_path):
    with pytest.raises(permissions.UnknownCommandError):
        run_command("shutdown now", level=Permission.ADMIN, fs_root=tmp_path)


def test_run_insufficient_permission_raises(tmp_path):
    with pytest.raises(permissions.PermissionError_):
        run_command("mkdir sous_dossier", level=Permission.READ, fs_root=tmp_path)


def test_mkdir_and_ls_stay_within_fs_root(tmp_path):
    result = run_command("mkdir sous_dossier", level=Permission.WRITE, fs_root=tmp_path)
    assert result["returncode"] == 0
    assert (tmp_path / "sous_dossier").is_dir()

    result = run_command("ls .", level=Permission.READ, fs_root=tmp_path)
    assert "sous_dossier" in result["stdout"]


def test_path_escape_relative_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_command("cat ../../etc/passwd", level=Permission.ADMIN, fs_root=tmp_path)


def test_path_escape_absolute_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_command("ls /etc", level=Permission.ADMIN, fs_root=tmp_path)


def test_destructive_command_requires_confirmation(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(permissions.ConfirmationRequiredError):
        run_command("rm a.txt", level=Permission.ADMIN, fs_root=tmp_path, confirmed=False)
    assert (tmp_path / "a.txt").exists()  # rien n'a été supprimé avant confirmation


def test_destructive_command_executes_once_confirmed(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    result = run_command("rm a.txt", level=Permission.ADMIN, fs_root=tmp_path, confirmed=True)
    assert result["returncode"] == 0
    assert not (tmp_path / "a.txt").exists()


def test_empty_command_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        run_command("   ", level=Permission.ADMIN, fs_root=tmp_path)
