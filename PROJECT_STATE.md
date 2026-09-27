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
- **PHASE 6 — AI GATEWAY : terminée et testée dans le sandbox. Pas encore validée sur la machine
  réelle** (à faire par l'utilisateur après `git pull && ./install.sh`). Assistant IA
  conversationnel gratuit, sans carte bancaire : `s1mone chat` (CLI, mode message unique ou
  interactif) + page `/chat` (web). 3 fournisseurs interchangeables sans toucher au code
  (config.toml `[ai] default_provider`) : Groq (recommandé), OpenRouter, Ollama (local,
  expérimental). Voir DECISIONS.md §D7 (révisé : LiteLLM abandonné au profit d'adaptateurs httpx
  maison, plus légers).
- **126/126 tests automatisés passent** dans le sandbox.

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

## Prochaine étape

Phase 6 (IA) codée et testée en sandbox, en attente de validation sur la machine réelle de
l'utilisateur (`git pull && ./install.sh`, puis `s1mone chat --list-providers`, puis configurer
au moins une clé gratuite dans `.env` pour tester une vraie conversation).

Candidats du plan initial restants après validation de la Phase 6 :
- **Phase 7 — Mémoire** : système de mémoire/contexte persistant (actuellement un lien désactivé
  dans la nav web, "Arrive en Phase 7") — permettrait aussi de garder l'historique du chat IA
  entre deux sessions, ce qui n'est pas encore le cas (historique en mémoire process uniquement).
- Améliorations transverses possibles : affichage terminal de `s1mone search` (tableau large),
  pagination, tri par pertinence/stars.
