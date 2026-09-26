"""
system/healthcheck.py — Auto-diagnostic minimal de S1M0NE (mega-prompt §23).

Combine : version Python, disponibilité SQLite, config chargée, DATA_DIR accessible en écriture,
état des ressources. Chaque vérification indique QUOI / POURQUOI KO si applicable.
"""

from __future__ import annotations

import sqlite3
import sys
from typing import Any

from core.config import settings
from core.db import database_health, init_db
from system.monitor import get_platform_info, get_snapshot, resource_level


def check_python_version(min_version: tuple[int, int] = (3, 11)) -> dict[str, Any]:
    ok = sys.version_info >= min_version
    return {
        "name": "python_version",
        "ok": ok,
        "detail": sys.version.split()[0],
        "reason": None if ok else f"Python >= {min_version[0]}.{min_version[1]} requis (tomllib)",
    }


def check_sqlite() -> dict[str, Any]:
    try:
        init_db()
        health = database_health()
        return {
            "name": "sqlite",
            "ok": health["ok"],
            "detail": health.get("path"),
            "reason": None if health["ok"] else f"Tables manquantes : {health.get('tables_missing')}",
        }
    except sqlite3.Error as exc:
        return {"name": "sqlite", "ok": False, "detail": None, "reason": str(exc)}


def check_data_dir_writable() -> dict[str, Any]:
    data_dir = settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        return {"name": "data_dir_writable", "ok": True, "detail": str(data_dir), "reason": None}
    except OSError as exc:
        return {
            "name": "data_dir_writable",
            "ok": False,
            "detail": str(data_dir),
            "reason": str(exc),
        }


def run_all_checks() -> dict[str, Any]:
    checks = [check_python_version(), check_data_dir_writable(), check_sqlite()]
    snapshot = get_snapshot()
    level = resource_level(snapshot)
    all_ok = all(c["ok"] for c in checks) and level != "CRITICAL"
    return {
        "overall_ok": all_ok,
        "resource_level": level,
        "checks": checks,
        "platform": get_platform_info(),
        "resources": snapshot.as_dict(),
    }
