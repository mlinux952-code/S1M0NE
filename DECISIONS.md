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

- **Décision initiale (Phase 0, PROPOSED) : interface interne `AIProvider` (ABC) + adaptateurs, le
  premier s'appuyant sur le SDK Python de LiteLLM.**
- **DÉCISION RÉVISÉE ET IMPLÉMENTÉE (Phase 6) : interface interne `AIProvider` (ABC) conservée,
  mais LiteLLM abandonné au profit d'adaptateurs maison en `httpx` direct (déjà une dépendance du
  projet), sur exactement le même principe que `connectors.Connector` (Phase 5).** `[DECIDED]`
- Justification de la révision : à l'usage, les 3 fournisseurs retenus (Groq, OpenRouter, Ollama)
  exposent tous une API REST simple (2 sont compatibles format OpenAI, le 3e un JSON tout aussi
  direct) — LiteLLM aurait ajouté des dizaines de sous-dépendances (dont `tiktoken`, compilé) pour
  un gain marginal, ce qui contredit la règle low-resource-first appliquée partout ailleurs dans
  le projet (SQLite plutôt que Postgres/Redis, moteur de tâches maison plutôt que Celery/RQ...).
  Si un jour le nombre de fournisseurs à supporter explose, LiteLLM (ou Pluggy pour les vrais
  plugins tiers, cf. D9) pourra être réévalué — même logique que la révision D9 (Bitbucket/Gitee).
- Fournisseurs implémentés, gratuits et sans carte bancaire, choix du fournisseur par défaut
  laissé à l'utilisateur dans `config/config.toml` (`[ai] default_provider`) :
  - **Groq** (recommandé par défaut) : rapide, quota généreux (~30 req/min, jusqu'à 500k
    tokens/jour selon le modèle), vérifié par recherche web en direct (septembre 2026).
  - **OpenRouter** : catalogue de modèles `:free` qui change régulièrement (vérifié volatile en
    recherche directe) — modèle configurable sans toucher au code, message d'erreur explicite si
    le modèle par défaut disparaît du catalogue gratuit.
  - **Ollama (local)** : à la demande explicite de l'utilisateur, curieux de l'option locale.
    Rappel du prompt (aucun grand modèle local sur cette machine ~4 Gio RAM) toujours respecté :
    seul un modèle minuscule (1B, quantifié) est proposé par défaut, présenté honnêtement comme
    lent et réservé aux tests/besoin de confidentialité — pas comme un usage quotidien confortable.
- Anti-hallucination (mega-prompt §10/§25) : un fournisseur qui échoue (clé absente, quota
  dépassé, service injoignable, format de réponse inattendu) lève toujours une erreur explicite
  et actionnable — jamais de réponse inventée à la place.

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

- **Décision : toute commande shell exécutée par S1M0NE passe par une liste blanche +
  une classification READ/WRITE/EXECUTE/ADMIN, avec confirmation explicite obligatoire pour
  toute commande destructrice.** `[DECIDED — implémenté en Phase 9]`
- Justification : le prompt insiste sur "ne jamais exécuter aveuglément" — principe posé dès la
  Phase 1 (liste blanche du terminal web, lecture seule) et complété en Phase 9 avec une vraie
  classification par permission et une capacité d'exécution réelle (au-delà du lecture-seule).
- **Périmètre final, plus restreint que l'intention initiale** : `core/permissions.py` définit
  un catalogue volontairement modeste (`pwd`, `whoami`, `date`, `uptime`, `df`, `free`, `ps`,
  `ls`, `cat`, `mkdir`, `touch`, `cp`, `mv`, `rm`, `rmdir`). **`dd`, `mkfs`, `shutdown`,
  `reboot`, `chmod`/`chown` massifs et tout accès réseau sensible ne sont PAS implémentés, quel
  que soit le niveau de permission** — écartés délibérément : danger réel pour la seule machine
  de l'utilisateur, sans bénéfice clair pour un assistant personnel. Toute commande qui touche à
  un fichier est en plus bornée à `fs_root` (DATA_DIR par défaut, configurable), même au niveau
  ADMIN — jamais le disque entier.
- Deux profils de confiance distincts : terminal local (`s1mone exec`, niveau ADMIN par défaut —
  même confiance qu'un shell classique lancé par le propriétaire) et terminal web (`/api/exec`,
  niveau READ par défaut — plus prudent car l'interface web écoute sur `0.0.0.0` sans
  authentification). Les commandes destructrices exigent toujours une confirmation explicite,
  y compris côté web via un flux en deux temps (409 puis renvoi avec `confirm=true`).

## D11 — Emplacement des données

- **Décision : variable `DATA_DIR` configurable, par défaut `~/S1M0NE/data` sur le disque
  système ; possibilité de pointer vers le disque secondaire NTFS pour les gros projets, avec
  vérification de montage avant toute écriture (jamais supposé monté).** `[PROPOSED]`

## D12 — Mémoire (Phase 7)

- **Décision : Memory Manager (`core/memory.py`) au-dessus de la table SQLite `memory` déjà créée
  en Phase 1 (4 niveaux : temporary/session/project/persistent). API minimaliste
  `remember/recall/forget/list_memory`, upsert applicatif (delete-then-insert) plutôt qu'une
  contrainte SQL UNIQUE, pour rester compatible sans migration avec les bases déjà créées par des
  installations antérieures à la Phase 7.** `[DECIDED]`
- **Premier consommateur réel : la conversation IA (Phase 6).** Le niveau `persistent` stocke
  l'historique de chat (`chat_history`, borné à 40 messages pour respecter les quotas gratuits en
  tokens/minute) : la conversation continue d'une session à l'autre (CLI comme web) au lieu de
  repartir de zéro à chaque redémarrage. `s1mone chat --reset` / `/reset` en interactif /
  `POST /api/chat/reset` (web) permettent de repartir d'une page blanche à la demande.
- **Auto-connaissance** : un message système décrivant S1M0NE (nom, architecture, machine cible)
  est injecté au début de chaque conversation — corrige le comportement observé où l'assistant
  ne savait pas ce qu'était S1M0NE (aucun contexte sur lui-même sans cela). Personnalisable en
  écrasant la clé `ai_system_prompt` (niveau `persistent`) sans toucher au code.
- Les niveaux `session` et `project` restent réservés (pas encore consommés) : `session` pour un
  futur état propre à chaque onglet navigateur/terminal, `project` pour un futur lien avec la
  table `projects`. Pas d'UI dédiée de navigation dans la mémoire pour l'instant (uniquement
  consommée en interne par le chat) — pourrait arriver plus tard si le besoin se précise.

## D13 — Plugins tiers (Phase 8)

- **Décision : Pluggy comme moteur de plugins (même bibliothèque que pytest), avec deux points
  d'extension officiels (`s1mone_connectors`, `s1mone_task_handlers`) et deux canaux de
  découverte : fichiers `.py` déposés dans `plugins_local/` (usage personnel, zéro friction) et
  paquets pip avec entry point `s1mone` (distribution réelle).** `[DECIDED]` Referme la question
  ouverte par D9 ("Pluggy réévalué en Phase 8").
- **Frontière de confiance explicite, différente de celle de la Phase 9** : la liste blanche de
  commandes système (D10) protège contre l'exécution *automatique* de commandes par S1M0NE
  lui-même ; un plugin, lui, est du code Python que l'utilisateur choisit *explicitement*
  d'installer (en déposant un fichier ou en faisant `pip install`) — il tourne avec les mêmes
  droits que S1M0NE, sans sandbox supplémentaire. C'est la même frontière que pour n'importe quel
  écosystème de plugins (extensions de navigateur, paquets npm, plugins pytest...) : la
  protection est l'acte d'installation explicite, pas un bac à sable technique. Documenté dans
  `plugins_local/README.md` pour que ce soit clair pour l'utilisateur.
- **Priorité aux composants intégrés en cas de conflit de nom** : un plugin ne peut jamais
  redéfinir un connecteur ou un type de tâche déjà fourni par S1M0NE (prévisibilité avant
  extensibilité), avec avertissement loggué plutôt qu'échec silencieux.
- Limite connue acceptée : si plusieurs plugins implémentent le même hook, une exception dans
  l'un peut empêcher les suivants de répondre pour cet appel précis (le cœur de S1M0NE n'est
  jamais affecté, seule la contribution des plugins pour ce tour l'est). Acceptable pour un outil
  personnel mono-utilisateur ; à revoir avec un appel hook par plugin isolé si le besoin se
  précise avec plusieurs plugins simultanés en usage réel.

---

## D14 — Authentification de l'interface web (post-plan-initial, NEXT_STEPS.md §A.1)

- **Constat de sécurité** : jusqu'ici, l'interface web (Phase 2) ne demandait aucun mot de passe.
  Acceptable tant qu'elle n'écoutait que sur `localhost`, mais devient un vrai risque dès que la
  machine est accessible depuis le réseau local (ou au-delà) — n'importe qui pourrait consulter
  les tâches, la mémoire/conversation IA, lancer des recherches ou déclencher des commandes
  autorisées.
- **Décision : cookie de session signé HMAC-SHA256, sans dépendance externe (`core/auth.py`),
  opt-in via `S1MONE_WEB_PASSWORD` dans `.env`.** `[DECIDED]` Alternatives écartées :
  - *Bibliothèque de sessions dédiée (`itsdangerous`, `starlette-login`, etc.)* — écartée : le
    besoin (un seul mot de passe partagé, un seul "utilisateur", pas de rôles) est trivial à
    coder en ~40 lignes avec `hmac`/`hashlib` de la stdlib ; ajouter une dépendance pour ça irait
    contre LOW RESOURCE FIRST et la philosophie déjà actée en D9/D10 (préférer un adaptateur
    maison à une bibliothèque lourde quand le besoin est simple et stable).
  - *Stockage de session côté serveur (fichier, table SQLite)* — écarté : un cookie signé est
    stateless (rien à nettoyer, rien qui grossisse avec le temps), suffisant pour un utilisateur
    unique, et évite d'ajouter une table `sessions` à surveiller/purger.
  - *Authentification HTTP Basic* — écartée : moins ergonomique (pas de vraie page de
    déconnexion propre, alerte navigateur disgracieuse), alors qu'une page `/login` Jinja2 coûte
    la même chose à écrire vu que le reste de l'interface l'est déjà (Phase 2).
- **Opt-in, jamais un mur bloquant par défaut** : si `S1MONE_WEB_PASSWORD` est absent, le
  comportement historique (aucune authentification) est conservé à l'identique — seul un
  avertissement est loggué au démarrage. Cohérent avec le principe déjà appliqué à Ollama/D10 :
  ne jamais casser un usage local existant pour une fonctionnalité de sécurité que tout le monde
  n'a pas besoin d'activer (ex. usage strictement local sur une machine déjà physiquement
  protégée).
- **Exemptions explicites** : `/login` (sinon impossible de se connecter) et `/static/` (feuilles
  de style, pas d'information sensible). Tout le reste — y compris `/api/*` — est protégé, avec
  une réponse adaptée au type de requête (redirection 303 vers `/login` pour du HTML, 401 JSON
  pour les appels `/api/*`, pour ne pas casser silencieusement d'éventuels clients API).
- **Dépendance ajoutée : `python-multipart`.** Nécessaire pour que FastAPI/Starlette parsent le
  formulaire HTML de `/login` (`Form(...)` / `request.form()` l'exigent inconditionnellement dans
  la version installée, même sans upload de fichier). Petite bibliothèque pure Python, gratuite,
  jugée conforme à LOW RESOURCE FIRST (même logique que les dépendances déjà acceptées : FastAPI,
  httpx, Typer...).
- Limite connue acceptée : un seul mot de passe partagé (pas de comptes multiples, pas de rôles)
  — cohérent avec l'hypothèse mono-utilisateur du méga-prompt ; à revoir seulement si S1M0NE doit
  un jour servir plusieurs personnes distinctes.

---

## D15 — Démarrage automatique (post-plan-initial, NEXT_STEPS.md §A.3)

- **Décision : `systemd --user`, jamais un service système root.** `[DECIDED]` Cohérent avec
  l'hypothèse "machine personnelle, utilisateur unique" du méga-prompt : pas besoin de droits
  administrateur, le service tourne avec exactement les mêmes droits que l'utilisateur qui lance
  `s1mone` à la main — pas de surface d'attaque supplémentaire liée à un service root.
- **Alternative écartée : cron `@reboot`.** Fonctionne, mais ne redémarre pas le processus s'il
  plante en cours de route (`systemd` le fait nativement avec `Restart=on-failure`), et ne
  fournit pas de commandes d'état/logs pratiques (`systemctl status`, `journalctl`). Gardée
  uniquement comme repli documenté si `systemctl` est absent (ex. certaines distributions
  minimalistes, conteneurs).
- **`loginctl enable-linger` jamais automatisé par le script d'installation** : c'est un réglage
  qui change un comportement global du compte utilisateur (processus qui continuent de tourner
  même sans session ouverte) — décision jugée trop invasive pour être prise silencieusement par
  un script, donc seulement documentée/affichée en fin d'installation, à l'utilisateur de
  l'activer s'il le souhaite.
- **Pas de test automatisé (`pytest`) pour cette fonctionnalité** : un vrai test nécessiterait un
  bus de session `systemd --user` actif, absent par construction d'un environnement d'exécution
  sandboxé/CI classique. Vérifié manuellement à la place (génération correcte du fichier
  d'unité, détection propre et message actionnable quand le bus de session est indisponible).

---

## D16 — Mémoire "project" enfin consommée (post-plan-initial, NEXT_STEPS.md §B.4)

- **Décision : namespacer la clé stockée (`"<project_id>::<clé>"`) plutôt qu'ajouter une colonne
  `project_id` à la table `memory`.** `[DECIDED]` Évite toute migration de schéma sur des bases
  déjà installées (cohérent avec le principe déjà appliqué en Phase 7 pour `remember()` — voir
  plus haut dans ce fichier) ; le reste du code (recall/forget/list_memory) ne voit jamais ce
  détail d'implémentation, qui reste entièrement interne à `core/memory.py`.
- **Changement de comportement assumé, sans rétrocompatibilité silencieuse** : `remember()`,
  `recall()` et `forget()` lèvent maintenant `ValueError` si `level="project"` est utilisé SANS
  `project_id` (auparavant, cette combinaison était silencieusement acceptée mais n'était jamais
  réellement exploitée nulle part dans le code, cf. NEXT_STEPS.md : "réservé depuis la Phase 7,
  jamais consommé"). Comme aucun usage réel n'existait, ce n'est pas traité comme une régression
  mais comme la première vraie définition de ce que "project" signifie.
- **`core/projects.py` : CRUD complet sur la table `projects`** (existait depuis la Phase 1, vide
  jusqu'ici). `delete_project()` supprime par défaut la mémoire associée (`--keep-memory` pour
  l'éviter) — un projet supprimé ne doit jamais laisser une mémoire orpheline invisible qui
  continuerait à occuper la base sans qu'on puisse la retrouver autrement que par la connaissance
  fortuite de son id.
- **Premier (et pour l'instant seul) consommateur : la conversation IA** (`s1mone chat --project
  <id ou nom>`, et `project_id` dans `POST /api/chat`). Plutôt qu'un système de "session courante"
  implicite (ex: un fichier `.s1mone_current_project` sur le disque), le choix est explicite à
  chaque appel — plus verbeux, mais sans état caché à synchroniser entre CLI et web, cohérent
  avec le reste de l'architecture (aucun état de session côté client).

---

## D17 — Tâches récurrentes (post-plan-initial, NEXT_STEPS.md §B.1)

- **Décision : intervalle simple ("30s", "5m", "2h", "1d") plutôt qu'une syntaxe cron complète.**
  `[DECIDED]` Une syntaxe cron réelle nécessiterait soit de l'écrire à la main (risque de bugs sur
  les cas limites : fuseaux horaires, jours du mois...), soit d'ajouter une dépendance
  (`croniter`) pour un besoin personnel qui se résume presque toujours à "répéter toutes les N
  minutes/heures/jours". Compromis assumé : pas d'équivalent direct à "tous les lundis à 9h" —
  si ce besoin apparaît un jour, `croniter` (pure Python, léger) sera reconsidéré à ce moment-là,
  pas anticipé maintenant (YAGNI).
- **Aucune nouvelle boucle asyncio : le tick de planification est greffé sur le worker de tâches
  existant** (`tasks/manager.py worker_loop`), pas un second processus/thread. Une échéance créée
  passe par le chemin normal d'une tâche (file d'attente, limites de ressources du Resource
  Manager, notifications B.3 incluses) — aucune logique d'exécution dupliquée.
- **Une planification dont le type de tâche a disparu se désactive automatiquement** (avec
  avertissement journalisé) plutôt que d'échouer indéfiniment au même tick, à l'identique du
  traitement déjà appliqué aux notifications ratées (B.3) et à la Phase 8 (plugin qui disparaît) :
  aucune erreur silencieuse en boucle infinie.

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
IA (Phase 6)       : abstraction interne `AIProvider` + adaptateurs httpx (Groq, OpenRouter,
                     Ollama local) — voir D7, révisé par rapport à la piste LiteLLM envisagée
                     en Phase 0
```

Aucune dépendance ne nécessite Docker, Kubernetes, Redis, PostgreSQL, Elasticsearch ou Node.js
pour que S1M0NE fonctionne. Conforme à la règle LOW RESOURCE FIRST (§3 du méga-prompt).
