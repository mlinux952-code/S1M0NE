# SYSTEM_PROFILE.md — Référence matérielle officielle de S1M0NE

Statut global : **DECLARED (déclaré par l'utilisateur)** — non vérifié directement par l'agent,
car l'agent travaille dans un sandbox cloud de développement, distinct de la machine cible réelle.

> Règle anti-hallucination appliquée : on n'affirme jamais avoir vérifié ce qu'on n'a pas vérifié.
> Ces valeurs viennent du prompt fourni par l'utilisateur, qui a confirmé qu'il s'agit bien des
> caractéristiques réelles de son Dell. Elles sont donc **fiables mais non ré-auditées par nous**.
> Un script (`scripts/audit_system.sh`) est fourni ci-dessous pour que tu puisses le lancer
> toi-même sur ta machine et confirmer/actualiser ce fichier à tout moment (Phase 0 le permet,
> Phase 10 l'exige à nouveau pour l'optimisation).

## Machine cible (déclarée)

| Composant | Valeur déclarée |
|---|---|
| OS | Linux Mint 22.3 |
| Architecture | x86_64 |
| CPU | Intel Core i3-3110M, 2 cœurs physiques, 4 threads, 2.40 GHz |
| RAM | 3.7 GiB utilisables |
| Swap | 3.9 GiB |
| GPU | Intel intégré (3e génération), pilote i915 |
| Disque système | ~118.7 GiB total, ~86 GiB disponibles |
| Disque secondaire | ~931.5 GiB, NTFS, ~926 GiB disponibles |

## Classification

**Machine LOW-END** confirmée :
- 2 cœurs / 4 threads à 2.4 GHz (CPU d'entrée de gamme, ~12 ans d'âge, sans instructions AVX2 modernes) ;
- moins de 4 GiB de RAM utilisable → aucune marge pour des services lourds en parallèle ;
- GPU Intel HD 4000 (3e gen) : **aucune accélération IA locale sérieuse possible** (pas de CUDA, support OpenVINO/oneAPI limité et peu fiable sur ce silicium) ;
- swap présent (3.9 GiB) mais un swap fortement sollicité sur un disque lent dégraderait sévèrement la réactivité.

Conséquence directe sur l'architecture (détaillée dans `ARCHITECTURE_OPTIONS.md` et `DECISIONS.md`) :
- **pas de LLM local** (même quantifié en 4 bits, un modèle 7B nécessite ~4-5 GiB de RAM rien que pour les poids : incompatible) ;
- **un seul processus serveur permanent** (le cœur S1M0NE), pas de pile "microservices + broker" ;
- **SQLite** plutôt que tout serveur de base de données ;
- **pas de Redis/Celery/Elasticsearch/Docker lourd** ;
- déport de l'IA lourde et des recherches gourmandes vers des APIs distantes gratuites.

## Informations manquantes à confirmer sur la machine réelle

Ces éléments ne sont **pas** dans le prompt d'origine — ils doivent être mesurés avant la Phase 1
pour finaliser certains choix (ex : version de Python disponible conditionne le typing moderne).

- [ ] Version exacte de Python 3 installée (`python3 --version`)
- [ ] Présence de `pip`, `venv` (`python3 -m venv --help`)
- [ ] Version de Git (`git --version`)
- [ ] Présence de Node.js (pour l'installation d'outils front éventuels — normalement inutile ici)
- [ ] Navigateur par défaut (pour tester le Dashboard Web)
- [ ] Interfaces réseau actives (`ip a`)
- [ ] Point de montage réel du disque secondaire NTFS (`lsblk -f`, `df -hT`)
- [ ] Charge au repos actuelle (RAM/CPU déjà utilisés par l'OS + Cinnamon/XFCE, etc.)
- [ ] Présence de `lm-sensors` pour la température CPU (optionnel)

## Script d'audit à exécuter sur le Dell

Voir `scripts/audit_system.sh` — lecture seule, ne modifie rien, n'installe rien.
Lance-le puis colle-moi la sortie : je mettrai à jour ce fichier avec la mention **VERIFIED**.

```bash
cd S1M0NE
bash scripts/audit_system.sh > audit_output.txt
cat audit_output.txt
```
