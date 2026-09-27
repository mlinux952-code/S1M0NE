"""
core/shell_runner.py — Exécution réelle des commandes système en liste blanche (Phase 9).

Règles non négociables (mega-prompt §10/§15/§31, DECISIONS.md D10) :
- Jamais `shell=True`, jamais de commande construite par interpolation de chaîne.
- Uniquement les commandes de `core.permissions.CATALOG`, avec vérification du niveau de
  permission de l'appelant AVANT toute exécution.
- Tout argument qui ressemble à un chemin est résolu et vérifié : il doit rester strictement
  à l'intérieur de `fs_root` (par défaut DATA_DIR), sinon on refuse — même au niveau ADMIN.
- Toute commande `destructive=True` exige `confirmed=True` explicite, sinon
  `ConfirmationRequiredError` est levée AVANT toute exécution (rien n'est jamais fait "au cas où").
- Timeout systématique : une commande qui ne répond pas ne bloque jamais S1M0NE indéfiniment.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.permissions import (
    ConfirmationRequiredError,
    Permission,
    check_access,
)

DEFAULT_TIMEOUT_SECONDS = 10.0


def _resolve_and_check_path(raw: str, root: Path) -> Path:
    """Résout `raw` par rapport à `root` et garantit qu'il ne s'en échappe pas (même via '..'
    ou un chemin absolu). Lève ValueError sinon."""
    root_resolved = root.resolve()
    candidate = Path(raw)
    candidate = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise ValueError(
            f"Chemin hors du périmètre autorisé ('{root_resolved}') : '{raw}'. "
            "Toutes les commandes de fichiers de S1M0NE sont bornées à fs_root (voir la section "
            "security de config.toml)."
        ) from None
    return candidate


def run_command(
    raw_command: str,
    *,
    level: Permission,
    fs_root: Path,
    confirmed: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Analyse, valide puis exécute `raw_command` (ex: "ls sous_dossier").

    Lève (avant toute exécution) :
    - UnknownCommandError si la commande n'est pas dans la liste blanche.
    - PermissionError_ si `level` est insuffisant.
    - ValueError si un argument-chemin sort de `fs_root`.
    - ConfirmationRequiredError si la commande est destructrice et `confirmed=False`.
    """
    tokens = shlex.split(raw_command)
    if not tokens:
        raise ValueError("Commande vide.")
    name, args = tokens[0], tokens[1:]

    spec = check_access(name, level)

    if spec.destructive and not confirmed:
        raise ConfirmationRequiredError(name)

    validated_args: list[str] = []
    fs_root = fs_root.resolve()
    fs_root.mkdir(parents=True, exist_ok=True)
    for arg in args:
        if spec.takes_path and not arg.startswith("-"):
            resolved = _resolve_and_check_path(arg, fs_root)
            # On repasse un chemin relatif à fs_root (cwd du sous-processus) plutôt que le
            # chemin absolu résolu : plus lisible dans la sortie, comportement identique.
            try:
                validated_args.append(str(resolved.relative_to(fs_root)) or ".")
            except ValueError:
                validated_args.append(str(resolved))
        else:
            validated_args.append(arg)

    full_command = [name, *validated_args]
    try:
        completed = subprocess.run(
            full_command,
            cwd=str(fs_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            f"Le binaire '{name}' est absent de ce système (liste blanche S1M0NE, mais "
            "l'exécutable réel n'est pas installé)."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        return {
            "command": raw_command,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Commande interrompue après {timeout}s (timeout de sécurité).",
            "timed_out": True,
        }

    return {
        "command": raw_command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "timed_out": False,
    }
