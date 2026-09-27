#!/usr/bin/env bash
#
# install_autostart.sh — Démarrage automatique de S1M0NE (NEXT_STEPS.md §A.3).
#
# Installe un service `systemd --user` qui lance `s1mone web` à la connexion, le relance
# automatiquement s'il plante (Restart=on-failure), et peut aussi démarrer dès le boot de la
# machine (avant toute connexion) via `loginctl enable-linger` — voir le message affiché en fin
# de script.
#
# Aucun droit root nécessaire (service --user, pas système). Ne touche à rien en dehors de
# ~/.config/systemd/user/s1mone.service et de l'état du service.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

echo "== Installation du démarrage automatique de S1M0NE =="
echo "Dossier du projet : $PROJECT_DIR"
echo ""

if ! command -v systemctl >/dev/null 2>&1; then
    cat >&2 << EOF
systemd introuvable sur cette machine : le démarrage automatique via ce script n'est pas
disponible ici.

Alternative possible (moins robuste, pas de redémarrage auto en cas de plantage) :
    crontab -e
puis ajoute la ligne :
    @reboot $PROJECT_DIR/venv/bin/s1mone web >> $PROJECT_DIR/logs/autostart.log 2>&1
EOF
    exit 1
fi

if [ ! -x "$PROJECT_DIR/venv/bin/s1mone" ]; then
    echo "ERREUR : $PROJECT_DIR/venv/bin/s1mone introuvable. Lance ./install.sh d'abord." >&2
    exit 1
fi

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
SERVICE_FILE="$SERVICE_DIR/s1mone.service"

sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$PROJECT_DIR/scripts/s1mone.service.template" > "$SERVICE_FILE"
echo "Fichier de service écrit : $SERVICE_FILE"
echo ""

if ! systemctl --user daemon-reload 2>/tmp/s1mone_systemctl_err.log; then
    cat >&2 << EOF
ERREUR : impossible de parler à systemd --user (session utilisateur non disponible ici, par
exemple dans un conteneur/sandbox sans session de connexion réelle). Détail :
$(cat /tmp/s1mone_systemctl_err.log)

Le fichier de service a quand même été écrit dans $SERVICE_FILE. Réessaie cette commande après
t'être connecté normalement (session graphique ou SSH avec une vraie session utilisateur) :
    systemctl --user daemon-reload && systemctl --user enable --now s1mone.service
EOF
    rm -f /tmp/s1mone_systemctl_err.log
    exit 1
fi
rm -f /tmp/s1mone_systemctl_err.log

systemctl --user enable --now s1mone.service

echo ""
echo "S1M0NE est démarré et démarrera automatiquement à ta prochaine connexion."
echo ""
echo "Pour qu'il démarre aussi AVANT toute connexion (dès le boot, sans ouvrir de session), active"
echo "le \"lingering\" (ne nécessite pas les droits root, une seule fois) :"
echo "    loginctl enable-linger \$USER"
echo ""
echo "Commandes utiles :"
echo "    systemctl --user status s1mone     # état du service"
echo "    journalctl --user -u s1mone -f     # logs en direct"
echo "    systemctl --user restart s1mone    # redémarrage (ex: après un git pull)"
echo "    systemctl --user stop s1mone       # arrêt"
echo "    systemctl --user disable s1mone    # désactive le démarrage automatique"
echo "    ./scripts/uninstall_autostart.sh   # désinstalle complètement le service"
