"""
core/permissions.py — Permission Manager de S1M0NE (Phase 9 : Sécurité).

Reprend la décision D10 de DECISIONS.md, posée dès la Phase 1 mais implémentée ici : toute
commande système réelle exécutée par S1M0NE (via `s1mone exec` en CLI ou `/api/exec` côté web)
passe par :

1. une LISTE BLANCHE stricte (`CATALOG` ci-dessous) — jamais de commande arbitraire, jamais
   `shell=True`, jamais d'interpolation de chaîne dans un appel shell ;
2. une classification à 4 niveaux **READ < WRITE < EXECUTE < ADMIN** — chaque commande du
   catalogue exige un niveau minimum, et l'appelant (CLI ou web) a un niveau plafond configurable
   (`config.toml [security]`) ;
3. une confirmation explicite obligatoire pour toute commande marquée `destructive=True`
   (rm, rmdir...) — jamais exécutée "à l'aveugle", conformément au mega-prompt.

Toutes les commandes qui acceptent un chemin sont en plus bornées à `Settings.fs_root` (par
défaut DATA_DIR) : impossible de sortir de ce périmètre, même au niveau ADMIN. On ne fait jamais
aveuglément confiance à un chemin fourni par l'utilisateur (mega-prompt §10/§31).

Ce module ne connaît PAS FastAPI ni Typer : il est utilisé identiquement par la CLI et le web
(mega-prompt §5 : un seul cerveau, plusieurs façades). L'exécution réelle est dans
`core/shell_runner.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from core.config import settings


class Permission(IntEnum):
    """Ordre croissant de confiance requise. READ < WRITE < EXECUTE < ADMIN."""

    READ = 1
    WRITE = 2
    EXECUTE = 3
    ADMIN = 4


class PermissionError_(Exception):
    """Le niveau de permission de l'appelant est insuffisant pour cette commande."""

    def __init__(self, command: str, required: Permission, have: Permission):
        self.command = command
        self.required = required
        self.have = have
        super().__init__(
            f"Commande '{command}' : niveau requis {required.name}, "
            f"niveau disponible {have.name}."
        )


class UnknownCommandError(Exception):
    """La commande demandée n'est pas dans la liste blanche."""

    def __init__(self, command: str):
        self.command = command
        super().__init__(
            f"Commande inconnue ou non autorisée : '{command}'. "
            f"Voir `s1mone exec list` pour la liste blanche complète."
        )


class ConfirmationRequiredError(Exception):
    """La commande est destructrice : elle exige une confirmation explicite avant exécution."""

    def __init__(self, command: str):
        self.command = command
        super().__init__(
            f"Commande destructrice '{command}' : confirmation explicite requise avant "
            "exécution."
        )


@dataclass(frozen=True)
class CommandSpec:
    name: str
    permission: Permission
    destructive: bool
    takes_path: bool
    description: str


# Liste blanche des commandes système réelles que S1M0NE sait exécuter (Phase 9).
# Volontairement modeste : pas de shutdown/reboot/dd/mkfs/chmod-chown massif ici — ces
# opérations réellement dangereuses pour la seule machine de l'utilisateur restent hors
# périmètre du produit, quel que soit le niveau de permission (voir DECISIONS.md D10 et
# README.md). Étendre ce catalogue reste possible plus tard (Phase 8 : plugins).
CATALOG: dict[str, CommandSpec] = {
    "pwd": CommandSpec("pwd", Permission.READ, False, False, "Affiche le répertoire courant (fs_root)."),
    "whoami": CommandSpec("whoami", Permission.READ, False, False, "Affiche l'utilisateur système."),
    "date": CommandSpec("date", Permission.READ, False, False, "Affiche la date/heure du système."),
    "uptime": CommandSpec("uptime", Permission.READ, False, False, "Affiche la charge et le temps de fonctionnement."),
    "df": CommandSpec("df", Permission.READ, False, False, "Espace disque disponible."),
    "free": CommandSpec("free", Permission.READ, False, False, "Mémoire RAM/swap disponible."),
    "ps": CommandSpec("ps", Permission.READ, False, False, "Liste les processus en cours."),
    "ls": CommandSpec("ls", Permission.READ, False, True, "Liste un dossier (borné à fs_root)."),
    "cat": CommandSpec("cat", Permission.READ, False, True, "Affiche un fichier (borné à fs_root)."),
    "mkdir": CommandSpec("mkdir", Permission.WRITE, False, True, "Crée un dossier (borné à fs_root)."),
    "touch": CommandSpec("touch", Permission.WRITE, False, True, "Crée/horodate un fichier (borné à fs_root)."),
    "cp": CommandSpec("cp", Permission.WRITE, False, True, "Copie un fichier (borné à fs_root)."),
    "mv": CommandSpec("mv", Permission.EXECUTE, False, True, "Déplace/renomme un fichier (borné à fs_root)."),
    "rmdir": CommandSpec("rmdir", Permission.ADMIN, True, True, "Supprime un dossier VIDE (borné à fs_root)."),
    "rm": CommandSpec("rm", Permission.ADMIN, True, True, "Supprime un fichier (borné à fs_root)."),
}


def parse_level(name: str) -> Permission:
    """Convertit une chaîne ('read', 'ADMIN', ...) en Permission. Lève ValueError sinon."""
    try:
        return Permission[str(name).strip().upper()]
    except KeyError as exc:
        valid = ", ".join(p.name for p in Permission)
        raise ValueError(f"Niveau de permission invalide : '{name}'. Valides : {valid}.") from exc


def cli_level() -> Permission:
    return parse_level(settings.cli_permission_level)


def web_level() -> Permission:
    return parse_level(settings.web_permission_level)


def get_command(name: str) -> CommandSpec:
    spec = CATALOG.get(name)
    if spec is None:
        raise UnknownCommandError(name)
    return spec


def check_access(name: str, level: Permission) -> CommandSpec:
    """Vérifie qu'une commande existe et que `level` suffit. Retourne son CommandSpec sinon
    lève UnknownCommandError / PermissionError_."""
    spec = get_command(name)
    if spec.permission > level:
        raise PermissionError_(name, spec.permission, level)
    return spec


def available_commands(level: Permission | None = None) -> list[CommandSpec]:
    """Catalogue trié par nom, filtré par niveau si fourni (sinon tout le catalogue)."""
    specs = sorted(CATALOG.values(), key=lambda s: s.name)
    if level is None:
        return specs
    return [s for s in specs if s.permission <= level]
