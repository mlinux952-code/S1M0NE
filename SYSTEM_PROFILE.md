# SYSTEM_PROFILE.md — Référence matérielle officielle de S1M0NE

**Statut global : VERIFIED** — confirmé le 2026-09-26 par exécution réelle de
`scripts/audit_system.sh` sur la machine cible (`omrane@omrane-Inspiron-3520`), sortie complète
récupérée et analysée. Les valeurs déclarées initialement se sont révélées quasi exactes.

## Machine cible (vérifiée)

| Composant | Valeur vérifiée | Détail de la mesure |
|---|---|---|
| OS | Linux Mint 22.3 "Zena" (base Ubuntu 24.04 "noble") | `/etc/os-release` |
| Noyau | 7.0.0-31-generic (x86_64) | `uname -a` |
| CPU | Intel Core i3-3110M @ 2.40GHz, 2 cœurs / 4 threads (Ivy Bridge, famille 6 modèle 58) | `lscpu` |
| RAM | 3.7 GiB total | `free -h` |
| Swap | 3.9-4.04 GiB | `free -h` |
| GPU | Mesa Intel HD Graphics 4000 (Ivy Bridge, rev 09), pilote i915 | `lspci` + `glxinfo` |
| Disque système | `/dev/sda3` ext4, 117 GiB total, 85 GiB libres (24 % utilisés) | `df -hT` |
| Disque secondaire | `/dev/sdc2` NTFS (fuseblk), 932 GiB total, 926 GiB libres, monté sur `/media/omrane/D0C698F3C698DB54` | `df -hT` / `lsblk -f` |
| Python | 3.12.3 | `python3 --version` |
| pip | 26.2.1 (dans le venv du projet) | `pip3 --version` |
| Git | 2.43.0 | `git --version` |
| Node.js | v18.19.1 (présent mais non requis par S1M0NE) | `node --version` |
| sqlite3 (CLI) | absent — sans impact, le module `sqlite3` intégré à Python est utilisé par S1M0NE | `sqlite3 --version` |
| Réseau | `wlp7s0` (WiFi) actif — `enp9s0` (Ethernet) inactif | `ip -brief addr` |
| Températures au repos | CPU ~51-52°C (seuils : high 72°C, crit 90°C) — aucun risque actuel | `sensors` |

## Charge réelle observée au repos (avec Firefox ouvert)

Donnée importante pour le Resource Manager (Phase 3+) : même "au repos", avec un usage normal
du PC (navigateur ouvert), il ne reste que **~1.7 Gio de RAM disponible** sur 3.7 Gio (Firefox et
ses process de contenu consomment à eux seuls plus de 2 Gio cumulés). Cela confirme et renforce
la nécessité des décisions déjà prises (pas de Redis, pas de gros process permanent, parallélisme
limité) : S1M0NE doit rester utilisable **en plus** de l'usage courant du PC, pas seulement sur
une machine vide.

Aucun service lourd ou inhabituel détecté parmi les services systemd actifs (uniquement les
services standards de bureau Linux Mint : réseau, impression, bluetooth, thermald, etc.).

## Classification

**Machine LOW-END confirmée par la mesure réelle**, avec une marge encore plus réduite que prévu
une fois l'usage courant (navigateur, etc.) pris en compte. Toutes les conséquences déjà tirées en
Phase 0 restent valables, renforcées :
- pas de LLM local ;
- un seul processus serveur S1M0NE ;
- SQLite plutôt que tout serveur de base de données ;
- pas de Redis/Celery/Elasticsearch/Docker lourd ;
- déport de l'IA lourde vers des APIs distantes gratuites.

## Historique

- 2026-09-26 — Spécifications initiales déclarées par l'utilisateur (voir Git, commit Phase 0).
- 2026-09-26 — **Vérification réelle effectuée** via `scripts/audit_system.sh`, valeurs confirmées
  à l'identique (écarts négligeables liés aux méthodes d'arrondi GiB/Go), + informations
  logicielles et charge réelle ajoutées.


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
