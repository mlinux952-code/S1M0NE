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

from ai.base import ProviderError
from ai.gateway import available_providers
from ai.gateway import converse as ai_converse
from ai.gateway import get_conversation_history, reset_conversation
from connectors.engine import available_connectors, search_all
from core import permissions
from core.config import settings
from core.db import init_db
from core.logging_setup import get_logger
from core.shell_runner import run_command as run_shell_command
from core.timeutil import format_timestamp
from plugins.manager import list_plugins
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


class ExecRequest(BaseModel):
    """Corps de requête pour POST /api/exec (Phase 9 - Sécurité).

    `confirm` doit être renvoyé à `true` pour une deuxième soumission après un premier refus
    409 (commande destructrice) : jamais d'exécution destructrice sans confirmation explicite
    du client, même côté web."""

    command: str
    confirm: bool = False


class ChatRequest(BaseModel):
    """Corps de requête pour POST /api/chat (Phase 6 - AI Gateway).

    L'historique n'est plus renvoyé par le client à chaque appel (contrairement à la première
    version de la Phase 6) : depuis la Phase 7 (Mémoire), le serveur est la seule source de
    vérité, persistée en SQLite (voir ai/gateway.py). Le client peut relire l'historique via
    GET /api/chat/history (ex. au chargement de la page) et le vider via POST /api/chat/reset.
    """

    message: str
    provider: str | None = None
    model: str | None = None
    reset: bool = False


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

    @app.get("/api/exec/catalog")
    def api_exec_catalog() -> dict[str, Any]:
        """Liste blanche complète (Phase 9), annotée de ce que ce terminal web a le droit
        d'exécuter avec son niveau de permission actuel (config.toml [security].web_permission_level)."""
        level = permissions.web_level()
        return {
            "level": level.name,
            "commands": [
                {
                    "name": spec.name,
                    "permission": spec.permission.name,
                    "destructive": spec.destructive,
                    "takes_path": spec.takes_path,
                    "description": spec.description,
                    "allowed": spec.permission <= level,
                }
                for spec in permissions.available_commands()
            ],
        }

    @app.post("/api/exec")
    def api_exec(payload: ExecRequest) -> dict[str, Any]:
        """Exécute une commande système réelle en liste blanche (Phase 9), bornée au niveau de
        permission web (plus prudent par défaut que le terminal local, voir config.toml)."""
        if not payload.command.strip():
            raise HTTPException(status_code=400, detail="Commande vide.")
        try:
            result = run_shell_command(
                payload.command,
                level=permissions.web_level(),
                fs_root=settings.fs_root,
                confirmed=payload.confirm,
            )
        except permissions.UnknownCommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except permissions.PermissionError_ as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except permissions.ConfirmationRequiredError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"{exc} Renvoyer la même requête avec confirm=true pour l'exécuter.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

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

    @app.get("/api/plugins")
    def api_plugins() -> dict[str, Any]:
        """Plugins tiers chargés (Phase 8), + l'effet visible : connecteurs et types de tâches
        disponibles au total (intégrés + plugins)."""
        return {
            "plugins": list_plugins(),
            "plugins_dir": str(settings.plugins_dir),
            "connectors": [c["name"] for c in available_connectors()],
            "task_types": available_types(),
        }

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

    @app.get("/api/search")
    async def api_search(q: str = "", sources: str | None = None, limit: int = 10) -> dict[str, Any]:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
        return await search_all(q, limit_per_source=limit, sources=source_list)

    @app.get("/api/search/sources")
    def api_search_sources() -> dict[str, Any]:
        return {"sources": available_connectors()}

    @app.get("/partials/search-results", response_class=HTMLResponse)
    async def partial_search_results(
        request: Request, q: str = "", sources: str | None = None, limit: int = 10
    ) -> HTMLResponse:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
        outcome = (
            await search_all(q, limit_per_source=limit, sources=source_list)
            if q.strip()
            else {"results": [], "errors": {}, "cache_hits": []}
        )
        return templates.TemplateResponse(
            request,
            "partials/search_results.html",
            {"query": q, **outcome},
        )

    @app.get("/search", response_class=HTMLResponse)
    def search_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "search.html", {"sources": available_connectors()}
        )

    @app.get("/api/chat/providers")
    def api_chat_providers() -> dict[str, Any]:
        return {"providers": available_providers()}

    @app.get("/api/chat/history")
    def api_chat_history() -> dict[str, Any]:
        return {"messages": [m.as_dict() for m in get_conversation_history()]}

    @app.post("/api/chat/reset")
    def api_chat_reset() -> dict[str, Any]:
        reset_conversation()
        return {"ok": True}

    @app.post("/api/chat")
    async def api_chat(body: ChatRequest) -> dict[str, Any]:
        if not body.message.strip():
            raise HTTPException(status_code=400, detail="Message vide.")
        try:
            return await ai_converse(
                body.message.strip(), provider=body.provider, model=body.model, reset=body.reset
            )
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/chat", response_class=HTMLResponse)
    def chat_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "chat.html", {"providers": available_providers()}
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "dashboard.html", {})

    @app.get("/terminal", response_class=HTMLResponse)
    def terminal_page(request: Request) -> HTMLResponse:
        level = permissions.web_level()
        exec_catalog = [
            {
                "name": spec.name,
                "permission": spec.permission.name,
                "destructive": spec.destructive,
                "description": spec.description,
                "allowed": spec.permission <= level,
            }
            for spec in permissions.available_commands()
        ]
        return templates.TemplateResponse(
            request,
            "terminal.html",
            {
                "allowed_commands": sorted(ALLOWED_WEB_COMMANDS),
                "exec_level": level.name,
                "exec_catalog": exec_catalog,
            },
        )

    logger.info("Application FastAPI S1M0NE initialisée (Phase 2).")
    return app


app = create_app()
