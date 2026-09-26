"""Tests de la CLI 's1mone task ...' (Phase 3)."""

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def test_task_submit_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))

    result = runner.invoke(app, ["task", "submit", "sleep", "--param", "seconds=0"])
    assert result.exit_code == 0
    assert "Tâche créée" in result.stdout

    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0
    assert "sleep" in result.stdout


def test_task_submit_unknown_type_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["task", "submit", "type_inconnu"])
    assert result.exit_code == 1


def test_task_worker_once_processes_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    runner.invoke(app, ["task", "submit", "sleep", "--param", "seconds=0"])
    result = runner.invoke(app, ["task", "worker", "--once"])
    assert result.exit_code == 0
    assert "traitée" in result.stdout


def test_task_cancel_queued_task(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    submit_result = runner.invoke(app, ["task", "submit", "sleep", "--param", "seconds=30"])
    task_id = submit_result.stdout.split("Tâche créée :")[1].split()[0]

    result = runner.invoke(app, ["task", "cancel", task_id])
    assert result.exit_code == 0
    assert "Annulation effectuée" in result.stdout
