# S1M0NE

> "Une petite machine peut héberger une grande idée si l'architecture est intelligente."

S1M0NE est une plateforme personnelle intelligente ("maison numérique") : terminal avancé,
interface web légère, moteur de tâches, moteur de recherche multi-sources, et architecture
extensible vers l'IA — conçue en priorité pour tourner confortablement sur une machine modeste
(2 cœurs, ~4 Gio de RAM).

## État du projet

- **Phase 0 — Découverte : terminée.**
- **Phase 1 — Fondation (config, logs, SQLite, System Manager, CLI de base) : terminée, testée et
  validée sur la machine réelle.**
- **Phase 2 — Interface Web (dashboard, terminal web, API) : terminée, testée et validée sur la
  machine réelle.**
- **Phase 3 — Task Manager (file de tâches asyncio/SQLite, CLI `s1mone task ...`, worker embarqué
  dans `s1mone web`) : terminée, testée et validée sur la machine réelle.**
- **Phase 4 — Cache Manager (SQLite + TTL) : terminée, testée et validée sur la machine réelle.**
- **Phase 5 — Connecteurs de recherche (npm, Hugging Face, GitHub, GitLab, Codeberg, PyPI,
  SourceForge) : terminée, testée et validée sur la machine réelle**, avec intégration complète
  CLI (`s1mone search`) et web (`/search`).
- **Phase 6 — AI Gateway (assistant IA conversationnel, gratuit et sans carte bancaire) : terminée,
  testée et validée sur la machine réelle.** `s1mone chat` (CLI) et page `/chat` (web), 3
  fournisseurs interchangeables : Groq (recommandé), OpenRouter, Ollama (local, expérimental).
- **Phase 7 — Mémoire : terminée, testée et validée sur la machine réelle.** La conversation IA
  persiste maintenant d'une session à l'autre (`s1mone chat` continue là où tu l'as laissé, même
  après avoir fermé le terminal), et l'assistant sait ce qu'est S1M0NE. Complétée par
  `s1mone memory list/show/forget` (transparence totale sur ce qui est mémorisé) et un tableau
  `s1mone search` plus lisible (une ligne par résultat).
- **Phase 9 — Sécurité (permissions + commandes système réelles) : terminée, testée et validée
  sur la machine réelle.** `s1mone exec` (CLI) et le terminal web (`/terminal`) peuvent exécuter
  de vraies commandes système, mais uniquement une liste blanche stricte, classée par niveau de
  permission (READ/WRITE/EXECUTE/ADMIN), bornée au dossier de données de S1M0NE, avec
  confirmation explicite obligatoire pour toute commande destructrice (rm, rmdir).
- **Phase 8 — Plugins (Pluggy) : terminée et testée en sandbox, en attente de validation sur la
  machine réelle.** Dépose un fichier `.py` dans `plugins_local/` pour ajouter un connecteur de
  recherche ou un type de tâche à S1M0NE, sans toucher au code central. Deux exemples fournis et
  fonctionnels dans `plugins_local/examples/`.

Le détail complet, phase par phase, est dans [`PROJECT_STATE.md`](./PROJECT_STATE.md).

## Installation (première fois)

```bash
git clone https://github.com/mlinux952-code/S1M0NE.git
cd S1M0NE
./install.sh
source venv/bin/activate
s1mone status
```

`install.sh` crée l'environnement virtuel, installe les dépendances, prépare `.env`, initialise
la base SQLite et lance les tests automatiquement. Ne touche à rien en dehors du dossier du
projet, et ne modifie jamais un `.env` déjà présent.

## Mise à jour (tu as déjà une installation existante)

```bash
cd ~/S1M0NE/S1M0NE     # adapte le chemin si besoin
git pull
./install.sh
```

`install.sh` est idempotent : il réutilise la venv existante, met à jour les dépendances si
besoin, et relance toute la suite de tests pour confirmer que tout va bien après la mise à jour.

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

s1mone search react                             # recherche dans les 7 connecteurs
s1mone search flask --sources npm,pypi --limit 3
s1mone search --list-sources                    # liste les sources disponibles

s1mone chat "explique-moi ce qu'est une API REST" # une question, une réponse (mémorisée)
s1mone chat                                     # conversation interactive (tape 'exit' pour sortir,
                                                 # '/reset' pour repartir de zéro en cours de route)
s1mone chat --list-providers                    # voir les fournisseurs dispo et leur statut
s1mone chat --reset "on recommence"             # efface la conversation précédente avant d'envoyer
s1mone chat --no-memory "question ponctuelle"   # ne lit ni n'écrit la conversation mémorisée

s1mone web                                      # dashboard + terminal web + recherche + chat IA
                                                 # (le worker de tâches tourne dans ce même
                                                 # processus, pas besoin de le lancer à part)
```

## Assistant IA (Phase 6)

Gratuit et sans carte bancaire par défaut. Aucune clé n'est jamais demandée par l'agent : à
ajouter toi-même dans ton fichier `.env` (jamais commité).

| Fournisseur | Configuration | Notes |
|---|---|---|
| **Groq** (recommandé) | `GROQ_API_KEY` dans `.env` — clé gratuite sur https://console.groq.com/keys | Rapide, quota généreux (~30 req/min) |
| **OpenRouter** | `OPENROUTER_API_KEY` dans `.env` — clé gratuite sur https://openrouter.ai/keys | Catalogue de modèles gratuits qui change souvent ; ajustable dans `config.toml` |
| **Ollama** (local) | Rien à configurer si installé par défaut (https://ollama.com) | 100% privé et hors-ligne, mais lent sur cette machine (~4 Gio RAM) — pour tester, pas pour un usage quotidien |

Le fournisseur par défaut se change dans `config/config.toml`, section `[ai] default_provider`,
ou ponctuellement avec `s1mone chat --provider openrouter "..."`.

## Mémoire (Phase 7)

La conversation avec l'assistant IA est mémorisée en base SQLite locale (table `memory`) : elle
continue d'une session à l'autre au lieu de repartir de zéro à chaque fois, en CLI comme en web.
L'assistant sait aussi ce qu'est S1M0NE (message système d'auto-présentation injecté à chaque
conversation). Pour repartir d'une page blanche : `s1mone chat --reset`, `/reset` en conversation
interactive, ou le bouton "Nouvelle conversation" sur `/chat`.

Transparence : tout ce que S1M0NE retient reste inspectable et supprimable depuis la CLI —
rien n'est caché.

```bash
s1mone memory list                              # tout ce qui est mémorisé (métadonnées)
s1mone memory list --level persistent           # filtré par niveau
s1mone memory show persistent chat_history      # contenu complet d'une entrée
s1mone memory forget persistent chat_history    # supprime une entrée (demande confirmation)
s1mone memory forget persistent chat_history -y # supprime sans demander de confirmation
```

## Sécurité — permissions et commandes système (Phase 9)

S1M0NE peut exécuter de vraies commandes système (`pwd`, `ls`, `mkdir`, `cp`, `rm`, ...), mais
jamais une commande arbitraire : uniquement une **liste blanche** définie dans
`core/permissions.py`, classée en 4 niveaux de confiance croissants **READ < WRITE < EXECUTE <
ADMIN**. Toute commande qui touche à un fichier reste bornée au dossier de données de S1M0NE
(`fs_root`, `DATA_DIR` par défaut), jamais au disque entier — même au niveau ADMIN. Les
commandes destructrices (`rm`, `rmdir`) exigent toujours une confirmation explicite avant
exécution.

- **Terminal local (`s1mone exec`)** : niveau `ADMIN` par défaut (c'est toi qui lances la CLI sur
  ta propre session, même confiance qu'un shell classique).
- **Terminal web (`/terminal`)** : niveau `READ` par défaut, plus prudent — l'interface web
  écoute sur `0.0.0.0` sans authentification, n'importe quel appareil de ton réseau local peut
  l'atteindre. Élève ce niveau dans `config.toml [security]` seulement si tu fais confiance à ton
  réseau.
- Explicitement **hors périmètre, quel que soit le niveau** : `shutdown`, `reboot`, `dd`, `mkfs`,
  `chmod`/`chown` massifs, `sudo` — ces commandes ne sont jamais ajoutées au catalogue.

```bash
s1mone exec list                    # catalogue complet + niveau du terminal local
s1mone exec run "pwd"
s1mone exec run "mkdir sous_dossier"
s1mone exec run "rm fichier.txt"    # demande confirmation, sauf --yes/-y
```

## Plugins (Phase 8)

S1M0NE s'étend sans jamais toucher à son code central : dépose un fichier `.py` dans
`plugins_local/` pour ajouter un connecteur de recherche ou un type de tâche, basé sur
[Pluggy](https://pluggy.readthedocs.io/) (le même moteur de plugins que pytest).

```bash
cp plugins_local/examples/hello_connector.py plugins_local/   # active l'exemple
s1mone plugin list                                            # vérifie qu'il est bien chargé
s1mone search test --sources hello                             # l'utilise
```

Voir [`plugins_local/README.md`](./plugins_local/README.md) pour écrire ton propre plugin (deux
hooks disponibles : `s1mone_connectors`, `s1mone_task_handlers`) et la frontière de confiance
associée (un plugin est du code Python exécuté avec les mêmes droits que S1M0NE — n'installe que
ce à quoi tu fais confiance). Un connecteur ou type de tâche déjà intégré ne peut jamais être
redéfini par un plugin.

## Recherche multi-sources (Phase 5)

| Source | Recherche | Authentification |
|---|---|---|
| npm | libre (mot-clé) | aucune |
| Hugging Face | libre (mot-clé) | aucune |
| GitHub | libre (mot-clé) | optionnelle — `GITHUB_TOKEN` dans `.env` pour passer de 10 à 30 req/min |
| GitLab | libre (mot-clé) | aucune |
| Codeberg | libre (mot-clé) | aucune |
| PyPI | nom exact uniquement (mode dégradé, transparent) | aucune |
| SourceForge | nom exact uniquement (mode dégradé, transparent) | aucune |

Bitbucket et Gitee ne sont volontairement pas implémentés : leurs APIs publiques ne permettent
plus de recherche par mot-clé fiable (vérifié en direct — voir `DECISIONS.md` §D9).

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
- Anti-hallucination : un connecteur qui ne peut pas répondre correctement dit clairement
  pourquoi (mode dégradé, erreur) plutôt que d'inventer un résultat.
- Aucune commande destructrice n'est exécutée sans confirmation explicite.
