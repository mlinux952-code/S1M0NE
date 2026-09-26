# S1M0NE

> "Une petite machine peut héberger une grande idée si l'architecture est intelligente."

S1M0NE est une plateforme personnelle intelligente ("maison numérique") : terminal avancé,
interface web légère, moteur de tâches, et architecture extensible vers l'IA — conçue en
priorité pour tourner confortablement sur une machine modeste (2 cœurs, ~4 Gio de RAM).

## État du projet

- **Phase 0 — Découverte : terminée.**
- **Phase 1 — Fondation (config, logs, SQLite, System Manager, CLI de base) : terminée, testée et
  validée sur la machine réelle.**
- **Phase 2 — Interface Web (dashboard, terminal web, API) : terminée, testée et validée sur la
  machine réelle.**
- **Phase 3 — Task Manager (file de tâches asyncio/SQLite, CLI `s1mone task ...`, worker embarqué
  dans `s1mone web`) : terminée et testée dans l'environnement de développement. À valider sur ta
  machine réelle après installation/mise à jour (voir ci-dessous).**

Le détail complet, phase par phase, est dans [`PROJECT_STATE.md`](./PROJECT_STATE.md).

## Installation (première fois)

```bash
cd ~
unzip S1M0NE_phase3.zip -d ~/S1M0NE_install
cd ~/S1M0NE_install/S1M0NE
./install.sh
source venv/bin/activate
s1mone status
```

`install.sh` crée l'environnement virtuel, installe les dépendances, prépare `.env`, initialise
la base SQLite et lance les tests automatiquement. Ne touche à rien en dehors du dossier du
projet.

## Mise à jour (tu as déjà une installation précédente)

Le zip ne contient volontairement pas `.git` (pour rester léger). Pour mettre à jour une
installation existante avec une nouvelle livraison (ex. `S1M0NE_phase3.zip`) :

```bash
cd ~                                    # ou le dossier qui CONTIENT ton dossier S1M0NE existant
unzip -o S1M0NE_phase3.zip -d ~/S1M0NE/  # -o : écrase les fichiers déjà présents, sans supprimer
                                          # data/, logs/, .env, venv/ (absents du zip)
cd ~/S1M0NE/S1M0NE
rm -rf venv
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -e . pytest
./venv/bin/python -m pytest -q
```

Adapte le premier `cd ~` et le chemin `-d` à l'endroit réel où se trouve ton dossier `S1M0NE`
existant sur ta machine.

## Utilisation

```bash
source venv/bin/activate

s1mone status                                   # diagnostic complet
s1mone system                                   # CPU / RAM / disque en direct

s1mone task submit sleep --param seconds=5      # soumet une tâche
s1mone task list                                # liste les tâches
s1mone task show <id>                           # détail d'une tâche
s1mone task cancel <id>                         # annule une tâche
s1mone task worker --once                       # traite la file d'attente une fois

s1mone web                                      # dashboard + terminal web + API
                                                 # (le worker de tâches tourne dans ce même
                                                 # processus, pas besoin de le lancer à part)
```

## Documents de référence

| Document | Contenu |
|---|---|
| [`PROJECT_STATE.md`](./PROJECT_STATE.md) | État courant détaillé, phase par phase, mémoire du projet |
| [`SYSTEM_PROFILE.md`](./SYSTEM_PROFILE.md) | Fiche matérielle de la machine cible |
| [`RESEARCH.md`](./RESEARCH.md) | Recherche technique sourcée (frameworks, APIs, librairies) |
| [`ARCHITECTURE_OPTIONS.md`](./ARCHITECTURE_OPTIONS.md) | Tableaux comparatifs par composant |
| [`DECISIONS.md`](./DECISIONS.md) | Décisions d'architecture retenues et justifiées |
| [`scripts/audit_system.sh`](./scripts/audit_system.sh) | Script d'audit lecture seule pour ta machine réelle |

## Philosophie

- Low resource first : SQLite, un seul processus serveur, pas de Docker/Kubernetes/Redis/ES.
- Zéro dépense obligatoire : APIs gratuites et logiciels libres en priorité.
- Développement par petites phases testées, jamais un gros bloc de code non vérifié.
- Aucune commande destructrice n'est exécutée sans confirmation explicite.
