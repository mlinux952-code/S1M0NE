# PROJECT_STATE.md — Mémoire vivante du projet

> Objectif : que le travail puisse reprendre sans perdre le contexte, même après une interruption.
> À mettre à jour après chaque étape/session importante (règle §31-32 du méga-prompt).

## État actuel

- **Phase en cours : PHASE 0 — DÉCOUVERTE**
- **Statut : terminée côté agent, EN ATTENTE DE VALIDATION UTILISATEUR** avant de démarrer la
  Phase 1 (fondation / code).
- Aucune ligne de code applicatif n'a encore été écrite (conforme à la règle "ne code pas trop
  tôt").

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

## En cours / en attente

- [ ] Validation utilisateur des décisions D1 à D11 avant tout code.
- [ ] Exécution de `scripts/audit_system.sh` sur la machine réelle (optionnel mais recommandé) et
      mise à jour de `SYSTEM_PROFILE.md` avec le statut `VERIFIED`.
- [ ] Démarrage de la **PHASE 1 — FONDATION** : configuration, logs, SQLite, CLI minimale
      (`s1mone status`, `s1mone system`), health check. Pas avant validation.

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

**PHASE 1 — FONDATION**, découpée en petites unités selon la règle de communication (§30/§33) :
1. Structure de dossiers + `config.toml` + `.env.example` + `.gitignore`.
2. Logging structuré avec rotation.
3. Module SQLite + schéma initial (tables `tasks`, `cache`, `memory`, `projects`).
4. CLI minimale : `s1mone status`, `s1mone system` (affiche CPU/RAM/disque via `psutil`).
5. Tests de base + premier commit Git propre.

Chaque étape suivra le format imposé : OBJECTIF → FICHIERS → CODE → INSTALLATION → TEST →
RÉSULTAT ATTENDU → RÉSULTAT OBTENU → PROBLÈMES → PROCHAINE ÉTAPE.
