# NEXT_STEPS.md — Pistes de réflexion pour la suite

> **Mise à jour** : sur mandat explicite "tous et plus encore", les trois catégories A, B et C
> ci-dessous (11 pistes) ont toutes été implémentées, testées et poussées. Détail et dates dans
> `PROJECT_STATE.md`. Ce document reste tel quel comme trace de la réflexion d'origine.

> Les 9 phases du plan initial (méga-prompt) sont terminées, testées et validées sur la machine
> réelle (voir `PROJECT_STATE.md`). Ce document ne fait pas partie du plan original : c'est une
> réflexion sur "et maintenant ?", à discuter avec l'utilisateur avant de se lancer dans quoi que
> ce soit — contrairement aux phases précédentes, il n'y a pas encore de mandat "vas-y, fais
> tout" sur ce qui suit.

Le plan initial a construit les fondations d'une "maison numérique" complète : terminal + web,
tâches, recherche, IA, mémoire, sécurité, plugins. Trois grandes familles de pistes se dégagent
pour continuer, classées par ordre de priorité recommandé.

## A. Consolider l'existant (recommandé en premier — protège ce qui est déjà construit)

1. **Authentification du terminal web.** C'est le point le plus important resté ouvert : `s1mone
   web` écoute sur `0.0.0.0` sans aucun mot de passe. Le niveau de permission READ par défaut
   (Phase 9) limite les dégâts possibles, mais n'importe quel appareil du réseau local peut
   aujourd'hui lire le dashboard, l'historique de chat, lancer des recherches, etc. Une solution
   simple et gratuite : un mot de passe unique dans `.env` (`S1MONE_WEB_PASSWORD`), vérifié via un
   cookie de session signé (stdlib `hmac`/`secrets`, pas de dépendance lourde) — cohérent avec la
   philosophie "low-resource, pas de framework d'auth complexe" du projet.
2. **Sauvegarde de la base SQLite.** Toute la mémoire de S1M0NE (conversations, tâches, cache)
   vit dans un seul fichier (`data/s1mone.db`). Une commande `s1mone backup` (copie horodatée,
   éventuellement vers le disque secondaire NTFS mentionné dans DECISIONS.md §D11) coûte très peu
   à écrire et protège tout le reste.
3. **Démarrage automatique.** Un service `systemd --user` (ou une entrée crontab `@reboot`) pour
   que `s1mone web` tourne en permanence dès que la machine démarre, sans terminal ouvert — fait
   réellement de S1M0NE une "maison numérique" ambiante plutôt qu'un outil qu'on lance à la main.
4. **Vigilance modèles IA gratuits.** Le bug réel de la Phase 6 (modèle Groq passé en accès
   payant sans préavis) peut se reproduire. Une commande `s1mone chat --check` (ping chaque
   fournisseur configuré, signale un modèle qui a disparu) transformerait un bug détecté après
   coup en avertissement proactif.

## B. Nouvelles capacités (étendent la vision, plus ambitieux)

5. **Tâches récurrentes (façon cron).** Actuellement une tâche s'exécute une fois, à la demande.
   Un type de tâche `recurring` (ou un champ `schedule` dans le Task Manager) permettrait par
   exemple "relance cette recherche tous les jours à 8h" — cohérent avec Task Manager (Phase 3)
   déjà en place, sans dépendance externe (juste une boucle de vérification dans le worker
   existant).
6. **Assistant IA "agentique".** Combiner ce qui existe déjà séparément : laisser l'assistant
   (Phase 6) déclencher lui-même une recherche (Phase 5) ou une commande en liste blanche
   (Phase 9) quand c'est pertinent pour répondre, au lieu que l'utilisateur tape les commandes à
   la main. C'est la synthèse naturelle de tout ce qui a été construit, mais plus gros chantier
   (function calling / tool use côté fournisseur IA, à vérifier lequel le supporte gratuitement).
7. **Notifications locales.** Un signal (notification bureau Linux via `notify-send`, ou un badge
   sur le dashboard) quand une tâche de fond se termine, plutôt que d'avoir à revenir voir
   `s1mone task list`.
8. **Utilisation réelle du niveau mémoire `project`** (réservé depuis la Phase 7, jamais
   consommé) : permettrait de garder un contexte séparé par projet/dossier de travail.

## C. Polish (déjà identifié, à faible enjeu)

9. Page web dédiée à la mémoire (actuellement CLI uniquement : `s1mone memory ...`).
10. Pagination/tri des résultats de `s1mone search` (pertinence, étoiles GitHub, date).
11. Un vrai paquet pip d'exemple pour un plugin distribué (entry point `s1mone`), au-delà des
    fichiers locaux déjà démontrés dans `plugins_local/examples/`.

## Recommandation

Si une seule chose devait être faite ensuite : **A.1 (authentification web)**. C'est la seule
lacune qui touche à la sécurité réelle de l'utilisateur (les autres points de la Phase 9
protègent contre l'exécution de commandes, pas contre la simple lecture/usage à distance de
l'interface). Le reste peut suivre dans l'ordre A → B → C, ou selon l'envie du moment — comme
pour les phases précédentes, l'utilisateur peut aussi simplement dire "tout" et l'agent
enchaînera dans cet ordre.
