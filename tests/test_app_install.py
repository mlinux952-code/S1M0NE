"""Tests de core/app_install.py (installation réelle et confinée d'apps du catalogue/de la
recherche en direct — demande explicite de l'utilisateur, "installer directement sur S1M0NE").

Même convention que les connecteurs (connectors/*.py, Phase 5) : jamais de vrai appel réseau
dans la suite automatisée (lent, non déterministe, pollue le disque à chaque run) —
`subprocess.run` est simulé (`monkeypatch`). Une vérification manuelle bout-en-bout avec de
vraies installations (npm/pip/git réels) a été faite une fois en dehors de pytest (voir
DECISIONS.md) pour s'assurer que le comportement réel correspond bien à ce que ces tests
vérifient de façon isolée."""

from __future__ import annotations

import subprocess

import pytest

from core.app_install import (
    InstallConfirmationRequiredError,
    InvalidNameError,
    InvalidUrlError,
    UnsupportedSiteError,
    build_command,
    install_app,
    install_dir_for,
    list_installed,
)
from core.config import settings


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Isole la base SQLite ET le dossier fs_root/installed_apps dans un répertoire temporaire —
    même pattern que tests/test_memory.py et tests/test_web_notes.py. Bug réel détecté avant ce
    correctif (voir DECISIONS.md D23) : sans cette isolation, ces tests dépendaient de l'ordre
    d'exécution (échec avec pytest-randomly sur un clone frais où data/s1mone.db n'existe pas
    encore) car ils réutilisaient la vraie base du projet."""
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings
    from core.db import init_db

    init_db(settings.db_path)
    yield


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_install_requires_confirmation():
    with pytest.raises(InstallConfirmationRequiredError):
        install_app("npm", "is-odd")


def test_sourceforge_is_never_installable():
    with pytest.raises(UnsupportedSiteError):
        install_app("sourceforge", "qbittorrent", confirmed=True)


def test_invalid_name_is_rejected():
    with pytest.raises(InvalidNameError):
        install_app("npm", "rm -rf /", confirmed=True)


def test_build_command_rejects_untrusted_url_for_git_sites():
    with pytest.raises(InvalidUrlError):
        build_command("github", "x/y", "https://evil.example.com/x/y", install_dir_for("github", "x/y"))


def test_build_command_accepts_known_gitlab_self_hosted_instances():
    # Le catalogue statique (D22) contient des projets sur gitlab.gnome.org/gitlab.freedesktop.org
    # en plus de gitlab.com : ces deux hôtes doivent rester utilisables.
    cmd = build_command(
        "gitlab", "GNOME/gimp", "https://gitlab.gnome.org/GNOME/gimp", install_dir_for("gitlab", "GNOME/gimp")
    )
    assert cmd[:2] == ["git", "clone"]
    assert "https://gitlab.gnome.org/GNOME/gimp" in cmd


def test_build_command_npm_uses_local_prefix_never_global():
    dest = install_dir_for("npm", "is-odd")
    cmd = build_command("npm", "is-odd", None, dest)
    assert cmd == ["npm", "install", "is-odd", "--prefix", str(dest)]
    assert "-g" not in cmd  # jamais d'installation globale sur la machine


def test_build_command_pypi_uses_target_never_the_running_venv():
    dest = install_dir_for("pypi", "six")
    cmd = build_command("pypi", "six", None, dest)
    assert "--target" in cmd
    assert str(dest) in cmd


def test_install_is_confined_under_fs_root():
    dest = install_dir_for("npm", "is-odd")
    assert dest.is_relative_to(settings.fs_root)


def test_successful_install_is_recorded_and_returns_output(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "added 1 package\n")
    )
    result = install_app("npm", "is-odd", confirmed=True)
    assert result["ok"] is True
    assert "added 1 package" in result["output"]
    assert result["install_dir"].endswith("is-odd")

    entries = list_installed()
    assert entries[0]["site"] == "npm"
    assert entries[0]["name"] == "is-odd"
    assert entries[0]["ok"] is True


def test_failed_install_reports_failure_honestly_not_a_false_success(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _FakeCompletedProcess(1, "", "404 Not Found\n"),
    )
    result = install_app("npm", "zzzz-improbable-zzzz", confirmed=True)
    assert result["ok"] is False
    assert "404" in result["output"]

    entries = list_installed()
    assert entries[0]["ok"] is False


def test_timeout_is_handled_gracefully(monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="npm", timeout=1, output="partial", stderr="")

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    result = install_app("npm", "is-odd", confirmed=True, timeout=1)
    assert result["ok"] is False
    assert "Interrompu" in result["output"]


def test_missing_binary_is_handled_gracefully(monkeypatch):
    def _raise_missing(*args, **kwargs):
        raise FileNotFoundError("npm introuvable")

    monkeypatch.setattr(subprocess, "run", _raise_missing)
    result = install_app("npm", "is-odd", confirmed=True)
    assert result["ok"] is False
    assert "introuvable" in result["output"]


def test_list_installed_most_recent_first(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    install_app("npm", "is-odd", confirmed=True)
    install_app("pypi", "six", confirmed=True)
    entries = list_installed()
    assert entries[0]["name"] == "six"
    assert entries[1]["name"] == "is-odd"
