# ARCHITECTURE_OPTIONS.md — Comparaison des options par composant

Format imposé par le méga-prompt (§26) : tableau `Solution | Ressources | Licence | Gratuit |
Linux | Complexité | Avantages | Limites`, puis discussion. Basé sur `RESEARCH.md`.

## 1. Backend / API

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| FastAPI + Uvicorn | ~42 Mo idle, async | MIT | Oui | Oui | Moyenne | Async natif (idéal pour interroger N connecteurs en parallèle), validation Pydantic, docs OpenAPI auto | Un peu plus de structure imposée que Flask |
| Flask | ~45-48 Mo idle, sync | BSD | Oui | Oui | Faible | Ultra simple, immense écosystème | Pas d'async natif → mauvais pour recherche multi-source parallèle |
| aiohttp pur | Léger | Apache-2.0 | Oui | Oui | Élevée (bas niveau) | Contrôle total | Il faut tout reconstruire soi-même (routing, validation...) |

## 2. Terminal / CLI

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| Typer + Rich + prompt_toolkit | Très léger | MIT/BSD | Oui | Oui | Faible-Moyenne | Commandes type `s1mone status`, sortie colorée/tables, historique+autocomplétion en mode interactif | Pas un "plein écran" TUI |
| Textual | ~45 Mo, 120 FPS | MIT | Oui | Oui | Moyenne-Élevée | Vrai dashboard terminal plein écran, réactif | Plus lourd, plus de code, overkill pour la Phase 1 |
| argparse brut | Quasi nul | PSF | Oui | Oui | Faible | Stdlib, zéro dépendance | Pas de couleurs/tables/autocomplétion "gratuites" |

## 3. Base de données locale

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| SQLite (stdlib `sqlite3`) | Quasi nul, fichier unique | Domaine public | Oui | Oui | Faible | Zéro serveur, zéro install, transactionnel, fiable | Pas fait pour des écritures concurrentes massives (non pertinent ici) |
| PostgreSQL | Serveur permanent, ~50-100 Mo+ | PostgreSQL Licence | Oui | Oui | Élevée | Très robuste, multi-utilisateur | Overkill pour un usage mono-utilisateur sur 4 Gio de RAM |
| JSON/fichiers plats | Quasi nul | - | Oui | Oui | Très faible | Simple à inspecter | Pas de requêtes, pas d'index, risque de corruption sur écriture concurrente |

## 4. Tâches en arrière-plan

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| Custom asyncio + SQLite | Minimal | interne | Oui | Oui | Moyenne (à écrire) | Colle exactement au schéma déjà défini dans le prompt (§13), pas de dépendance, pas de broker | Il faut l'écrire et le tester nous-mêmes |
| Huey (backend SQLite) | ~120 Mo/worker | MIT | Oui | Oui | Faible | Mature, retry/cron intégrés | Ajoute un 2e "modèle de tâche" à maintenir en parallèle du nôtre |
| Celery / RQ | Élevé, nécessite Redis | BSD | Oui | Oui | Élevée | Très robuste à grande échelle | Redis = process permanent supplémentaire → contraire à la règle low-resource |

## 5. IA Gateway / multi-fournisseurs

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| Adapter interne + LiteLLM **SDK** (pas le proxy) | Léger (import Python) | MIT | Oui (le SDK ; les APIs derrière peuvent être payantes) | Oui | Moyenne | Traduction vers 100+ fournisseurs déjà écrite et testée, on garde notre propre interface | Dépendance externe à surveiller (projet qui évolue vite) |
| Tout coder à la main (un adapter par fournisseur) | Léger | interne | Oui | Oui | Élevée (répétitif) | Contrôle total, zéro dépendance | Réinvente ce que LiteLLM fait déjà bien |
| LiteLLM proxy (serveur séparé) | Nécessite PostgreSQL + Redis en prod | MIT | Oui | Oui | Élevée | Multi-clients, budgets, clés virtuelles | Beaucoup trop lourd pour un usage personnel mono-machine |

## 6. Interface Web

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| Jinja2 (SSR) + htmx + Alpine.js | ~29 Ko JS total, pas de build | BSD/MIT | Oui | Oui | Faible | Pas de Node.js/npm/webpack requis, tout servi par FastAPI directement | Moins "riche" qu'une SPA pour des interactions très complexes (pas notre besoin ici) |
| React/Vue (SPA) | Chaîne de build lourde (npm, node_modules) | MIT | Oui | Oui | Élevée | Écosystème riche | Toolchain Node.js lourde à faire tourner/maintenir sur la machine cible |

## 7. Système de plugins/connecteurs

| Solution | Ressources | Licence | Gratuit | Linux | Complexité | Avantages | Limites |
|---|---|---|---|---|---|---|---|
| Classe ABC `Connector` + chargement dynamique de dossier | Nul | interne | Oui | Oui | Faible | Simple, lisible, suffisant en V1 | Pas de packaging/distribution externe de plugins |
| Pluggy (entry points) | Nul (pur Python) | MIT | Oui | Oui | Moyenne | Standard éprouvé (pytest), évolutif vers de vrais plugins tiers | Un peu de cérémonie (hookspecs) pour un besoin encore simple en Phase 5 |

## 8. Connecteurs de recherche — état réel des APIs

| Source | API publique | Clé requise | Limite notable |
|---|---|---|---|
| GitHub | Oui (REST + Search) | Optionnelle (recommandée) | Search API : 30 req/min avec token |
| GitLab | Oui (REST) | Optionnelle | Quota raisonnable |
| Codeberg (Forgejo/Gitea API) | Oui | Optionnelle | Pas de quota agressif documenté |
| SourceForge | Limitée (Allura API) | Non | API peu riche, pas de CI |
| Bitbucket | Oui | Optionnelle | 5 users gratuits (n/a pour lecture publique) |
| Gitee | Oui | Optionnelle | Écosystème surtout chinois |
| Hugging Face Hub | Oui, sans clé | Non (optionnelle) | Aucune limite bloquante en usage normal |
| PyPI | Métadonnées par paquet uniquement (`/pypi/<nom>/json`) | Non | **Pas de recherche floue officielle** (XML-RPC désactivé depuis 2020) |
| npm | Oui, sans clé (`/-/v1/search`) | Non | Aucune limite bloquante documentée |

---

Ces tableaux nourrissent directement les choix figés dans `DECISIONS.md`.
