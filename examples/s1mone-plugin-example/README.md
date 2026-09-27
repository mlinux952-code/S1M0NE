# s1mone-plugin-example

Plugin d'exemple pour [S1M0NE](../../README.md), distribué comme un **vrai paquet pip installable**
plutôt qu'un simple fichier `.py` à copier — c'est le second mécanisme décrit dans
`plugins/hookspecs.py` (Phase 8), jusqu'ici seulement démontré par les fichiers de
`plugins_local/examples/`. Ce dossier montre le second mécanisme : un entry point du groupe
`"s1mone"`, déclaré dans `pyproject.toml`.

## Ce qu'il ajoute

- Un connecteur de recherche `example-pip` (résultat de démonstration uniquement — jamais une
  vraie donnée externe, conformément à la règle anti-hallucination du projet).
- Un type de tâche `example-echo` (renvoie tel quel le message reçu).

## Installer

Depuis la racine du dépôt S1M0NE, dans le même environnement virtuel que S1M0NE lui-même
(ce plugin importe `connectors.base` et `plugins.manager` : il n'a de sens qu'installé à côté
d'un checkout de S1M0NE, jamais seul) :

```bash
pip install -e examples/s1mone-plugin-example
```

Puis vérifier :

```bash
s1mone plugin list
# → doit afficher "example" avec source = "paquet installé"

s1mone search bonjour --sources example-pip
s1mone task submit example-echo --params '{"message": "salut"}'
```

## Désinstaller

```bash
pip uninstall s1mone-plugin-example
```

S1M0NE le redétecte (ou l'oublie) automatiquement au prochain démarrage — rien à configurer côté
S1M0NE dans un sens comme dans l'autre.

## Adapter ce modèle

Copie ce dossier, renomme le paquet (`pyproject.toml` : `name`, `[project.entry-points.s1mone]`
et le nom du module dans `src/`), puis modifie `src/s1mone_plugin_example/__init__.py` pour
implémenter un vrai connecteur (`s1mone_connectors`) et/ou un vrai type de tâche
(`s1mone_task_handlers`) — voir `plugins/hookspecs.py` dans le dépôt principal pour le contrat
exact de chaque hook.
