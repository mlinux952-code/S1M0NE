"""
web/app.py — Web Gateway de S1M0NE (Phase 2).

Principes appliqués :
- L'interface web NE DUPLIQUE AUCUNE LOGIQUE : elle appelle exactement les mêmes fonctions que
  la CLI (system.monitor, system.healthcheck). Un seul cerveau, plusieurs façades (mega-prompt §5).
- Le "terminal web" n'exécute JAMAIS de commande shell arbitraire : seule une liste blanche stricte
  de commandes en lecture seule est exposée (mega-prompt §15/§31 — sécurité avant tout).
- Frontend léger : Jinja2 (rendu serveur) + htmx + Alpine.js servis en local (vendored), sans
  build Node.js, conforme à DECISIONS.md (D8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.logging_setup import get_logger
from system.healthcheck import run_all_checks
from system.monitor import get_platform_info, get_snapshot, resource_level

logger = get_logger("s1mone.web")

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Liste blanche stricte : seules ces commandes en LECTURE SEULE sont exposées via le web.
# Aucune commande système, aucune écriture, aucune exécution arbitraire (§15/§31 du mega-prompt).
ALLOWED_WEB_COMMANDS = {"status", "system", "version"}


def _run_command(command: str) -> dict[str, Any]:
    if command not in ALLOWED_WEB_COMMANDS:
        raise HTTPException(
            status_code=403,
            detail=f"Commande non autorisée depuis le terminal web : '{command}'. "
            f"Autorisées : {sorted(ALLOWED_WEB_COMMANDS)}",
        )
    if command == "system":
        snap = get_snapshot()
        return {
            "platform": get_platform_info(),
            "resources": snap.as_dict(),
            "resource_level": resource_level(snap),
        }
    if command == "status":
        return run_all_checks()
    if command == "version":
        return {"name": "S1M0NE", "version": "0.2.0", "phase": "Phase 2 - Interface Web"}
    raise AssertionError("unreachable")  # garde-fou : ne doit jamais arriver


def create_app() -> FastAPI:
    app = FastAPI(title="S1M0NE", version="0.2.0")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/api/health")
    def api_health() -> dict[str, Any]:
        return run_all_checks()

    @app.get("/api/system")
    def api_system() -> dict[str, Any]:
        snap = get_snapshot()
        return {
            "platform": get_platform_info(),
            "resources": snap.as_dict(),
            "resource_level": resource_level(snap),
        }

    @app.get("/api/cli/{command}")
    def api_cli(command: str) -> dict[str, Any]:
        return {"command": command, "output": _run_command(command)}

    @app.get("/partials/system", response_class=HTMLResponse)
    def partial_system(request: Request) -> HTMLResponse:
        snap = get_snapshot()
        return templates.TemplateResponse(
            request,
            "partials/system.html",
            {
                "platform": get_platform_info(),
                "resources": snap.as_dict(),
                "level": resource_level(snap),
            },
        )

    @app.get("/partials/health", response_class=HTMLResponse)
    def partial_health(request: Request) -> HTMLResponse:
        report = run_all_checks()
        return templates.TemplateResponse(
            request,
            "partials/health.html",
            {"checks": report["checks"], "overall_ok": report["overall_ok"]},
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "dashboard.html", {})

    @app.get("/terminal", response_class=HTMLResponse)
    def terminal_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "terminal.html", {"allowed_commands": sorted(ALLOWED_WEB_COMMANDS)}
        )

    logger.info("Application FastAPI S1M0NE initialisée (Phase 2).")
    return app


app = create_app()
