"""core/app_run.py — Exécution RÉELLE et confinée d'une app déjà installée (Catégorie G++).

Suite explicite de la Catégorie G+ (`core/app_install.py`) : l'utilisateur peut désormais
installer réellement une app (npm/pip/git), mais S1M0NE ne pouvait pas l'exécuter — seulement
l'inspecter via le terminal existant (`ls`/`cat`, Phase 9). L'utilisateur a proposé une
"machine virtuelle" ; décision retenue après recherche concrète (voir DECISIONS.md D24) : pas de
VM (beaucoup trop lourd pour une machine à 4 Go de RAM), mais **Firejail** — un sandbox Linux
léger (namespaces + seccomp, aucun daemon, quelques Mo, overhead mémoire quasi nul) déjà
disponible dans les dépôts standards (`apt install firejail` / `dnf install firejail` /
`pacman -S firejail`).

Garanties de sécurité (même esprit que D10/D23 — jamais de confiance aveugle) :
- **Sandbox obligatoire, jamais de repli silencieux en exécution non confinée** : si `firejail`
  n'est pas installé sur la machine, on refuse d'exécuter et on l'affiche clairement à
  l'utilisateur (avec la commande d'installation), plutôt que de lancer le code en clair "pour
  que ça marche quand même".
- **Vue disque restreinte** (`--private=<dossier installé>`) : le processus sandboxé ne voit QUE
  le dossier de l'app installée comme "home" — ni le reste de `fs_root`, ni les vrais fichiers
  personnels de l'utilisateur, ni le code de S1M0NE lui-même. Vérifié manuellement (une app
  sandboxée ne peut pas lire `S1M0NE/.env` ni lister `/home/<user>` réel).
- **Réseau coupé par défaut** (`--net=none`) : une app installée ne doit pas pouvoir "téléphoner
  à la maison" sans que l'utilisateur l'ait explicitement autorisé (case à cocher dédiée, jamais
  cochée par défaut). Vérifié manuellement (accès réseau lève bien une erreur DNS/connexion).
- **Capacités système supprimées** (`--caps.drop=all --nonewprivs --seccomp`) et **limites de
  ressources strictes** (`--rlimit-as` mémoire, `--rlimit-cpu` temps CPU, `--rlimit-nproc`
  nombre de process) — cohérent avec la contrainte "machine à 4 Go de RAM" : une app qui
  boucle ou fuit de la mémoire ne peut pas mettre la machine à genoux. Vérifié manuellement
  (allocation de 2 Go refusée avec une limite à 512 Mo ; boucle infinie tuée après quelques
  secondes de CPU).
- **Interpréteur en liste blanche** (`RUNNERS`) : comme `core/shell_runner.py`, seul un
  interpréteur reconnu (python3, node, npm, java, ruby, php, perl) peut être lancé — jamais une
  chaîne shell arbitraire construite par interpolation.
- **Confirmation explicite obligatoire**, même logique que `core/app_install.py`.
- **Effet de bord connu de Firejail, documenté et sans risque** : `--private=<dossier>` peut
  copier des fichiers de config par défaut (`.bashrc`, `.inputrc`) dans ce dossier au premier
  lancement s'ils n'y sont pas déjà — vérifié : ce sont des modèles génériques (pas les vrais
  fichiers de l'utilisateur), inoffensifs.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core import memory
from core.app_install import _NAME_RE, install_dir_for
from core.logging_setup import get_logger

logger = get_logger("s1mone.app_run")

RUN_TIMEOUT_SECONDS = 60.0
DEFAULT_MEMORY_MB = 512
DEFAULT_CPU_SECONDS = 30
DEFAULT_NPROC = 64

# Interpréteurs reconnus pour lancer un fichier d'une app installée. Volontairement modeste (même
# philosophie que core/permissions.py) : pas de shell générique (bash/sh) pour l'instant — peut
# être étendu plus tard sur demande explicite.
RUNNERS: tuple[str, ...] = ("python3", "python", "node", "npm", "java", "ruby", "php", "perl")

_MEMORY_KEY = "run_apps_log"
_MAX_LOG_ENTRIES = 200
# La sortie est conservée dans l'historique (contrairement à app_install.py) car c'est le SEUL
# endroit où elle reste visible après coup côté web : contrairement au résultat "live" affiché
# juste après avoir cliqué "Lancer" (qui disparaît si la page est rechargée ou quittée), cet
# historique persiste réellement (core.memory, niveau persistent) — demande explicite de
# l'utilisateur après un signalement "je ne vois rien" (le résultat était bien là, mais éphémère).
_MAX_OUTPUT_CHARS = 4000


class RunConfirmationRequiredError(Exception):
    """Exécuter du code déjà installé reste une action à risque (par nature) : confirmation
    explicite requise avant toute exécution, jamais faite "à l'aveugle"."""

    def __init__(self, site: str, name: str):
        self.site = site
        self.name = name
        super().__init__(
            f"Exécution de '{name}' ({site}) : confirmation explicite requise avant "
            "lancement (le code sandboxé s'exécute réellement, même confiné)."
        )


class NotInstalledError(Exception):
    """Le dossier de l'app n'existe pas : elle n'a jamais été installée via S1M0NE."""

    def __init__(self, site: str, name: str, install_dir: Path):
        self.site = site
        self.name = name
        super().__init__(
            f"'{name}' ({site}) n'est pas installé (dossier introuvable : {install_dir}). "
            "Installe-la d'abord via `s1mone discover install`."
        )


class UnknownRunnerError(Exception):
    """L'interpréteur demandé n'est pas dans la liste blanche RUNNERS."""

    def __init__(self, runner: str):
        self.runner = runner
        super().__init__(
            f"Interpréteur inconnu ou non autorisé : '{runner}'. Autorisés : {', '.join(RUNNERS)}."
        )


class InvalidEntryError(Exception):
    """Le fichier d'entrée sort du dossier confiné de l'app installée."""


class SandboxUnavailableError(Exception):
    """Firejail n'est pas installé sur cette machine — on refuse d'exécuter sans sandbox plutôt
    que de lancer le code en clair."""

    def __init__(self):
        super().__init__(
            "Firejail n'est pas installé sur cette machine — S1M0NE refuse d'exécuter du code "
            "installé sans sandbox. Installe-le avec : "
            "`sudo apt install firejail` (Debian/Ubuntu), `sudo dnf install firejail` (Fedora) "
            "ou `sudo pacman -S firejail` (Arch)."
        )


def _resolve_entry(entry: str, install_dir: Path) -> Path:
    """Résout `entry` par rapport à `install_dir` et garantit qu'il n'en sort pas (même via
    '..' ou un chemin absolu)."""
    install_dir = install_dir.resolve()
    candidate = Path(entry)
    candidate = candidate.resolve() if candidate.is_absolute() else (install_dir / candidate).resolve()
    try:
        candidate.relative_to(install_dir)
    except ValueError:
        raise InvalidEntryError(
            f"Le fichier '{entry}' sort du dossier de l'app installée ({install_dir})."
        ) from None
    return candidate


def build_command(
    runner: str,
    install_dir: Path,
    entry: str,
    args: list[str],
    *,
    firejail_bin: str,
    network: bool,
    memory_mb: int,
    cpu_seconds: int,
) -> list[str]:
    """Construit la commande sandboxée (liste d'arguments, jamais une chaîne shell)."""
    if runner not in RUNNERS:
        raise UnknownRunnerError(runner)
    entry_path = _resolve_entry(entry, install_dir)
    entry_rel = str(entry_path.relative_to(install_dir.resolve()))

    firejail_flags = [
        "--quiet",
        "--noprofile",
        "--private-tmp",
        "--caps.drop=all",
        "--nonewprivs",
        "--seccomp",
        f"--rlimit-as={memory_mb * 1024 * 1024}",
        f"--rlimit-cpu={cpu_seconds}",
        f"--rlimit-nproc={DEFAULT_NPROC}",
        f"--private={install_dir.resolve()}",
    ]
    if not network:
        firejail_flags.append("--net=none")

    return [firejail_bin, *firejail_flags, "--", runner, entry_rel, *args]


def _record(entry: dict[str, Any]) -> None:
    log = memory.recall("persistent", _MEMORY_KEY, default=[])
    log.append(entry)
    memory.remember("persistent", _MEMORY_KEY, log[-_MAX_LOG_ENTRIES:])


def list_runs() -> list[dict[str, Any]]:
    """Historique des exécutions effectuées via S1M0NE (plus récent en premier)."""
    log = memory.recall("persistent", _MEMORY_KEY, default=[])
    return list(reversed(log))


def run_app(
    site: str,
    name: str,
    runner: str,
    entry: str,
    args: list[str] | None = None,
    *,
    network: bool = False,
    memory_mb: int = DEFAULT_MEMORY_MB,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    confirmed: bool = False,
    timeout: float = RUN_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Exécute `entry` (fichier de l'app `name`/`site` déjà installée) via `runner`, sandboxé
    par Firejail.

    Lève (avant toute exécution) :
    - `InvalidNameError` (réutilisée d'`app_install`) si `name` contient des caractères inattendus.
    - `NotInstalledError` si le dossier de l'app n'existe pas.
    - `UnknownRunnerError` si `runner` n'est pas dans la liste blanche.
    - `InvalidEntryError` si `entry` sort du dossier confiné.
    - `RunConfirmationRequiredError` si `confirmed` n'est pas `True`.
    - `SandboxUnavailableError` si Firejail n'est pas installé.

    Retourne un dict {ok, command_display, output, exit_code, duration_seconds, timed_out} —
    `output` contient TOUJOURS la sortie complète (stdout+stderr), succès ou échec.
    """
    from core.app_install import InvalidNameError  # import tardif pour éviter un cycle

    if not _NAME_RE.match(name):
        raise InvalidNameError(f"Nom de paquet/dépôt invalide : '{name}'.")

    install_dir = install_dir_for(site, name)
    if not install_dir.is_dir():
        raise NotInstalledError(site, name, install_dir)

    if not confirmed:
        raise RunConfirmationRequiredError(site, name)

    firejail_bin = shutil.which("firejail")
    if not firejail_bin:
        raise SandboxUnavailableError()

    args = args or []
    command = build_command(
        runner,
        install_dir,
        entry,
        args,
        firejail_bin=firejail_bin,
        network=network,
        memory_mb=memory_mb,
        cpu_seconds=cpu_seconds,
    )
    command_display = " ".join(shlex.quote(c) for c in [runner, entry, *args])

    logger.info(f"Exécution sandboxée démarrée ({site}/{name}) : {command_display}")
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            cwd=str(install_dir.resolve()),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        output = (result.stdout or "") + (result.stderr or "")
        ok = result.returncode == 0
        exit_code = result.returncode
    except FileNotFoundError:
        output = "Firejail introuvable au moment de l'exécution (a-t-il été désinstallé ?)."
        ok = False
        exit_code = None
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "")
        output = f"{partial}\n[Interrompu après {timeout:.0f}s — délai d'exécution dépassé]"
        ok = False
        exit_code = None
        timed_out = True
    duration = time.monotonic() - started

    output_for_log = output
    truncated = len(output) > _MAX_OUTPUT_CHARS
    if truncated:
        output_for_log = output[:_MAX_OUTPUT_CHARS] + "\n[...sortie tronquée, voir les logs...]"

    entry_log = {
        "site": site,
        "name": name,
        "runner": runner,
        "entry": entry,
        "args": args,
        "network": network,
        "command_display": command_display,
        "ok": ok,
        "exit_code": exit_code,
        "output": output_for_log,
        "output_truncated": truncated,
        "run_at": time.time(),
        "duration_seconds": round(duration, 1),
    }
    _record(entry_log)
    logger.info(f"Exécution terminée ({'ok' if ok else 'échec'}) : {command_display}")

    return {
        "ok": ok,
        "command_display": command_display,
        "output": output,
        "exit_code": exit_code,
        "duration_seconds": round(duration, 1),
        "timed_out": timed_out,
    }
