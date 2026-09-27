# Plugins locaux de S1M0NE (Phase 8)

Ce dossier est surveillé au démarrage de S1M0NE : tout fichier `.py` posé **directement ici**
(pas dans un sous-dossier) est automatiquement chargé comme plugin. Aucune installation, aucun
redémarrage de service compliqué — c'est la façon la plus simple d'étendre S1M0NE sans toucher
à son code central.

## Écrire un plugin

Un plugin implémente une ou deux fonctions, décorées avec `@hookimpl` (importé depuis
`plugins.manager`) :

- `s1mone_connectors()` → retourne une liste d'instances `connectors.base.Connector`, ajoutées
  au moteur de recherche multi-source (`s1mone search`, `/search`).
- `s1mone_task_handlers()` → retourne un dict `{"type_name": handler_async}`, ajouté au Task
  Manager (`s1mone task submit <type_name> ...`).

Deux exemples complets et fonctionnels sont dans `examples/` :

- [`examples/hello_connector.py`](./examples/hello_connector.py) — un connecteur de recherche
  factice.
- [`examples/hello_task.py`](./examples/hello_task.py) — un type de tâche `echo` factice.

Pour les activer : copie le fichier voulu depuis `examples/` vers ce dossier (`plugins_local/`),
puis relance `s1mone` (CLI) ou `s1mone web`. Vérifie avec :

```bash
s1mone plugin list
```

## Désactiver un plugin sans le supprimer

Préfixe le nom du fichier par `_` (ex. `_hello_connector.py`) — il sera ignoré au chargement.

## Limites et frontière de confiance

- Un plugin est du code Python arbitraire, exécuté avec les mêmes droits que S1M0NE. Ce n'est
  **pas** soumis à la liste blanche de commandes système de la Phase 9 : cette liste blanche
  protège contre l'exécution *automatique* de commandes système, pas contre du code que tu
  choisis toi-même d'installer. N'installe que des plugins auxquels tu fais confiance.
- Un type de tâche ou un connecteur déjà intégré à S1M0NE ne peut pas être redéfini par un
  plugin (le composant intégré gagne toujours, un avertissement apparaît dans les logs).
- Pour distribuer un vrai paquet pip plutôt qu'un fichier local, expose un entry point du
  groupe `s1mone` dans son `pyproject.toml` :
  ```toml
  [project.entry-points.s1mone]
  mon_plugin = "mon_paquet.plugin_module"
  ```
