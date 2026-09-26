"""core/timeutil.py — formatage de date/heure partagé entre la CLI et le Web (Phase 3).

Évite de dupliquer la logique de formatage : un seul cerveau, plusieurs façades
(mega-prompt §5). Avant cette extraction, la CLI formatait les timestamps en HH:MM:SS
via un helper privé, tandis que le panneau web affichait les timestamps Unix bruts
(illisibles) — bug réel constaté sur la machine réelle de l'utilisateur.
"""

from __future__ import annotations

from datetime import datetime


def format_timestamp(ts: float | None) -> str:
    """Formate un timestamp Unix en heure locale lisible (HH:MM:SS), ou '-' si absent/nul."""
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
