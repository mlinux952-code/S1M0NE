# PROJECT_STATE.md — Mémoire vivante du projet

> Objectif : que le travail puisse reprendre sans perdre le contexte, même après une interruption.
> À mettre à jour après chaque étape/session importante (règle §31-32 du méga-prompt).
> Convention : on précise TOUJOURS si un statut concerne le **sandbox** (atelier de développement
> de l'agent) ou la **machine réelle** de l'utilisateur (omrane-Inspiron-3520). Les deux peuvent
> être en avance/retard l'une sur l'autre entre deux sessions — voir §"Workflow de livraison".

## État actuel (sandbox ET machine réelle, à jour)

- **PHASE 0 — DÉCOUVERTE : terminée et validée.**
- **PHASE 1 — FONDATION : terminée, testée et validée sur la machine réelle.**
- **PHASE 2 — INTERFACE WEB : terminée, testée et validée sur la machine réelle.**
- **PHASE 3 — TASK MANAGER : terminée, testée et validée sur la machine réelle.**
- **PHASE 4 — CACHE MANAGER : terminée, testée et validée sur la machine réelle.**
  Construite rétroactivement (trou de numérotation détecté en cours de route — voir DECISIONS.md
  et l'historique Git) juste avant la Phase 5, dont elle est un prérequis direct (GitHub : quota
  strict de recherche).
- **PHASE 5 — CONNECTEURS DE RECHERCHE : terminée, testée et validée sur la machine réelle.**
  7 connecteurs actifs : npm, Hugging Face, GitHub (token optionnel), GitLab, Codeberg (recherche
  libre) + PyPI, SourceForge (mode dégradé transparent : nom exact uniquement). Bitbucket et
  Gitee ont été **retirés définitivement** du plan après vérification en direct de leurs API
  (voir DECISIONS.md §D9) : aucune recherche par mot-clé fiable n'y est possible.
- **Intégration CLI + Web du moteur de recherche : terminée, testée et validée sur la machine
  réelle.** Commande `s1mone search <terme> [--sources ...] [--limit N] [--list-sources]` en CLI,
  page `/search` (formulaire htmx) + `/api/search` + `/api/search/sources` côté web. Deux bugs
  réels détectés et corrigés après retour utilisateur (voir Historique ci-dessous).
- **PHASE 6 — AI GATEWAY : terminée, testée et validée sur la machine réelle.** Assistant IA
  conversationnel gratuit, sans carte bancaire : `s1mone chat` (CLI, mode message unique ou
  interactif) + page `/chat` (web). 3 fournisseurs interchangeables sans toucher au code
  (config.toml `[ai] default_provider`) : Groq (recommandé), OpenRouter, Ollama (local,
  expérimental). Voir DECISIONS.md §D7 (révisé : LiteLLM abandonné au profit d'adaptateurs httpx
  maison, plus légers). Bug réel détecté et corrigé après retour utilisateur : le modèle Groq par
  défaut (`llama-3.3-70b-versatile`) était passé en accès Enterprise chez Groq entre-temps →
  remplacé par `openai/gpt-oss-20b`.
- **PHASE 7 — MÉMOIRE : terminée, testée et validée sur la machine réelle** (confirmé : le
  symlink `~/.local/bin/s1mone` fonctionne dans un nouveau terminal, `s1mone chat` se souvient du
  prénom de l'utilisateur et de l'auto-description de S1M0NE à travers plusieurs invocations).
  Memory Manager (`core/memory.py`) au-dessus de la table SQLite `memory` (Phase 1). Premier
  usage concret : la conversation IA (Phase 6) persiste maintenant entre deux lancements de
  `s1mone chat` ou deux visites de `/chat`, au lieu de repartir de zéro — plus un message système
  d'auto-présentation de S1M0NE. `--reset` / `/reset` / bouton "Nouvelle conversation" pour
  repartir à zéro. Voir DECISIONS.md §D12.
- **Polish post-Phase 7 (terminé, testé et validé sur la machine réelle) :**
  - `s1mone memory list/show/forget` : transparence sur ce qui est mémorisé (métadonnées,
    contenu complet, suppression avec confirmation) — demandé par cohérence avec la Phase 7.
  - Tableau `s1mone search` réécrit en une seule ligne par résultat (`overflow="ellipsis"` +
    nettoyage des descriptions contenant des retours à la ligne bruts) : corrige le rough edge
    "tableau trop large / difficile à lire" identifié précédemment.
- **PHASE 9 — SÉCURITÉ : terminée et testée en sandbox, en attente de validation sur la machine
  réelle.** Voir la section dédiée plus bas pour le détail complet. En résumé : `s1mone exec` +
  `/terminal` (web) peuvent exécuter de vraies commandes système, en liste blanche stricte,
  classées par permission READ/WRITE/EXECUTE/ADMIN, bornées au dossier de données, avec
  confirmation obligatoire pour les commandes destructrices (rm, rmdir). Voir DECISIONS.md §D10
  (mis à jour : DECIDED).
- **186/186 tests automatisés passent** dans le sandbox (152 avant Phase 9 + 34 nouveaux).

## Workflow de livraison (actuel, définitif)

Plus de zips. Dépôt Git distant opérationnel : `https://github.com/mlinux952-code/S1M0NE.git`.
- L'agent (sandbox) commit + push directement sur `main`.
- L'utilisateur récupère avec `git pull` puis relance `./install.sh` (idempotent : réutilise la
  venv existante, ne touche jamais à `.env` s'il existe déjà, réinstalle les dépendances,
  réinitialise la base si besoin, relance toute la suite de tests).
- Après chaque commit poussé par l'agent, une vérification est systématiquement faite sur un
  **clone frais** dans le sandbox (pas seulement le dossier de travail courant) pour confirmer
  que `./install.sh` fonctionne de bout en bout avant de dire "c'est prêt".

## Connecteurs de recherche — état détaillé (Phase 5)

| Connecteur | Recherche | Auth | Statut |
|---|---|---|---|
| npm | mot-clé libre | aucune | ✅ machine réelle |
| Hugging Face | mot-clé libre | aucune | ✅ machine réelle |
| GitHub | mot-clé libre | optionnelle (`GITHUB_TOKEN` dans `.env`, jamais transmis à l'agent) | ✅ machine réelle |
| GitLab | mot-clé libre | aucune | ✅ machine réelle |
| Codeberg | mot-clé libre | aucune | ✅ machine réelle |
| PyPI | nom exact uniquement (dégradé) | aucune | ✅ machine réelle |
| SourceForge | nom exact uniquement (dégradé) | aucune | ✅ machine réelle |
| ~~Bitbucket~~ | — | — | ❌ abandonné (API de recherche globale supprimée par Atlassian, avril 2026) |
| ~~Gitee~~ | — | — | ❌ abandonné (API de recherche publique non fonctionnelle, vérifié en direct) |

Tous les connecteurs passent par le Cache Manager (Phase 4, TTL configurable dans
`config/config.toml`, section `[cache]`) avant tout appel réseau réel.

## Historique récent (bugs réels détectés après retour utilisateur, résolus)

- `pyproject.toml` ne listait pas le package `connectors` (`[tool.setuptools] packages = [...]`)
  depuis sa création en Phase 5 — invisible dans les tests (pytest résout le module depuis le
  répertoire courant), mais cassait le vrai binaire `s1mone` installé. Corrigé.
- `s1mone search --list-sources` exigeait quand même un terme de recherche (argument positionnel
  obligatoire côté Typer, validé avant même d'entrer dans le corps de la fonction). Corrigé :
  `query` est maintenant optionnel, avec message d'erreur clair si aucun des deux n'est fourni.
- Bit exécutable perdu à plusieurs reprises sur `install.sh` / `scripts/audit_system.sh` lors de
  la recréation de la venv en sandbox (incident d'environnement récurrent, pas un bug du projet).
  Vérifié et corrigé systématiquement avant chaque push depuis que le pattern est identifié.

## Contexte d'exécution important

- L'agent travaille dans un **sandbox cloud de développement**, distinct de la machine cible
  réelle (Dell Inspiron 3520, Linux Mint, i3-3110M, ~4 Gio RAM, hostname `omrane-Inspiron-3520`,
  utilisateur `omrane`, Python 3.12.3).
- Le code est développé et testé dans ce sandbox, poussé sur GitHub par l'agent, puis récupéré
  par l'utilisateur via `git pull` + `./install.sh` sur sa machine réelle.

## Décisions techniques clés (résumé, voir DECISIONS.md pour le détail complet)

| Domaine | Choix retenu |
|---|---|
| Backend | FastAPI + Uvicorn |
| CLI | Typer + Rich |
| DB | SQLite (stdlib) |
| Tâches | moteur maison asyncio + SQLite |
| Cache | table SQLite dédiée avec TTL |
| Frontend | Jinja2 + htmx + Alpine.js (sans build Node.js) |
| Connecteurs | classe `Connector` + registre statique dans `connectors/engine.py` |
| IA Gateway | interface interne + LiteLLM SDK comme 1er adaptateur (Phase 6, pas encore commencée) |
| Sécurité | liste blanche stricte de commandes en lecture seule pour le terminal web ; rien
  d'arbitraire n'est jamais exécuté depuis le navigateur |

## PHASE 9 — SÉCURITÉ (permissions + commandes système réelles)

**Terminée et testée en sandbox (186/186 tests), en attente de validation sur la machine réelle
de l'utilisateur.**

Reprend la décision D10 de `DECISIONS.md`, posée dès la Phase 1 mais implémentée seulement
maintenant : S1M0NE peut désormais exécuter de vraies commandes système (jusque-là, seuls des
handlers Python fixes existaient : `sleep`, `system_snapshot`), mais uniquement via :

- `core/permissions.py` : liste blanche de commandes (`CATALOG`), classées en 4 niveaux
  **READ < WRITE < EXECUTE < ADMIN**. Catalogue volontairement modeste : `pwd`, `whoami`, `date`,
  `uptime`, `df`, `free`, `ps` (READ) ; `ls`, `cat` (READ, avec chemin) ; `mkdir`, `touch`, `cp`
  (WRITE) ; `mv` (EXECUTE) ; `rm`, `rmdir` (ADMIN, destructifs). **Décision explicite** :
  `shutdown`/`reboot`/`dd`/`mkfs`/`chmod`/`chown` massifs/`sudo` ne sont PAS implémentés, quel
  que soit le niveau — hors périmètre du produit, danger réel pour la seule machine de
  l'utilisateur sans bénéfice clair.
- `core/shell_runner.py` : exécution réelle (`subprocess.run`, jamais `shell=True`), avec
  validation de chemin systématique (`_resolve_and_check_path`) bornant tout argument-chemin à
  `Settings.fs_root` (DATA_DIR par défaut) — rejette absolu comme relatif (`../..`) qui sortirait
  du périmètre, même au niveau ADMIN. Timeout de sécurité (10s par défaut). Toute commande
  `destructive=True` lève `ConfirmationRequiredError` tant que `confirmed=True` n'est pas fourni
  explicitement par l'appelant.
- CLI : `s1mone exec list` (catalogue + niveau courant), `s1mone exec run "<commande>"`
  (`--yes/-y` pour confirmer d'avance). Niveau par défaut : **ADMIN** (terminal local = même
  confiance qu'un shell classique lancé par le propriétaire de la machine).
- Web : `GET /api/exec/catalog`, `POST /api/exec` (`{command, confirm}` — 409 si confirmation
  requise et non fournie, 403 si permission insuffisante, 400 si commande inconnue ou chemin
  hors périmètre). Niveau par défaut : **READ** (plus prudent — l'interface web écoute sur
  `0.0.0.0` sans authentification). Page `/terminal` enrichie d'un vrai formulaire de commande
  avec gestion du flux de confirmation en deux temps (Alpine.js, sans dépendance JS
  supplémentaire).
- `config.toml [security]` : `cli_permission_level` (défaut ADMIN), `web_permission_level`
  (défaut READ), `fs_root` (défaut DATA_DIR) — tous surchargeables (env `S1MONE_*` ou
  config.toml).
- 34 nouveaux tests (`test_permissions.py`, `test_shell_runner.py`, `test_cli_exec.py`,
  `test_web_exec.py`) : ordre des permissions, refus commande inconnue/permission
  insuffisante/chemin hors périmètre, flux de confirmation CLI (interactif + `--yes`) et web
  (409 puis `confirm=true`).
- **186/186 tests automatisés passent** dans le sandbox (152 + 34).

## Prochaine étape

Validation de la Phase 9 sur la machine réelle de l'utilisateur (`git pull && ./install.sh`,
puis `s1mone exec list`, `s1mone exec run "ls ."`, tester une commande destructrice pour
vérifier la confirmation, et la page `/terminal` en web).

Candidats du plan initial restants après validation de la Phase 9 :
- Phase 8 : vrais plugins tiers (Pluggy), extensibilité sans toucher au code central — permettrait
  d'étendre le catalogue de commandes système ou d'ajouter de nouveaux connecteurs de recherche
  sans modifier `core/`.
- Améliorations transverses possibles : page web dédiée à la mémoire (actuellement CLI
  uniquement) ; pagination/tri des résultats de recherche.
