"""core/app_install.py — Installation réelle d'une app du catalogue de découverte (Catégorie G+).

Demande explicite de l'utilisateur : pouvoir installer POUR DE VRAI une des 100 apps du
catalogue statique (`core/discover.py`) — ou un résultat de la recherche en direct (`/search`,
Phase 5) — directement depuis S1M0NE, voir les lignes d'installation, puis utiliser le terminal
déjà existant de S1M0NE (`/terminal`, Phase 9) pour inspecter ce qui a été installé.

Choix de sécurité (mega-prompt §10/§31, même esprit que `core/permissions.py`/D10) :
- **Jamais `shell=True`, jamais d'interpolation de chaîne** : chaque commande est une liste
  d'arguments passée telle quelle à `subprocess.run`.
- **Toute installation est CONFINÉE sous `settings.fs_root/installed_apps/`** — jamais
  d'installation globale sur la machine (pas de `npm install -g`, pas de `pip install` dans le
  Python système ou dans le venv de S1MONE lui-même). C'est ce même dossier que le terminal
  existant de S1M0NE (`ls`/`cat`, bornés à `fs_root`) peut ensuite parcourir — d'où la demande de
  l'utilisateur "un terminal pour l'utiliser" est satisfaite par la réutilisation de l'existant,
  sans nouvelle surface d'exécution.
- **Confirmation explicite obligatoire** avant toute exécution réelle (`confirmed=True`), même
  logique que les commandes destructrices de `core/shell_runner.py`.
- **SourceForge n'est PAS installable automatiquement** : ces projets sont très majoritairement
  des logiciels Windows/binaires (WinSCP, KeePass, Ventoy...), pas des paquets ou dépôts qu'un
  gestionnaire de paquets sait installer proprement et sans risque. Honnêteté avant tout : on ne
  fait jamais semblant de savoir installer ce qu'on ne sait pas installer correctement. Le
  catalogue continue d'afficher le lien de téléchargement officiel pour ces entrées.
- **Avertissement assumé et affiché à l'utilisateur** : `npm install`/`pip install` exécutent du
  code tiers (scripts d'installation) par nature — comme n'importe quelle installation manuelle
  de ces écosystèmes. S1M0NE ne peut pas éliminer ce risque inhérent, seulement le confiner dans
  un dossier dédié et le rendre visible (sortie affichée intégralement, jamais masquée).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core import memory
from core.config import settings
from core.logging_setup import get_logger

logger = get_logger("s1mone.app_install")

INSTALL_TIMEOUT_SECONDS = 180.0

# Sites pour lesquels une installation réelle est proposée. SourceForge est volontairement absent
# (voir docstring du module).
INSTALLABLE_SITES = {"npm", "pypi", "github", "gitlab", "codeberg", "huggingface"}

# Domaine(s) officiel(s) attendu(s) pour l'URL de chaque site "dépôt git" — défense en
# profondeur : même si une URL provient d'un résultat de recherche en direct (pas seulement du
# catalogue statique), on refuse de cloner autre chose que le vrai site annoncé. GitLab a
# plusieurs préfixes valides : gitlab.com (recherche en direct, connectors/gitlab.py) ET les
# instances self-hosted présentes dans le catalogue statique (gitlab.gnome.org,
# gitlab.freedesktop.org — voir DECISIONS.md D22).
_GIT_HOSTS: dict[str, tuple[str, ...]] = {
    "github": ("https://github.com/",),
    "gitlab": ("https://gitlab.com/", "https://gitlab.gnome.org/", "https://gitlab.freedesktop.org/"),
    "codeberg": ("https://codeberg.org/",),
    "huggingface": ("https://huggingface.co/",),
}

# Nom de paquet npm/pypi : alphanumérique + . _ - @ / (paquets scoped npm type "@babel/core").
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@/-]{0,213}$")

_MEMORY_KEY = "installed_apps_log"
_MAX_LOG_ENTRIES = 200


class InstallConfirmationRequiredError(Exception):
    """Une installation réelle est destructrice/coûteuse par nature (réseau + exécution de code
    tiers) : elle exige une confirmation explicite, jamais faite \"à l'aveugle\"."""

    def __init__(self, site: str, name: str):
        self.site = site
        self.name = name
        super().__init__(
            f"Installation de '{name}' ({site}) : confirmation explicite requise avant "
            "exécution (cette action télécharge et exécute du code tiers)."
        )


class UnsupportedSiteError(Exception):
    """Le site demandé n'a pas d'installation automatique proposée (ex: SourceForge)."""

    def __init__(self, site: str):
        self.site = site
        super().__init__(
            f"Aucune installation automatique n'est proposée pour le site '{site}' — "
            "vérifie le lien de téléchargement officiel du projet."
        )


class InvalidNameError(Exception):
    """Le nom du paquet/dépôt ne respecte pas le format attendu."""


class InvalidUrlError(Exception):
    """L'URL fournie ne correspond pas au domaine officiel attendu pour ce site."""


def _safe_dir_name(name: str) -> str:
    return name.replace("/", "__").replace("@", "at_")


def install_dir_for(site: str, name: str) -> Path:
    """Dossier dédié et confiné à `fs_root/installed_apps/<site>/<nom_sûr>`."""
    return settings.fs_root / "installed_apps" / site / _safe_dir_name(name)


def build_command(site: str, name: str, url: str | None, dest: Path) -> list[str]:
    """Construit la commande d'installation réelle (liste d'arguments, jamais une chaîne shell)."""
    if site == "npm":
        return ["npm", "install", name, "--prefix", str(dest)]
    if site == "pypi":
        return [sys.executable, "-m", "pip", "install", name, "--target", str(dest)]
    if site in _GIT_HOSTS:
        allowed_prefixes = _GIT_HOSTS[site]
        if not url or not url.startswith(allowed_prefixes):
            raise InvalidUrlError(
                f"URL invalide pour le site '{site}' : attendu un lien commençant par l'un de "
                f"{allowed_prefixes}, reçu '{url}'."
            )
        return ["git", "clone", "--depth", "1", url, str(dest)]
    raise UnsupportedSiteError(site)


def _subprocess_env(site: str) -> dict[str, str]:
    """Environnement transmis à la commande d'installation.

    **Protection LOW RESOURCE FIRST spécifique à `git clone`** : certains dépôts (surtout
    Hugging Face, où les poids de modèles font parfois plusieurs dizaines de Go — Llama-3.1-8B,
    FLUX.1-dev, DeepSeek-R1...) utilisent Git LFS. Si `git-lfs` est installé et configuré sur la
    machine de l'utilisateur, un `git clone` classique télécharge AUTOMATIQUEMENT tous les
    fichiers volumineux — risque réel de saturer une machine faible en disque/bande passante en
    un seul clic. `GIT_LFS_SKIP_SMUDGE=1` force le clone à ne récupérer que de petits fichiers
    pointeurs (quelques Ko), jamais les poids réels — vérifié en sandbox : un clone Hugging Face
    passe de plusieurs Go potentiels à quelques Mo. L'utilisateur qui veut vraiment les poids
    complets doit ensuite lancer `git lfs pull` lui-même dans le dossier installé, en toute
    connaissance de cause (jamais une action aussi lourde ne doit être déclenchée en un clic
    sans que l'utilisateur sache ce qu'il télécharge)."""
    env = dict(os.environ)
    if site in _GIT_HOSTS:
        env["GIT_LFS_SKIP_SMUDGE"] = "1"
    return env


def _record(entry: dict[str, Any]) -> None:
    log = memory.recall("persistent", _MEMORY_KEY, default=[])
    log.append(entry)
    memory.remember("persistent", _MEMORY_KEY, log[-_MAX_LOG_ENTRIES:])


def list_installed() -> list[dict[str, Any]]:
    """Historique des installations effectuées via S1M0NE (plus récent en premier)."""
    log = memory.recall("persistent", _MEMORY_KEY, default=[])
    return list(reversed(log))


def install_app(
    site: str,
    name: str,
    url: str | None = None,
    *,
    confirmed: bool = False,
    timeout: float = INSTALL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Installe réellement `name` (site `site`) dans un dossier confiné sous `fs_root`.

    Lève (avant toute exécution) :
    - `UnsupportedSiteError` si le site n'a pas d'installation automatique (SourceForge).
    - `InvalidNameError` si `name` contient des caractères inattendus.
    - `InvalidUrlError` si `url` ne correspond pas au domaine officiel du site.
    - `InstallConfirmationRequiredError` si `confirmed` n'est pas `True`.

    Retourne un dict {ok, command_display, output, install_dir, exit_code, duration_seconds} —
    `output` contient TOUJOURS la sortie complète (stdout+stderr), succès ou échec, jamais
    masquée.
    """
    if site not in INSTALLABLE_SITES:
        raise UnsupportedSiteError(site)
    if not _NAME_RE.match(name):
        raise InvalidNameError(f"Nom de paquet/dépôt invalide : '{name}'.")
    if not confirmed:
        raise InstallConfirmationRequiredError(site, name)

    dest = install_dir_for(site, name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(site, name, url, dest)
    command_display = " ".join(command)

    logger.info(f"Installation réelle démarrée : {command_display}")
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_subprocess_env(site),
        )
        output = (result.stdout or "") + (result.stderr or "")
        ok = result.returncode == 0
        exit_code = result.returncode
    except FileNotFoundError as exc:
        output = f"Commande introuvable sur cette machine : {exc}"
        ok = False
        exit_code = None
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") + (exc.stderr or "")
        output = f"{partial}\n[Interrompu après {timeout:.0f}s — délai d'installation dépassé]"
        ok = False
        exit_code = None
    duration = time.monotonic() - started

    entry = {
        "site": site,
        "name": name,
        "url": url,
        "command_display": command_display,
        "install_dir": str(dest),
        "ok": ok,
        "exit_code": exit_code,
        "installed_at": time.time(),
        "duration_seconds": round(duration, 1),
    }
    _record(entry)
    logger.info(f"Installation terminée ({'ok' if ok else 'échec'}) : {command_display}")

    return {
        "ok": ok,
        "command_display": command_display,
        "output": output,
        "install_dir": str(dest),
        "exit_code": exit_code,
        "duration_seconds": round(duration, 1),
    }
