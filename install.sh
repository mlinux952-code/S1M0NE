#!/usr/bin/env bash
#
# install.sh — Installation de S1M0NE (Phase 1 : fondation).
#
# Ce script :
#   1. vérifie la version de Python (>= 3.11, requis pour tomllib) ;
#   2. crée un environnement virtuel ./venv ;
#   3. installe le paquet en mode éditable + dépendances ;
#   4. crée les dossiers de données/logs ;
#   5. prépare .env depuis .env.example si absent ;
#   6. initialise la base SQLite ;
#   7. lance les tests ;
#   8. affiche les instructions de démarrage.
#
# Ne supprime rien, ne touche à rien en dehors du dossier du projet.

set -euo pipefail

cd "$(dirname "$0")"

echo "== 1. Vérification de Python =="
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERREUR : python3 introuvable. Installe-le avant de continuer." >&2
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')
echo "Python détecté : $PY_VERSION"
if [ "$PY_OK" != "1" ]; then
    echo "ERREUR : Python >= 3.11 requis (module 'tomllib' nécessaire pour lire config.toml)." >&2
    echo "Version détectée : $PY_VERSION" >&2
    exit 1
fi

echo ""
echo "== 2. Création de l'environnement virtuel (./venv) =="
if [ ! -d "venv" ]; then
    python3 -m venv venv
else
    echo "venv déjà présent, réutilisation."
fi

echo ""
echo "== 3. Installation des dépendances =="
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -e . pytest

echo ""
echo "== 4. Création des dossiers =="
mkdir -p data logs data/cache

echo ""
echo "== 5. Préparation du fichier .env =="
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ".env créé à partir de .env.example (à compléter toi-même, jamais commité)."
else
    echo ".env déjà présent, non modifié."
fi

echo ""
echo "== 6. Initialisation de la base SQLite =="
./venv/bin/python -c "from core.db import init_db; init_db()"

echo ""
echo "== 7. Exécution des tests =="
./venv/bin/python -m pytest -q

echo ""
echo "======================================================"
echo " Installation terminée avec succès."
echo ""
echo " Pour démarrer :"
echo "   source venv/bin/activate"
echo "   s1mone status"
echo "   s1mone system"
echo "======================================================"
