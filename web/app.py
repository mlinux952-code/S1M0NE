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

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from core.db import init_db
from core.logging_setup import get_logger
from core.timeutil import format_timestamp
from system.healthcheck import run_all_checks
from system.monitor import get_platform_info, get_snapshot, resource_level
from tasks import manager as task_manager
from tasks.registry import available_types

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


class TaskSubmitRequest(BaseModel):
    """Corps de requête pour POST /api/tasks (Phase 3 - Task Manager)."""

    type: str
    parameters: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie du processus 's1mone web' : un seul processus permanent qui héberge à la
    fois le serveur HTTP ET le worker de tâches en tâche de fond (mega-prompt : pas de service
    supplémentaire, low-resource first). Le worker s'arrête proprement à l'extinction."""
    init_db()
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(task_manager.worker_loop(interval_seconds=2.0, stop_event=stop_event))
    logger.info("Worker de tâches démarré en arrière-plan dans le processus web.")
    try:
        yield
    finally:
        stop_event.set()
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        logger.info("Worker de tâches arrêté proprement.")


def create_app() -> FastAPI:
    app = FastAPI(title="S1M0NE", version="0.3.0", lifespan=lifespan)
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

    @app.get("/api/task-types")
    def api_task_types() -> dict[str, Any]:
        return {"types": available_types()}

    @app.get("/api/tasks")
    def api_tasks_list(status: str | None = None, limit: int = 50) -> dict[str, Any]:
        return {"tasks": task_manager.list_tasks(status=status, limit=limit)}

    @app.post("/api/tasks", status_code=201)
    def api_tasks_submit(payload: TaskSubmitRequest) -> dict[str, Any]:
        try:
            task_id = task_manager.submit_task(payload.type, payload.parameters)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"task": task_manager.get_task(task_id)}

    @app.get("/api/tasks/{task_id}")
    def api_tasks_get(task_id: str) -> dict[str, Any]:
        task = task_manager.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"Tâche introuvable : {task_id}")
        return {"task": task}

    @app.post("/api/tasks/{task_id}/cancel")
    def api_tasks_cancel(task_id: str) -> dict[str, Any]:
        ok = task_manager.cancel_task(task_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail=f"Tâche introuvable ou déjà terminée, impossible d'annuler : {task_id}",
            )
        return {"task": task_manager.get_task(task_id)}

    @app.get("/partials/tasks", response_class=HTMLResponse)
    def partial_tasks(request: Request) -> HTMLResponse:
        tasks = task_manager.list_tasks(limit=20)
        for t in tasks:
            t["created_display"] = format_timestamp(t.get("created_at"))
            t["finished_display"] = format_timestamp(t.get("finished_at"))
        return templates.TemplateResponse(
            request,
            "partials/tasks.html",
            {"tasks": tasks, "task_types": available_types()},
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
