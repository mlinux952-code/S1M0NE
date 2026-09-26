"""Tests du System Manager (Phase 1, étape 3)."""

from system.healthcheck import run_all_checks
from system.monitor import get_snapshot, resource_level


def test_snapshot_returns_plausible_values():
    snap = get_snapshot()
    assert snap.ram_total_gb > 0
    assert 0 <= snap.ram_percent_used <= 100
    assert snap.disk_total_gb > 0


def test_resource_level_is_one_of_expected_values():
    snap = get_snapshot()
    assert resource_level(snap) in {"NORMAL", "WARNING", "CRITICAL"}


def test_run_all_checks_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("S1MONE_DATA_DIR", str(tmp_path))
    report = run_all_checks()
    names = {c["name"] for c in report["checks"]}
    assert {"python_version", "data_dir_writable", "sqlite"}.issubset(names)
    assert "resource_level" in report
    assert "resources" in report
