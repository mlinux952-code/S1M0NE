#!/usr/bin/env bash
#
# uninstall_autostart.sh — Retire le service systemd --user installé par install_autostart.sh
# (NEXT_STEPS.md §A.3). Arrête le service s'il tourne, le désactive, puis supprime son fichier
# d'unité. N'importe quoi d'autre (code, données, config) n'est jamais touché.

set -euo pipefail

SERVICE_FILE="$HOME/.config/systemd/user/s1mone.service"

if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd introuvable : rien à désinstaller via ce script." >&2
    exit 1
fi

echo "== Désinstallation du démarrage automatique de S1M0NE =="

systemctl --user stop s1mone.service 2>/dev/null || true
systemctl --user disable s1mone.service 2>/dev/null || true

if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    echo "Fichier de service supprimé : $SERVICE_FILE"
else
    echo "Aucun fichier de service trouvé ($SERVICE_FILE) — rien à supprimer."
fi

systemctl --user daemon-reload 2>/dev/null || true

echo ""
echo "Service désinstallé. S1M0NE ne démarrera plus automatiquement."
echo "(Si tu avais activé 'loginctl enable-linger', tu peux le désactiver avec :"
echo "    loginctl disable-linger \$USER"
echo ")"
