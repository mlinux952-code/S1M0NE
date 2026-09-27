#!/usr/bin/env bash
#
# audit_system.sh — Audit matériel/logiciel en LECTURE SEULE pour S1M0NE.
#
# Ce script NE MODIFIE RIEN, N'INSTALLE RIEN, NE SUPPRIME RIEN.
# Il ne fait qu'interroger le système et afficher un rapport.
# Objectif : confirmer/actualiser SYSTEM_PROFILE.md avec des données réellement mesurées.
#
# Usage :
#   bash scripts/audit_system.sh
#   bash scripts/audit_system.sh > audit_output.txt   # pour sauvegarder le rapport

set -uo pipefail

section () {
    echo ""
    echo "==================== $1 ===================="
}

section "OS / DISTRIBUTION"
if [ -f /etc/os-release ]; then cat /etc/os-release; else echo "N/A"; fi

section "NOYAU / ARCHITECTURE"
uname -a

section "CPU"
if command -v lscpu >/dev/null 2>&1; then
    lscpu
else
    grep -m1 "model name" /proc/cpuinfo
    nproc --all
fi

section "RAM / SWAP"
free -h

section "GPU"
if command -v lspci >/dev/null 2>&1; then
    lspci | grep -iE "vga|3d|display"
else
    echo "lspci indisponible"
fi
echo "Pilote graphique en cours :"
if command -v glxinfo >/dev/null 2>&1; then
    glxinfo -B 2>/dev/null | grep -iE "OpenGL renderer|OpenGL version"
else
    echo "glxinfo non installé (optionnel : sudo apt install mesa-utils)"
fi

section "STOCKAGE"
df -hT
echo ""
echo "Partitions / systèmes de fichiers détectés :"
lsblk -f 2>/dev/null || echo "lsblk indisponible"

section "TEMPÉRATURE (si disponible)"
if command -v sensors >/dev/null 2>&1; then
    sensors
else
    echo "lm-sensors non installé (optionnel : sudo apt install lm-sensors)"
fi

section "RÉSEAU"
ip -brief addr 2>/dev/null || ifconfig 2>/dev/null || echo "Outils réseau indisponibles"

section "LOGICIELS DE BASE"
echo -n "Python3 : "; python3 --version 2>/dev/null || echo "absent"
echo -n "pip3    : "; pip3 --version 2>/dev/null || echo "absent"
echo -n "venv    : "; python3 -c "import venv; print('module venv disponible')" 2>/dev/null || echo "module venv absent"
echo -n "sqlite3 : "; sqlite3 --version 2>/dev/null || echo "absent (le module Python intégré fonctionne quand même)"
echo -n "git     : "; git --version 2>/dev/null || echo "absent"
echo -n "node    : "; node --version 2>/dev/null || echo "absent (normalement pas requis pour S1M0NE)"
echo -n "curl    : "; curl --version 2>/dev/null | head -n1 || echo "absent"

section "CHARGE ACTUELLE AU REPOS"
echo "Utilisation mémoire :"
free -m
echo ""
echo "Top 10 processus par RAM :"
ps aux --sort=-%mem | head -n 11

section "SERVICES ACTIFS (systemd, aperçu)"
if command -v systemctl >/dev/null 2>&1; then
    systemctl list-units --type=service --state=running --no-pager | head -n 30
else
    echo "systemctl indisponible"
fi

echo ""
echo "==================== FIN DE L'AUDIT ===================="
echo "Copie/colle la sortie complète pour mise à jour de SYSTEM_PROFILE.md."
