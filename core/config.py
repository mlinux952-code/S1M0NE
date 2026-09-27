"""
core/config.py — Configuration Manager de S1M0NE.

Règles appliquées (mega-prompt §10, §19, §22) :
- Les réglages non sensibles vivent dans config/config.toml.
- Les secrets vivent uniquement dans .env (jamais committé, jamais affiché dans les logs).
- Les variables d'environnement (.env ou export shell) ont toujours priorité sur config.toml.
- Aucune valeur sensible n'est jamais écrite en clair dans les logs (voir core/logging_setup.py).
- On ne suppose jamais qu'un chemin/disque existe : c'est vérifié à l'usage (voir system/).

Pas de dépendance externe : lecture TOML via `tomllib` (stdlib depuis Python 3.11),
lecture .env via un petit parseur maison (évite d'ajouter python-dotenv pour ~15 lignes de code).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.toml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

# Clés considérées sensibles : ne doivent jamais apparaître en clair dans les logs.
SENSITIVE_KEY_HINTS = ("token", "key", "secret", "password", "passwd")


def _require_tomllib():
    if sys.version_info < (3, 11):
        raise RuntimeError(
            "S1M0NE nécessite Python >= 3.11 (module 'tomllib' requis pour lire config.toml). "
            f"Version détectée : {sys.version}. "
            "Lance scripts/audit_system.sh pour vérifier ta version de Python."
        )
    import tomllib  # noqa: F401 - juste pour valider la disponibilité


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Fichier de configuration introuvable : {path}. "
            "Copie config/config.toml.example si besoin, ou vérifie ton chemin."
        )
    _require_tomllib()
    import tomllib

    with path.open("rb") as f:
        return tomllib.load(f)


def _load_env_file(path: Path) -> dict[str, str]:
    """Parseur .env minimal : KEY=VALUE, ignore lignes vides et commentaires (#)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _mask_if_sensitive(key: str, value: Any) -> Any:
    if isinstance(value, str) and any(hint in key.lower() for hint in SENSITIVE_KEY_HINTS):
        return "***MASKED***"
    return value


@dataclass
class Settings:
    raw_toml: dict[str, Any] = field(default_factory=dict)
    env_values: dict[str, str] = field(default_factory=dict)

    # --- accès pratiques, avec valeurs par défaut sûres ---

    @property
    def data_dir(self) -> Path:
        override = self.env_values.get("S1MONE_DATA_DIR") or os.environ.get("S1MONE_DATA_DIR")
        if override:
            return Path(override).expanduser()
        relative = self.raw_toml.get("storage", {}).get("data_dir", "data")
        return (PROJECT_ROOT / relative).resolve()

    @property
    def logs_dir(self) -> Path:
        relative = self.raw_toml.get("storage", {}).get("logs_dir", "logs")
        return (PROJECT_ROOT / relative).resolve()

    @property
    def cache_dir(self) -> Path:
        relative = self.raw_toml.get("storage", {}).get("cache_dir", "data/cache")
        return (PROJECT_ROOT / relative).resolve()

    @property
    def db_path(self) -> Path:
        filename = self.raw_toml.get("database", {}).get("filename", "s1mone.db")
        return self.data_dir / filename

    @property
    def log_level(self) -> str:
        override = self.env_values.get("S1MONE_LOG_LEVEL") or os.environ.get("S1MONE_LOG_LEVEL")
        if override:
            return override.upper()
        return str(self.raw_toml.get("logging", {}).get("level", "INFO")).upper()

    @property
    def log_max_bytes(self) -> int:
        return int(self.raw_toml.get("logging", {}).get("max_bytes", 1_048_576))

    @property
    def log_backup_count(self) -> int:
        return int(self.raw_toml.get("logging", {}).get("backup_count", 3))

    @property
    def resource_limits(self) -> dict[str, Any]:
        return self.raw_toml.get("resource_limits", {})

    @property
    def cache_default_ttl_seconds(self) -> int:
        return int(self.raw_toml.get("cache", {}).get("default_ttl_seconds", 300))

    @property
    def ai_default_provider(self) -> str:
        """Fournisseur IA utilisé quand aucun n'est précisé explicitement (CLI --provider,
        API ?provider=...). L'environnement (.env ou export shell) a priorité sur config.toml."""
        override = self.env_values.get("AI_DEFAULT_PROVIDER") or os.environ.get(
            "AI_DEFAULT_PROVIDER"
        )
        if override:
            return override
        return str(self.raw_toml.get("ai", {}).get("default_provider", "") or "")

    def ai_provider_model(self, provider_name: str) -> str | None:
        """Surcharge de modèle pour un fournisseur donné (config.toml [ai.<provider>] model=...).

        Retourne None si rien n'est configuré : le fournisseur utilisera alors son propre
        `default_model` codé en dur (voir ai/providers/*.py).
        """
        ai_section = self.raw_toml.get("ai", {})
        provider_section = ai_section.get(provider_name, {}) if isinstance(ai_section, dict) else {}
        if isinstance(provider_section, dict):
            model = provider_section.get("model")
            if model:
                return str(model)
        return None

    @property
    def cli_permission_level(self) -> str:
        """Niveau de permission du terminal local (CLI) pour les commandes système réelles
        (Phase 9 - Sécurité). Par défaut ADMIN : le terminal local est lancé par le propriétaire
        de la machine, sur sa propre session — c'est la même confiance qu'un shell classique."""
        override = self.env_values.get("S1MONE_CLI_PERMISSION_LEVEL") or os.environ.get(
            "S1MONE_CLI_PERMISSION_LEVEL"
        )
        if override:
            return override
        return str(self.raw_toml.get("security", {}).get("cli_permission_level", "ADMIN"))

    @property
    def web_permission_level(self) -> str:
        """Niveau de permission du terminal web pour les commandes système réelles (Phase 9).
        Par défaut READ SEULEMENT : contrairement au terminal local, l'interface web peut être
        atteinte depuis n'importe quelle machine du réseau local (host='0.0.0.0') sans
        authentification — on part du principe le plus prudent, l'utilisateur peut l'élever
        explicitement dans config.toml s'il fait confiance à son réseau."""
        override = self.env_values.get("S1MONE_WEB_PERMISSION_LEVEL") or os.environ.get(
            "S1MONE_WEB_PERMISSION_LEVEL"
        )
        if override:
            return override
        return str(self.raw_toml.get("security", {}).get("web_permission_level", "READ"))

    @property
    def fs_root(self) -> Path:
        """Racine du système de fichiers à laquelle sont bornées TOUTES les commandes système
        qui manipulent des chemins (ls, cat, mkdir, touch, cp, mv, rm — Phase 9). Par défaut
        DATA_DIR : le bac à sable propre de S1M0NE, jamais le disque entier. Configurable
        (`[security] fs_root` dans config.toml) si l'utilisateur veut élargir le périmètre en
        connaissance de cause."""
        override = self.raw_toml.get("security", {}).get("fs_root")
        if override:
            return Path(override).expanduser().resolve()
        return self.data_dir

    @property
    def require_confirmation_for_dangerous_commands(self) -> bool:
        return bool(
            self.raw_toml.get("security", {}).get(
                "require_confirmation_for_dangerous_commands", True
            )
        )

    @property
    def plugins_dir(self) -> Path:
        """Dossier surveillé pour les plugins locaux (Phase 8) : tout fichier .py posé ici est
        chargé au démarrage. Par défaut `plugins_local/` à la racine du projet (voir
        plugins_local/README.md). Configurable (`[plugins] dir` dans config.toml, ou
        $S1MONE_PLUGINS_DIR)."""
        override = self.env_values.get("S1MONE_PLUGINS_DIR") or os.environ.get(
            "S1MONE_PLUGINS_DIR"
        )
        if override:
            return Path(override).expanduser().resolve()
        relative = self.raw_toml.get("plugins", {}).get("dir", "plugins_local")
        return (PROJECT_ROOT / relative).resolve()

    @property
    def backups_dir(self) -> Path:
        """Dossier des sauvegardes SQLite (NEXT_STEPS.md §A.2). Par défaut `data/backups`
        (configurable : `[backup] dir` dans config.toml)."""
        relative = self.raw_toml.get("backup", {}).get("dir", "data/backups")
        return (PROJECT_ROOT / relative).resolve()

    @property
    def backups_keep(self) -> int:
        """Nombre de sauvegardes conservées avant purge automatique des plus anciennes."""
        return int(self.raw_toml.get("backup", {}).get("keep", 10))

    @property
    def web_password(self) -> str | None:
        """Mot de passe du terminal web (NEXT_STEPS.md §A.1). Uniquement via .env/environnement
        (jamais config.toml, jamais loggué en clair — voir SENSITIVE_KEY_HINTS). Si absent,
        l'interface web reste ouverte sans authentification (comportement historique, un
        avertissement est affiché au démarrage de `s1mone web`)."""
        return self.get_secret("S1MONE_WEB_PASSWORD") or None

    @property
    def web_auth_enabled(self) -> bool:
        return bool(self.web_password)

    def get_secret(self, name: str, default: str | None = None) -> str | None:
        """Lit un secret : priorité à l'environnement système, puis .env, jamais config.toml."""
        return os.environ.get(name) or self.env_values.get(name) or default

    def as_safe_dict(self) -> dict[str, Any]:
        """Représentation sûre pour affichage/logs (secrets masqués)."""
        safe: dict[str, Any] = {}
        for section, values in self.raw_toml.items():
            if isinstance(values, dict):
                safe[section] = {k: _mask_if_sensitive(k, v) for k, v in values.items()}
            else:
                safe[section] = _mask_if_sensitive(section, values)
        safe["_env_keys_present"] = sorted(self.env_values.keys())
        return safe


def load_settings(
    config_path: Path | None = None, env_path: Path | None = None
) -> Settings:
    config_path = config_path or DEFAULT_CONFIG_PATH
    env_path = env_path or DEFAULT_ENV_PATH
    raw_toml = _load_toml(config_path)
    env_values = _load_env_file(env_path)
    return Settings(raw_toml=raw_toml, env_values=env_values)


# Instance par défaut, chargée une seule fois, utilisée par le reste de l'app.
settings = load_settings()
