"""
system/monitor.py — System Manager / Resource Manager (lecture seule) de S1M0NE.

Objectif (mega-prompt §17, §18) : donner un état matériel fiable, jamais inventé.
Utilise `psutil`, seule dépendance externe ajoutée ici (légère, native, largement utilisée,
compatible Linux Mint).

Ce module NE MODIFIE RIEN sur le système : lecture seule.
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from core.config import settings


@dataclass
class ResourceSnapshot:
    cpu_percent: float
    cpu_count_physical: int | None
    cpu_count_logical: int | None
    ram_total_gb: float
    ram_available_gb: float
    ram_percent_used: float
    swap_total_gb: float
    swap_used_gb: float
    swap_percent_used: float
    disk_total_gb: float
    disk_free_gb: float
    disk_percent_used: float

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def get_snapshot(disk_path: str | Path | None = None) -> ResourceSnapshot:
    """Interroge l'état réel de la machine. Ne suppose jamais de valeurs par défaut."""
    disk_target = str(disk_path) if disk_path else str(settings.data_dir.anchor or "/")
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    du = shutil.disk_usage(disk_target)

    return ResourceSnapshot(
        cpu_percent=psutil.cpu_percent(interval=0.2),
        cpu_count_physical=psutil.cpu_count(logical=False),
        cpu_count_logical=psutil.cpu_count(logical=True),
        ram_total_gb=round(vm.total / (1024**3), 2),
        ram_available_gb=round(vm.available / (1024**3), 2),
        ram_percent_used=vm.percent,
        swap_total_gb=round(sm.total / (1024**3), 2),
        swap_used_gb=round(sm.used / (1024**3), 2),
        swap_percent_used=sm.percent,
        disk_total_gb=round(du.total / (1024**3), 2),
        disk_free_gb=round(du.free / (1024**3), 2),
        disk_percent_used=round((du.used / du.total) * 100, 1) if du.total else 0.0,
    )


def resource_level(snapshot: ResourceSnapshot) -> str:
    """Classement simple pour le futur Resource Manager (§18) : NORMAL / WARNING / CRITICAL."""
    limits = settings.resource_limits
    ram_warn = limits.get("ram_warning_percent", 80)
    ram_crit = limits.get("ram_critical_percent", 92)
    swap_warn = limits.get("swap_warning_percent", 50)
    cpu_warn = limits.get("cpu_warning_percent", 90)

    if snapshot.ram_percent_used >= ram_crit:
        return "CRITICAL"
    if (
        snapshot.ram_percent_used >= ram_warn
        or snapshot.swap_percent_used >= swap_warn
        or snapshot.cpu_percent >= cpu_warn
    ):
        return "WARNING"
    return "NORMAL"


def get_platform_info() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }
