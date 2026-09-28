"""Tests de core/app_run.py (exécution RÉELLE et sandboxée d'une app déjà installée, via
Firejail — suite de la Catégorie G+, demande de l'utilisateur après le signalement
"algorithms-keeper installé mais impossible à lancer").

Même convention que test_app_install.py : `subprocess.run` et `shutil.which` sont simulés
(monkeypatch) — jamais de vraie exécution sandboxée dans la suite automatisée. Une vérification
manuelle avec Firejail réellement installé (apt install firejail) a été faite une fois en dehors
de pytest (voir DECISIONS.md D24) pour confirmer --private/--net=none/--rlimit-as/--rlimit-cpu
fonctionnent comme attendu."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from core.app_install import InvalidNameError, install_dir_for
from core.app_run import (
    InvalidEntryError,
    NotInstalledError,
    RunConfirmationRequiredError,
    SandboxUnavailableError,
    UnknownRunnerError,
    build_command,
    list_runs,
    run_app,
)
from core.config import settings


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    from core.config import settings as _settings
    from core.db import init_db

    init_db(_settings.db_path)
    yield


@pytest.fixture
def installed_app(tmp_path):
    """Simule une app déjà installée : dossier + fichier d'entrée sous fs_root/installed_apps."""
    dest = install_dir_for("github", "TheAlgorithms/algorithms-keeper")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "main.py").write_text("print('bonjour')\n")
    sub = dest / "sub"
    sub.mkdir()
    (sub / "script.py").write_text("print('sous-dossier')\n")
    return dest


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture(autouse=True)
def fake_firejail(monkeypatch):
    """Simule la présence de firejail sur le PATH (sinon SandboxUnavailableError partout)."""
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/firejail" if name == "firejail" else None)


def test_run_requires_confirmation(installed_app):
    with pytest.raises(RunConfirmationRequiredError):
        run_app("github", "TheAlgorithms/algorithms-keeper", "python3", "main.py")


def test_run_rejects_unknown_app_not_installed():
    with pytest.raises(NotInstalledError):
        run_app("github", "jamais/installe-zzz", "python3", "main.py", confirmed=True)


def test_run_rejects_invalid_name(installed_app):
    with pytest.raises(InvalidNameError):
        run_app("github", "rm -rf /", "python3", "main.py", confirmed=True)


def test_run_rejects_unknown_runner(installed_app):
    with pytest.raises(UnknownRunnerError):
        run_app("github", "TheAlgorithms/algorithms-keeper", "bash", "main.py", confirmed=True)


def test_run_rejects_entry_escaping_install_dir(installed_app):
    with pytest.raises(InvalidEntryError):
        run_app(
            "github", "TheAlgorithms/algorithms-keeper", "python3", "../../etc/passwd", confirmed=True
        )


def test_run_accepts_entry_in_subdirectory(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "sous-dossier\n"))
    result = run_app(
        "github", "TheAlgorithms/algorithms-keeper", "python3", "sub/script.py", confirmed=True
    )
    assert result["ok"] is True


def test_run_without_firejail_installed_is_refused_not_run_unsandboxed(installed_app, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(SandboxUnavailableError):
        run_app("github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True)


def test_build_command_uses_firejail_and_private_sandbox(installed_app):
    cmd = build_command(
        "python3",
        installed_app,
        "main.py",
        [],
        firejail_bin="/usr/bin/firejail",
        network=False,
        memory_mb=512,
        cpu_seconds=30,
    )
    assert cmd[0] == "/usr/bin/firejail"
    assert "--net=none" in cmd
    assert f"--private={installed_app.resolve()}" in cmd
    assert "--caps.drop=all" in cmd
    assert "--nonewprivs" in cmd
    assert any(f.startswith("--rlimit-as=") for f in cmd)
    assert any(f.startswith("--rlimit-cpu=") for f in cmd)
    assert cmd[-2:] == ["python3", "main.py"]


def test_build_command_network_flag_omits_net_none(installed_app):
    cmd = build_command(
        "python3",
        installed_app,
        "main.py",
        [],
        firejail_bin="/usr/bin/firejail",
        network=True,
        memory_mb=512,
        cpu_seconds=30,
    )
    assert "--net=none" not in cmd


def test_build_command_passes_extra_args(installed_app):
    cmd = build_command(
        "python3",
        installed_app,
        "main.py",
        ["--foo", "bar"],
        firejail_bin="/usr/bin/firejail",
        network=False,
        memory_mb=512,
        cpu_seconds=30,
    )
    assert cmd[-4:] == ["python3", "main.py", "--foo", "bar"]


def test_successful_run_is_recorded_and_confined_under_fs_root(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "bonjour\n"))
    result = run_app(
        "github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True
    )
    assert result["ok"] is True
    assert "bonjour" in result["output"]
    assert installed_app.is_relative_to(settings.fs_root)

    entries = list_runs()
    assert entries[0]["site"] == "github"
    assert entries[0]["name"] == "TheAlgorithms/algorithms-keeper"
    assert entries[0]["runner"] == "python3"
    assert entries[0]["ok"] is True
    assert entries[0]["output"] == "bonjour\n"
    assert entries[0]["output_truncated"] is False


def test_run_output_is_persisted_in_history_not_just_shown_live(installed_app, monkeypatch):
    """Correctif suite au signalement utilisateur ('je ne vois rien') : le résultat affiché
    juste après avoir cliqué 'Lancer' disparaît si la page est rechargée — la sortie doit donc
    aussi être conservée dans l'historique persistant (core.memory), pas seulement retournée."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "42,7,3\n"))
    run_app("github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True)
    assert "42,7,3" in list_runs()[0]["output"]


def test_long_output_is_truncated_in_history(installed_app, monkeypatch):
    from core.app_run import _MAX_OUTPUT_CHARS

    huge = "x" * (_MAX_OUTPUT_CHARS + 500)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, huge))
    run_app("github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True)
    entry = list_runs()[0]
    assert entry["output_truncated"] is True
    assert len(entry["output"]) < len(huge)


def test_failed_run_reports_failure_honestly(installed_app, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeCompletedProcess(1, "", "Traceback...\n")
    )
    result = run_app(
        "github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True
    )
    assert result["ok"] is False
    assert "Traceback" in result["output"]
    assert list_runs()[0]["ok"] is False


def test_run_timeout_is_handled_gracefully(installed_app, monkeypatch):
    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="firejail", timeout=1, output="partiel", stderr="")

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    result = run_app(
        "github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True, timeout=1
    )
    assert result["ok"] is False
    assert result["timed_out"] is True
    assert "Interrompu" in result["output"]


def test_run_defaults_have_no_network_access_by_default(installed_app):
    cmd = build_command(
        "python3",
        installed_app,
        "main.py",
        [],
        firejail_bin="/usr/bin/firejail",
        network=False,
        memory_mb=512,
        cpu_seconds=30,
    )
    assert "--net=none" in cmd


def test_list_runs_most_recent_first(installed_app, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeCompletedProcess(0, "ok\n"))
    run_app("github", "TheAlgorithms/algorithms-keeper", "python3", "main.py", confirmed=True)
    run_app(
        "github", "TheAlgorithms/algorithms-keeper", "python3", "sub/script.py", confirmed=True
    )
    entries = list_runs()
    assert entries[0]["entry"] == "sub/script.py"
    assert entries[1]["entry"] == "main.py"
