# PROJECT_STATE.md — Mémoire vivante du projet

> Objectif : que le travail puisse reprendre sans perdre le contexte, même après une interruption.
> À mettre à jour après chaque étape/session importante (règle §31-32 du méga-prompt).

## État actuel

- **PHASE 0 — DÉCOUVERTE : terminée et validée.**
- **PHASE 1 — FONDATION : terminée, testée ET VALIDÉE SUR LA VRAIE MACHINE (omrane-Inspiron-3520, Linux Mint 22.3, install.sh + 15/15 tests exécutés avec succès en conditions réelles).**
- **PHASE 2 — INTERFACE WEB : terminée, testée ET VALIDÉE SUR LA VRAIE MACHINE** (dashboard live
  vérifié dans le navigateur sur omrane-Inspiron-3520 : RAM/CPU/disque réels affichés,
  auto-diagnostic OK, page Terminal Web fonctionnelle, 23/23 tests passés lors de l'installation).
- Prochaine phase à valider avec l'utilisateur avant démarrage : **PHASE 3 — TASK MANAGER**.

## Fonctionnalités terminées — Phase 2 (nouveau)

- [x] `web/app.py` — Web Gateway FastAPI : `/`, `/terminal`, `/api/health`, `/api/system`,
      `/api/cli/{command}` (liste blanche stricte : status/system/version, 403 sinon),
      `/partials/system`, `/partials/health`.
- [x] `web/templates/` — Jinja2 (base + dashboard + terminal + fragments htmx).
- [x] `web/static/vendor/` — htmx 2.0.3 + Alpine.js 3.14.3 vendorisés localement (pas de CDN,
      fonctionne hors-ligne, conforme DECISIONS.md D8).
- [x] `cli/main.py` — nouvelle commande `s1mone web` (lance uvicorn, host/port configurables).
- [x] 8 nouveaux tests (`test_web.py`, `test_cli_web_command.py`) → total 23/23.
- [x] Vérifié en live dans le sandbox (dashboard, terminal web, API) avant transmission.

## Contexte d'exécution important

- L'agent travaille dans un **sandbox cloud de développement**, distinct de la machine cible
  réelle (Dell, Linux Mint 22.3, i3-3110M, 3.7 GiB RAM).
- Le code sera développé et testé dans ce workspace, puis récupéré par l'utilisateur via
  `git clone` / `git pull` pour être installé et exécuté sur sa machine réelle via `install.sh`.
- Les caractéristiques matérielles dans `SYSTEM_PROFILE.md` sont **déclarées par l'utilisateur**,
  pas encore ré-auditées avec `scripts/audit_system.sh` sur la machine réelle.

## Fonctionnalités terminées

- [x] Lecture et validation du méga-prompt de conception (fourni par l'utilisateur).
- [x] `SYSTEM_PROFILE.md` (déclaré, à confirmer).
- [x] `RESEARCH.md` (recherche web réelle et sourcée sur 8 grandes décisions techniques).
- [x] `ARCHITECTURE_OPTIONS.md` (tableaux comparatifs par composant).
- [x] `DECISIONS.md` (choix figés, statut PROPOSED en attente de test réel).
- [x] `scripts/audit_system.sh` (script d'audit lecture seule pour la vraie machine).

## Fonctionnalités terminées — Phase 1 (nouveau)

- [x] `core/config.py` — Configuration Manager (config.toml + .env, secrets jamais dans le TOML,
      masquage automatique dans les logs). 5 tests.
- [x] `core/logging_setup.py` — Logging Manager (rotation, filtre anti-fuite de secrets). Vérifié
      manuellement (un `token=...` injecté n'apparaît jamais en clair dans `logs/s1mone.log`).
- [x] `core/db.py` — Storage Manager SQLite (tables `tasks`, `memory`, `cache`, `projects`,
      `schema_meta`), idempotent, WAL activé. 4 tests.
- [x] `system/monitor.py` + `system/healthcheck.py` — System Manager (psutil : CPU/RAM/swap/disque,
      classification NORMAL/WARNING/CRITICAL) + auto-diagnostic. 3 tests.
- [x] `cli/main.py` — Terminal Gateway (Typer + Rich) : `s1mone status`, `s1mone system`,
      `s1mone version`. 3 tests.
- [x] `pyproject.toml` + `install.sh` — installation reproductible, **validée deux fois de bout en
      bout sur un clone Git propre** (venv, dépendances, dossiers, `.env`, SQLite, tests → 15/15).
- [x] Bug réel détecté et corrigé pendant les tests d'installation : un test supposait à tort que
      le dossier de clone s'appelait "S1M0NE" (corrigé pour être indépendant du nom du dossier).

## En cours / en attente

- [x] Exécution de `scripts/audit_system.sh` sur la machine réelle : FAIT, `SYSTEM_PROFILE.md` passé en VERIFIED.
- [ ] Validation utilisateur avant de démarrer la **PHASE 2 — INTERFACE WEB** (FastAPI + Jinja2 +
      htmx/Alpine.js, dashboard + terminal web minimal).

## Problèmes connus / points de vigilance identifiés pendant la recherche

- L'API de recherche PyPI officielle (XML-RPC) est désactivée depuis fin 2020 : le futur
  connecteur PyPI ne pourra pas faire de "recherche floue" native, seulement une résolution par
  nom exact de paquet. Ce sera présenté clairement à l'utilisateur, jamais simulé.
- L'API de recherche GitHub est limitée à 30 requêtes/minute (avec token) : le Cache Manager doit
  être opérationnel avant d'activer ce connecteur en usage intensif.
- Le proxy LiteLLM (pas le SDK) nécessite PostgreSQL + Redis en production : écarté d'office pour
  cette machine ; seul le SDK sera utilisé, plus tard (Phase 6).

## Décisions techniques clés (résumé, voir DECISIONS.md pour le détail)

| Domaine | Choix retenu |
|---|---|
| Backend | FastAPI + Uvicorn |
| CLI | Typer + Rich + prompt_toolkit |
| DB | SQLite (stdlib) |
| Tâches | moteur maison asyncio + SQLite |
| Cache | table SQLite dédiée avec TTL |
| Frontend | Jinja2 + htmx + Alpine.js (sans build Node.js) |
| IA Gateway | interface interne + LiteLLM SDK comme 1er adaptateur (Phase 6) |
| Connecteurs | classe `Connector` + chargement dynamique (npm → HF → GitHub → GitLab/Codeberg → PyPI limité → autres) |
| Sécurité | READ/WRITE/EXECUTE/ADMIN + confirmation obligatoire pour commandes destructrices, dès la Phase 1 |

## Prochaine étape (après validation)

**PHASE 2 — INTERFACE WEB** (mega-prompt §7/§9), découpée en petites unités :
1. Serveur FastAPI minimal (réutilise `core.config`, `core.logging_setup`).
2. Endpoint santé `/api/status` (réutilise `system.healthcheck.run_all_checks`).
3. Dashboard HTML (Jinja2) affichant CPU/RAM/disque en direct (polling htmx).
4. Terminal web minimal (à définir : rejouer les commandes CLI existantes via l'API).
5. Tests d'intégration API (TestClient FastAPI) + commit.

Chaque étape suivra le format imposé : OBJECTIF → FICHIERS → CODE → INSTALLATION → TEST →
RÉSULTAT ATTENDU → RÉSULTAT OBTENU → PROBLÈMES → PROCHAINE ÉTAPE.
