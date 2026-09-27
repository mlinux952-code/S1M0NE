"""
core/auth.py — Authentification minimale du terminal web (NEXT_STEPS.md §A.1).

Contexte : `s1mone web` écoute sur 0.0.0.0 (mega-prompt : accessible depuis le réseau local pour
un usage "maison numérique" multi-appareils), mais jusqu'ici sans aucune protection — n'importe
quel appareil du réseau pouvait lire le dashboard, l'historique de chat, lancer des recherches,
voire des commandes système en liste blanche (Phase 9, niveau READ par défaut). Ce module ajoute
une protection par mot de passe unique, optionnelle et rétrocompatible :

- Si `S1MONE_WEB_PASSWORD` n'est pas défini dans `.env` : comportement historique, aucun
  changement (avec un avertissement au démarrage de `s1mone web`).
- Si défini : toutes les routes (sauf `/login`, `/static/*`) exigent un cookie de session valide,
  obtenu via `/login`.

Volontairement SANS dépendance supplémentaire (pas de `itsdangerous`, pas de base de données de
sessions) : un cookie signé par HMAC-SHA256 (stdlib `hmac`/`hashlib`), avec expiration intégrée
et vérification en temps constant (`hmac.compare_digest`). Adapté à un usage mono-utilisateur,
cohérent avec la philosophie "low-resource first" du projet.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from core.config import settings

COOKIE_NAME = "s1mone_session"
SESSION_LIFETIME_SECONDS = 7 * 24 * 3600  # 7 jours

# Chemins accessibles sans authentification, même quand elle est activée.
EXEMPT_PATH_PREFIXES = ("/login", "/static/")


def _sign(expiry: int, secret: str) -> str:
    message = f"s1mone-auth:{expiry}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def create_session_cookie(password: str) -> str:
    """Construit la valeur du cookie de session, valide `SESSION_LIFETIME_SECONDS`."""
    expiry = int(time.time()) + SESSION_LIFETIME_SECONDS
    signature = _sign(expiry, password)
    return f"{expiry}.{signature}"


def verify_session_cookie(cookie_value: str | None, password: str) -> bool:
    """Vérifie la signature ET l'expiration. Jamais d'exception : une valeur malformée est
    simplement invalide (comportement défensif, mega-prompt §10)."""
    if not cookie_value or "." not in cookie_value:
        return False
    expiry_str, _, signature = cookie_value.partition(".")
    try:
        expiry = int(expiry_str)
    except ValueError:
        return False
    if expiry < int(time.time()):
        return False
    expected = _sign(expiry, password)
    return hmac.compare_digest(expected, signature)


def check_password(candidate: str) -> bool:
    """Compare le mot de passe fourni au mot de passe configuré, en temps constant."""
    expected = settings.web_password
    if not expected:
        return False
    return hmac.compare_digest(expected, candidate)


def is_path_exempt(path: str) -> bool:
    return any(path == "/login" or path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)
