"""
plugins/hookspecs.py — Points d'extension officiels de S1M0NE (Phase 8 - Plugins).

Décision D9 (DECISIONS.md) : la Phase 5 (connecteurs) a délibérément évité un framework de
plugin externe ("classe abstraite + découverte dynamique, sans Pluggy pour l'instant"), en
renvoyant le sujet à cette Phase 8. C'est ici que ça se concrétise : Pluggy (déjà présent comme
dépendance transitive de pytest, maintenant une dépendance directe de S1M0NE) fournit un vrai
mécanisme de plugins, avec validation de signature et enregistrement explicite.

Principe (mega-prompt : extensibilité sans toucher au noyau) : un plugin tiers peut ajouter de
nouveaux connecteurs de recherche et/ou de nouveaux types de tâches, sans modifier une seule
ligne de `connectors/`, `tasks/`, `cli/` ou `web/`. Deux façons d'installer un plugin :

1. **Fichier local** : déposer un `.py` dans le dossier `plugins_local/` (configurable,
   `config.toml [plugins] dir`) — le plus simple, zéro dépendance, adapté à un usage personnel.
2. **Paquet pip installé** exposant un entry point du groupe `"s1mone"` (setuptools/pyproject
   `[project.entry-points.s1mone]`) — pour un vrai plugin distribuable.

Frontière de confiance explicite : un plugin est du code Python arbitraire, exécuté avec les
mêmes droits que S1M0NE lui-même. Ce n'est PAS soumis à la liste blanche de commandes système de
la Phase 9 (qui protège contre l'exécution *automatique* de commandes, pas contre du code que
l'utilisateur choisit lui-même d'installer). Voir DECISIONS.md (nouvelle entrée Phase 8) pour le
détail de cette distinction.
"""

from __future__ import annotations

import pluggy

HOOK_NAMESPACE = "s1mone"

hookspec = pluggy.HookspecMarker(HOOK_NAMESPACE)
hookimpl = pluggy.HookimplMarker(HOOK_NAMESPACE)


class S1moneHookSpecs:
    """Chaque méthode ci-dessous est un point d'extension qu'un plugin peut implémenter (une
    seule des deux, les deux, ou ni l'une ni l'autre — pluggy n'exige jamais tout)."""

    @hookspec
    def s1mone_connectors(self) -> list:
        """Retourne une liste d'instances `connectors.base.Connector` à ajouter au moteur de
        recherche multi-source (Phase 5), en plus des connecteurs intégrés. Un nom de connecteur
        qui entre en conflit avec un connecteur intégré est ignoré (le connecteur intégré gagne
        toujours, avec un avertissement dans les logs)."""

    @hookspec
    def s1mone_task_handlers(self) -> dict:
        """Retourne un dict {type_name: handler_async} à ajouter au Task Manager (Phase 3), en
        plus des types intégrés (`sleep`, `system_snapshot`). Même règle de conflit que pour les
        connecteurs : un type déjà intégré ne peut pas être redéfini par un plugin."""
