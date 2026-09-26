# S1M0NE

> "Une petite machine peut héberger une grande idée si l'architecture est intelligente."

S1M0NE est une plateforme personnelle intelligente ("maison numérique") : terminal avancé,
interface web légère, moteur de recherche multi-source, orchestrateur, mémoire locale, et
architecture extensible vers l'IA — conçue en priorité pour tourner confortablement sur une
machine modeste (2 cœurs, ~4 Gio de RAM).

## État du projet

**Phase 0 — Découverte, terminée, en attente de validation.** Aucun code applicatif n'existe
encore : voir les documents ci-dessous avant toute chose.

| Document | Contenu |
|---|---|
| [`SYSTEM_PROFILE.md`](./SYSTEM_PROFILE.md) | Fiche matérielle de la machine cible |
| [`RESEARCH.md`](./RESEARCH.md) | Recherche technique sourcée (frameworks, APIs, librairies) |
| [`ARCHITECTURE_OPTIONS.md`](./ARCHITECTURE_OPTIONS.md) | Tableaux comparatifs par composant |
| [`DECISIONS.md`](./DECISIONS.md) | Décisions d'architecture retenues et justifiées |
| [`PROJECT_STATE.md`](./PROJECT_STATE.md) | État courant, prochaine étape, mémoire du projet |
| [`scripts/audit_system.sh`](./scripts/audit_system.sh) | Script d'audit lecture seule pour ta machine réelle |

## Philosophie

- Low resource first : SQLite, un seul processus serveur, pas de Docker/Kubernetes/Redis/ES.
- Zéro dépense obligatoire : APIs gratuites et logiciels libres en priorité.
- Développement par petites phases testées, jamais un gros bloc de code non vérifié.
- Aucune commande destructrice n'est exécutée sans confirmation explicite.

## Démarrage (à venir — Phase 1)

```bash
git clone <url-du-depot> S1M0NE
cd S1M0NE
./install.sh   # sera créé en Phase 1
s1mone status
```
