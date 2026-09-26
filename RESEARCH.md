# RESEARCH.md — Recherche approfondie Phase 0

Statut : recherches web réellement effectuées le 2026-09-26. Chaque affirmation ci-dessous est
sourcée. Ce document ne remplace pas `ARCHITECTURE_OPTIONS.md` (qui compare) ni `DECISIONS.md`
(qui tranche) — il rassemble la matière première.

---

## 1. Serveur web / API : FastAPI vs Flask

- FastAPI est **asynchrone (ASGI/uvicorn)**, natif async/await, validation automatique via
  Pydantic, documentation OpenAPI générée automatiquement. Empreinte mémoire mesurée dans un
  benchmark récent : **~42 Mo pour FastAPI contre ~45-48 Mo pour Flask**, démarrage ~0.6s contre
  0.8-1.2s [1](https://craftyourstartup.com/cys-docs/insights/fastapi-vs-flask-2025-comprehensive-guide/).
- Sous charge, FastAPI tient nettement plus de requêtes/s pour un usage I/O-bound (recherches
  réseau multi-sources, appels API externes) — exactement notre cas d'usage
  [2](https://www.codecademy.com/article/fastapi-vs-flask-key-differences-performance-and-use-cases).
- Flask reste imbattable pour un script minimal ou une petite page HTML isolée, mais n'a pas
  d'async natif — pénalisant dès qu'on interroge 5-10 connecteurs en parallèle
  [3](https://developersvoice.com/blog/python/fastapi_django_flask_architecture_guide/).

## 2. Interfaces terminal : Rich / Textual / prompt_toolkit

Comparatif détaillé trouvé (2026) :

| Lib | Type | Mémoire | Cas d'usage |
|---|---|---|---|
| Rich | Formatage de sortie (tables, panels, logs colorés) | Très léger, rendu paresseux | Sortie CLI soignée |
| Textual | Framework TUI plein écran (CSS-like, widgets réactifs) | ~45 Mo, 120 FPS sur 1000 widgets | Appli interactive plein écran type "dashboard terminal" |
| prompt_toolkit | REPL / saisie interactive, autocomplétion | ~28 Mo | Historique, autocomplétion, moteur derrière IPython/pgcli |

Sources : [1](https://www.pistack.xyz/posts/2026-07-01-python-terminal-ui-libraries-textual-rich-prompt-toolkit-urwid/),
[2](https://botmonster.com/coding/build-tui-apps-python-textual-rich/).

Conclusion recherche : Rich + prompt_toolkit couvrent déjà tout le cahier des charges du
"terminal avancé" (historique, autocomplétion, couleurs, tables, logs) sans le poids d'un
framework TUI plein écran. Textual reste une option future si on veut un vrai "tableau de bord
terminal" plein écran (Phase ultérieure, pas Phase 1).

## 3. Abstraction multi-fournisseurs IA : LiteLLM

- LiteLLM est un projet **open source (MIT)** qui fournit une API unifiée au format OpenAI vers
  100+ fournisseurs (OpenAI, Anthropic, Google, HuggingFace, Ollama en local, etc.)
  [1](https://ai-tldr.dev/learn/production-llmops/cost-latency-optimization/litellm-gateway/).
- Existe en **SDK Python léger** (à importer directement, pas de service séparé) ou en **serveur
  proxy** complet [2](https://skywork.ai/skypage/en/LiteLLM-A-Deep-Dive-into-the-Unified-Gateway-for-AI-Models/1972870863895195648).
- Attention : le **proxy** LiteLLM en production recommande PostgreSQL + Redis
  [3](https://www.braintrust.dev/articles/best-llm-gateways-2026) — **incompatible avec notre
  contrainte low-resource**. Le **SDK seul**, lui, n'a pas cette exigence et peut être appelé
  directement depuis notre AI Gateway custom.

## 4. Sources de code / connecteurs

- Panorama des forges : GitHub (propriétaire, gratuit avec quotas), GitLab CE (gratuit,
  auto-hébergeable), Bitbucket (5 users gratuits), Gitee (Chine, gratuit avec compte),
  Codeberg = instance **Forgejo** (fork libre de Gitea, GPL-3.0, géré par une association à but
  non lucratif), SourceForge (gratuit pour l'open source, API limitée, pas de CI)
  [1](https://githubalternatives.com/).
- **Limite de débit critique sur l'API de recherche GitHub** : seulement **30 requêtes/minute**
  avec un token personnel pour l'endpoint `/search` (contre 5000/h pour l'API générale) — un
  détail souvent ignoré qui doit être pris en compte dans le Cache Manager et le Resource Manager
  [2](https://github.com/orgs/community/discussions/179480),
  [3](https://stackoverflow.com/questions/37602893/github-search-limit-results).
- Codeberg/Gitea exposent une API REST compatible et libre, sans quota agressif documenté pour un
  usage raisonnable.

## 5. Hugging Face / PyPI / npm

- **Hugging Face Hub** expose une API publique **sans clé** : `GET /api/models`,
  `/api/datasets`, `/api/spaces`, avec tri (`sort=trendingScore|downloads|likes`), filtrage par
  tags, pagination par curseur [1](https://dev.to/scrapemint/the-hugging-face-hub-is-a-free-json-api-rank-trending-ai-models-without-a-key-39cb).
  Un token optionnel augmente juste les limites de débit.
- **PyPI** : ⚠️ point important trouvé — l'ancienne recherche XML-RPC (`pip search`) est
  **désactivée depuis fin 2020** et ne doit jamais être utilisée
  [1](https://pip.pypa.io/en/stable/cli/pip_search/),
  [2](https://discuss.python.org/t/pip-search-is-still-broken/18680). Il n'existe **pas d'API
  JSON officielle de recherche** sur PyPI aujourd'hui. Deux options réalistes :
  1. utiliser l'endpoint JSON **par paquet exact** `https://pypi.org/pypi/<nom>/json` (officiel,
     stable, gratuit) quand on connaît déjà le nom ;
  2. pour une vraie recherche floue, s'appuyer sur un connecteur tiers (ex. libraries.io) ou sur
     une recherche croisée via GitHub/HF plutôt que d'inventer un scraping fragile de la page
     HTML `pypi.org/search`.
  → Ce point doit être documenté explicitement dans le connecteur PyPI pour ne pas laisser croire
  à une "recherche PyPI" qui n'existe pas réellement.
- **npm** : `GET https://registry.npmjs.org/-/v1/search?text=...&size=...` est une **API
  publique, sans clé, sans limite de débit contraignante documentée**, toujours active en 2026
  [3](https://stackoverflow.com/questions/34071621/query-npmjs-registry-via-api),
  [4](https://dev.to/0012303/npm-registry-api-discover-packages-in-any-tech-niche-no-key-needed-3c72).

## 6. Système de plugins Python

- **Pluggy** (utilisé par pytest) : système de hooks léger, pur Python, zéro dépendance lourde,
  mécanisme de découverte via `importlib.metadata` entry points
  [1](https://lab.abilian.com/Tech/Programming%20Techniques/Plugins/),
  [2](https://eli.thegreenplace.net/2026/plugins-case-study-pluggy/).
- Alternative "faite maison" : classes Python implémentant une interface `Connector` (ABC),
  chargées dynamiquement depuis un dossier `connectors/`. Plus simple à comprendre pour une V1,
  suffisant tant qu'on ne distribue pas de plugins tiers packagés.

## 7. Interface Web légère : htmx + Alpine.js vs React

- htmx (~14 Ko) + Alpine.js (~15 Ko) = ~29 Ko total, **sans étape de build, sans Node.js,
  sans bundler** — s'oppose à React (~47 Ko + toute une chaîne d'outils npm/webpack/vite)
  [1](https://www.pkgpulse.com/guides/htmx-vs-alpinejs-2026).
- htmx gère les échanges avec le serveur (fragments HTML), Alpine.js gère l'état/interactions
  purement côté client (menus, toggles). Combo largement utilisé avec FastAPI + Jinja2
  [2](https://blog.nashtechglobal.com/building-a-modern-web-app-with-htmx-alpinejs/).
- Sur une machine à 2 cœurs / 4 Gio, éviter une chaîne de build front (webpack/vite/npm install
  de centaines de Mo de `node_modules`) est un gain direct en simplicité et en disque.

## 8. Gestionnaire de tâches en arrière-plan

- Comparatif Celery / RQ / Huey / arq : **Huey avec backend SQLite** est l'option consommant le
  moins de mémoire (~120 Mo/worker) et ne nécessite **aucun broker externe (pas de Redis)**,
  pensée justement pour "single-server or edge device"
  [1](https://markaicode.com/vs/celery-alternatives/),
  [2](https://markaicode.com/alternatives/celery-alternatives/).
- Cependant, S1M0NE a un besoin de Task Manager **très spécifique et déjà précisément défini**
  dans le méga-prompt (schéma `id/status/created_at/.../QUEUED/RUNNING/...`, historique,
  annulation, intégration Resource Manager). Ajouter Huey reviendrait à faire cohabiter deux
  systèmes de suivi de tâches (celui de Huey + le nôtre) pour un volume de tâches qui restera
  faible (usage personnel, pas un SaaS multi-utilisateurs).
- → Voir `DECISIONS.md` : on retient une implémentation **maison, asyncio + SQLite**, plus
  simple à auditer et 100% alignée sur le schéma déjà spécifié, sans dépendance supplémentaire.

---

## Sources consultées (liste)

GitHub, GitLab, Codeberg/Forgejo, SourceForge, Bitbucket, Gitee, Hugging Face Hub, PyPI
(pypi.org + Warehouse docs), npm registry, ainsi que des comparatifs techniques indépendants sur
FastAPI/Flask, Rich/Textual/prompt_toolkit, LiteLLM/OpenRouter/Portkey, Pluggy/Stevedore/Yapsy,
htmx/Alpine.js/React, Celery/RQ/Huey/arq. Tous les liens sont cités inline ci-dessus.
