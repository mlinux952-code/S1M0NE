"""
plugins/manager.py — Chargement et invocation des plugins tiers (Phase 8).

Découverte, dans cet ordre :
1. Paquets pip installés exposant un entry point du groupe "s1mone" (`pm.load_setuptools_entrypoints`).
2. Fichiers `.py` déposés directement dans `Settings.plugins_dir` (par défaut `plugins_local/` à
   la racine du projet), chargés un par un et enregistrés sous leur nom de fichier.

Un plugin cassé (erreur d'import, exception dans un hook) est capturé et loggué : il ne doit
JAMAIS empêcher S1M0NE de démarrer ou de fonctionner (même philosophie de dégradation gracieuse
que `connectors/engine.py` pour les connecteurs de recherche). Limite connue et documentée
(DECISIONS.md) : si PLUSIEURS plugins implémentent le même hook, une exception dans l'un d'eux
peut empêcher les suivants de répondre pour cet appel précis — le cœur de S1M0NE n'est jamais
affecté, seule la contribution des plugins pour ce tour l'est.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import pluggy

from core.config import settings
from core.logging_setup import get_logger
from plugins.hookspecs import HOOK_NAMESPACE, S1moneHookSpecs, hookimpl, hookspec

__all__ = ["hookimpl", "hookspec", "get_plugin_manager", "reset_plugin_manager", "list_plugins",
           "plugin_connectors", "plugin_task_handlers"]

logger = get_logger("s1mone.plugins")

_manager: pluggy.PluginManager | None = None
_local_plugin_names: set[str] = set()


def _load_local_plugin_files(pm: pluggy.PluginManager) -> None:
    plugins_dir = settings.plugins_dir
    if not plugins_dir.is_dir():
        return
    for path in sorted(plugins_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue  # convention : préfixer par '_' pour désactiver un plugin sans le supprimer
        module_name = f"s1mone_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"impossible de créer le spec d'import pour {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            pm.register(module, name=path.stem)
            _local_plugin_names.add(path.stem)
            logger.info(f"Plugin local chargé : '{path.stem}' ({path}).")
        except Exception as exc:  # noqa: BLE001 - un plugin cassé ne doit jamais bloquer S1M0NE
            logger.error(f"Échec du chargement du plugin local '{path.name}' : {exc}")


def get_plugin_manager() -> pluggy.PluginManager:
    """Construit (une seule fois par processus) et retourne le PluginManager Pluggy de S1M0NE."""
    global _manager
    if _manager is not None:
        return _manager
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.add_hookspecs(S1moneHookSpecs)
    try:
        pm.load_setuptools_entrypoints(HOOK_NAMESPACE)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Échec de la découverte des plugins installés (entry points) : {exc}")
    _load_local_plugin_files(pm)
    _manager = pm
    return pm


def reset_plugin_manager() -> None:
    """Force un rechargement complet au prochain appel de `get_plugin_manager()`. Utilisé par
    les tests (chaque test peut pointer `plugins_dir` vers un dossier temporaire différent)."""
    global _manager
    _manager = None
    _local_plugin_names.clear()


def list_plugins() -> list[dict[str, Any]]:
    """Liste les plugins chargés (nom, origine, hooks implémentés) — pour `s1mone plugin list`
    et `/api/plugins`."""
    pm = get_plugin_manager()
    out: list[dict[str, Any]] = []
    for name, plugin in pm.list_name_plugin():
        hooks = [h for h in ("s1mone_connectors", "s1mone_task_handlers") if hasattr(plugin, h)]
        out.append(
            {
                "name": name,
                "source": "fichier local" if name in _local_plugin_names else "paquet installé",
                "hooks": hooks,
            }
        )
    return out


def _call_hook(hook_name: str) -> list[Any]:
    pm = get_plugin_manager()
    try:
        return list(getattr(pm.hook, hook_name)())
    except Exception as exc:  # noqa: BLE001 - un plugin qui plante ne doit jamais crasher S1M0NE
        logger.error(f"Échec de l'appel du hook '{hook_name}' auprès des plugins : {exc}")
        return []


def plugin_connectors() -> list:
    """Fusionne les connecteurs fournis par tous les plugins (`s1mone_connectors`)."""
    connectors: list = []
    for batch in _call_hook("s1mone_connectors"):
        if batch:
            connectors.extend(batch)
    return connectors


def plugin_task_handlers() -> dict:
    """Fusionne les handlers de tâches fournis par tous les plugins (`s1mone_task_handlers`)."""
    handlers: dict[str, Any] = {}
    for batch in _call_hook("s1mone_task_handlers"):
        if batch:
            handlers.update(batch)
    return handlers
