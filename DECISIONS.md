# DECISIONS.md — Décisions d'architecture (Phase 0)

Statut des tags utilisés : `VERIFIED` (testé/mesuré par nous), `PROPOSED` (décision prise sur
base de recherche, pas encore testée en pratique sur S1M0NE), `REQUIRES TEST` (à valider en
Phase 1+).

## D1 — Langage & environnement

- **Décision : Python 3 + environnement virtuel (`venv`)** pour tout le cœur (`core`, `api`,
  `cli`, `search`, `tasks`, `ai`, `memory`, `security`). `[PROPOSED]`
- Justification : déjà présent nativement sur Linux Mint 22.3, léger, immense écosystème,
  correspond à toutes les briques choisies ci-dessous.
- JavaScript limité au strict nécessaire côté navigateur (htmx + Alpine.js), sans Node.js/npm
  requis pour faire tourner S1M0NE (seulement si on veut un jour un outil de dev optionnel).

## D2 — Serveur web / API

- **Décision : FastAPI + Uvicorn (1 seul worker au démarrage).** `[PROPOSED]`
- Justification : async natif → indispensable pour lancer les recherches vers plusieurs
  connecteurs en parallèle sans bloquer ; empreinte mémoire mesurée plus faible que Flask ;
  validation Pydantic gratuite ; docs OpenAPI auto utiles pour tester chaque endpoint pendant le
  développement. Voir `ARCHITECTURE_OPTIONS.md` §1.
- Limite acceptée : légèrement plus de structure imposée que Flask — jugé acceptable.

## D3 — Terminal S1M0NE

- **Décision : Typer (CLI à commandes) + Rich (sortie formatée) + prompt_toolkit (mode REPL
  interactif avec historique/autocomplétion).** `[PROPOSED]`
- Justification : couvre 100% du besoin exprimé (§6 du méga-prompt : historique, autocomplétion,
  couleurs, tables, monitoring) sans le poids d'un framework TUI plein écran.
- Textual est noté comme option future si on veut un vrai "dashboard terminal" plein écran, mais
  reporté (pas nécessaire pour Phase 1-2).

## D4 — Stockage / mémoire

- **Décision : SQLite (module stdlib `sqlite3`), un seul fichier `.db` dans `DATA_DIR`.**
  `[PROPOSED]`
- Justification : zéro serveur, zéro dépendance, adapté à un usage mono-utilisateur, transactions
  fiables, facilement inspectable (`sqlite3 s1mone.db`).
- Complément : petits fichiers JSON/TOML uniquement pour la configuration statique (pas pour les
  données qui évoluent).

## D5 — Task Manager

- **Décision : implémentation maison (asyncio + table SQLite `tasks`), pas de Huey/Celery/RQ.**
  `[PROPOSED]`
- Justification : le méga-prompt définit déjà un schéma de tâche précis et un besoin d'intégration
  fine avec le Resource Manager (réduire le parallélisme selon RAM/CPU) — un système externe
  ajouterait une deuxième source de vérité sans réel gain, et Celery/RQ nécessitent Redis (process
  permanent supplémentaire, contraire à la règle low-resource).
- Alternative sérieuse rejetée : Huey (backend SQLite) — solide, mais redondant avec ce que le
  prompt demande déjà de construire nous-mêmes.

## D6 — Cache

- **Décision : table SQLite dédiée `cache` avec colonnes `key, value, source, created_at, ttl`.**
  `[PROPOSED]`
- Justification : évite une dépendance de plus (pas de Redis), cohérent avec D4, suffisant pour
  des volumes personnels.

## D7 — AI Gateway

- **Décision : interface interne `AIProvider` (ABC) + adaptateurs. Le premier adaptateur réel
  s'appuiera sur le SDK Python de LiteLLM (pas le proxy serveur) pour bénéficier gratuitement de
  la traduction vers 100+ fournisseurs, tout en gardant notre propre abstraction au-dessus (pour
  pouvoir remplacer LiteLLM plus tard sans casser S1M0NE).** `[PROPOSED — Phase 6, pas maintenant]`
- Justification : évite de réécrire à la main un adaptateur par fournisseur ; le proxy LiteLLM
  (qui nécessite PostgreSQL+Redis en prod) est explicitement écarté car incompatible avec la
  contrainte low-resource.
- Rappel du prompt : aucun grand modèle local sur cette machine — l'IA lourde est systématiquement
  déportée vers une API distante (gratuite en priorité).

## D8 — Interface Web

- **Décision : Jinja2 (rendu serveur) + htmx + Alpine.js, aucune étape de build front, aucun
  Node.js requis pour faire fonctionner S1M0NE.** `[PROPOSED]`
- Justification : ~29 Ko de JS total, cohérent avec "léger", évite d'installer une chaîne
  npm/webpack sur une machine à 4 Gio de RAM et disque système limité.

## D9 — Connecteurs / plugins

- **Décision Phase 5 (connecteurs) : interface `Connector` (classe abstraite Python) +
  découverte dynamique d'un dossier `connectors/`, sans framework de plugin externe pour l'instant.**
  `[PROPOSED]`
- **Décision Phase 8 (vrais plugins tiers) : réévaluer Pluggy à ce moment-là**, une fois le besoin
  de plugins *externes/tiers* réellement confirmé (le prompt le distingue explicitement des
  connecteurs internes).
- Ordre d'implémentation des connecteurs (du plus simple/fiable au plus incertain) :
  1. **npm** (API publique sans clé, sans quota bloquant — le plus simple pour valider le pipeline).
  2. **Hugging Face Hub** (API publique sans clé).
  3. **GitHub** (API riche, mais respecter la limite de 30 req/min sur `/search` → passage
     obligatoire par le Cache Manager).
  4. **GitLab**, **Codeberg/Gitea**.
  5. **PyPI** : implémenté en mode dégradé et **transparent** — recherche par nom exact via
     `/pypi/<nom>/json` uniquement, avec un message clair "PyPI ne propose plus de recherche
     floue officielle" plutôt que de simuler un résultat inventé (règle anti-hallucination du
     prompt, §10/§25).
  6. Bitbucket, Gitee, SourceForge : en dernier, APIs moins riches ou moins prioritaires pour un
     usage perso.

- **Mise à jour (vérification en direct, session Phase 5 étape 6) : Bitbucket et Gitee sont
  RETIRÉS DÉFINITIVEMENT du plan de connecteurs.** `[DECIDED]`
  - **Bitbucket** : Atlassian a définitivement supprimé l'API de recherche globale de dépôts
    (`GET /2.0/repositories?q=...`) le 14 avril 2026 (changelog officiel `CHANGE-2770`/`CHANGE-3081`,
    confirmé par plusieurs sources indépendantes lors d'une vérification directe). Il ne reste que
    `GET /2.0/repositories/{workspace}`, qui exige de déjà connaître le nom exact de l'espace de
    travail — impossible de faire une recherche par mot-clé comme pour GitHub/GitLab/Codeberg.
  - **Gitee** : l'endpoint documenté `GET /api/v5/search/repositories` répond `200 OK` mais
    renvoie systématiquement `total_count: 0`, y compris pour des requêtes très populaires
    (`redis`, `vue`...) dont on peut vérifier qu'il existe pourtant des centaines de résultats via
    le moteur de recherche web de Gitee lui-même (`so.gitee.com`). L'API publique semble non
    fonctionnelle pour un accès anonyme. Implémenter ce connecteur aurait fait croire à
    l'utilisateur qu'"aucun résultat" existe alors que c'est faux — inacceptable au regard de la
    règle anti-hallucination (§10/§25) : mieux vaut ne pas avoir le connecteur du tout que d'avoir
    un connecteur qui ment silencieusement par omission.
  - **SourceForge** : conservé, mais en **mode dégradé transparent** (même principe que PyPI) —
    pas de recherche par mot-clé possible (pas d'endpoint dédié ; la recherche HTML classique
    répond `403` aux requêtes automatisées), uniquement un lookup par nom exact de projet via
    `GET /rest/p/<shortname>`. Chaque résultat porte `extra.exact_match_only=True` et la
    description du connecteur affiche explicitement "MODE DÉGRADÉ".
  - **Bilan final Phase 5** : 7 connecteurs actifs — npm, Hugging Face, GitHub, GitLab, Codeberg
    (recherche floue complète) + PyPI, SourceForge (mode dégradé, nom exact uniquement). Bitbucket
    et Gitee ne seront pas implémentés sauf si leurs APIs redeviennent fonctionnelles à l'avenir
    (à revérifier si le besoin se représente).

## D10 — Sécurité / permissions

- **Décision : dès la Phase 1, toute commande shell exécutée par S1M0NE passe par une liste
  blanche + une classification READ/WRITE/EXECUTE/ADMIN, avec confirmation explicite obligatoire
  pour toute commande destructrice (rm, dd, mkfs, shutdown, reboot, chmod/chown massifs, réseau
  sensible).** `[PROPOSED — à implémenter dès le noyau, pas en Phase 9 seulement]`
- Justification : le prompt insiste sur "ne jamais exécuter aveuglément" — plus simple et plus
  sûr de construire cette barrière dès le début que de la retrofiter plus tard.

## D11 — Emplacement des données

- **Décision : variable `DATA_DIR` configurable, par défaut `~/S1M0NE/data` sur le disque
  système ; possibilité de pointer vers le disque secondaire NTFS pour les gros projets, avec
  vérification de montage avant toute écriture (jamais supposé monté).** `[PROPOSED]`

---

## Récapitulatif de la stack retenue pour la Phase 1 (fondation)

```text
Langage        : Python 3 (venv)
API/serveur    : FastAPI + Uvicorn
CLI            : Typer + Rich + prompt_toolkit
Base de données: SQLite (stdlib sqlite3)
Config         : fichier config.toml + .env pour les secrets
Logs           : logging stdlib, rotation via RotatingFileHandler
Frontend (Phase 2+): Jinja2 + htmx + Alpine.js
Tâches (Phase 3+)  : moteur asyncio + SQLite maison
IA (Phase 6+)      : abstraction interne + LiteLLM SDK comme 1er adaptateur
```

Aucune dépendance ne nécessite Docker, Kubernetes, Redis, PostgreSQL, Elasticsearch ou Node.js
pour que S1M0NE fonctionne. Conforme à la règle LOW RESOURCE FIRST (§3 du méga-prompt).
