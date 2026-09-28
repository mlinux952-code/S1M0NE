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
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ai.base import ProviderError
from ai.gateway import available_providers
from ai.gateway import converse as ai_converse
from ai.gateway import get_conversation_history, reset_conversation
from connectors.engine import (
    DEFAULT_PAGE_SIZE,
    SORT_OPTIONS,
    available_connectors,
    paginate_results,
    search_all,
    sort_results,
)
from core import auth, memory, notifications, permissions, projects, scheduler
from core.config import DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH, settings
from core.db import init_db
from core.logging_setup import get_logger
from core.shell_runner import run_command as run_shell_command
from core.stats import usage_stats
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
templates.env.globals["auth_enabled"] = lambda: settings.web_auth_enabled

# Liste blanche stricte : seules ces commandes en LECTURE SEULE sont exposées via le web.
# Aucune commande système, aucune écriture, aucune exécution arbitraire (§15/§31 du mega-prompt).
ALLOWED_WEB_COMMANDS = {"status", "system", "version"}

# Cookie anonyme (Catégorie D §D.3) identifiant "cet appareil/navigateur" pour le niveau mémoire
# "session" — totalement indépendant du cookie d'authentification (core/auth.py, A.1) : ce
# cookie-ci ne porte aucun privilège, c'est un simple identifiant de scoping (même esprit que
# project_id pour le niveau "project"), présent même quand l'authentification web est désactivée.
BROWSER_SESSION_COOKIE = "s1mone_browser_session"
BROWSER_SESSION_MAX_AGE = 365 * 24 * 3600  # 1 an : une "session" survit à la fermeture du tab


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
    project_id: str | None = None  # NEXT_STEPS §B.4 : conversation scopée à un projet précis
    agent: bool = False  # NEXT_STEPS §B.2 : mode agentique (opt-in explicite, jamais par défaut)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie du processus 's1mone web' : un seul processus permanent qui héberge à la
    fois le serveur HTTP ET le worker de tâches en tâche de fond (mega-prompt : pas de service
    supplémentaire, low-resource first). Le worker s'arrête proprement à l'extinction."""
    init_db()
    if settings.web_auth_enabled:
        logger.info("Authentification web activée (S1MONE_WEB_PASSWORD défini dans .env).")
    else:
        logger.warning(
            "Authentification web DÉSACTIVÉE : l'interface est accessible sans mot de passe à "
            "quiconque atteint ce serveur (0.0.0.0). Définis S1MONE_WEB_PASSWORD dans .env pour "
            "l'activer — voir NEXT_STEPS.md §A.1."
        )
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

    @app.middleware("http")
    async def _require_auth(request: Request, call_next):
        """Authentification web optionnelle (NEXT_STEPS.md §A.1). Désactivée par défaut (aucun
        S1MONE_WEB_PASSWORD dans .env) : comportement historique, zéro régression. Activée : une
        requête HTML sans cookie valide est redirigée vers /login, une requête API reçoit un 401
        JSON plutôt qu'une redirection (inutile pour un client programmatique)."""
        if not settings.web_auth_enabled or auth.is_path_exempt(request.url.path):
            return await call_next(request)
        cookie = request.cookies.get(auth.COOKIE_NAME)
        if auth.verify_session_cookie(cookie, settings.web_password):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Authentification requise."}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request, error: str | None = None) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", {"error": error})

    @app.post("/login")
    def login_submit(password: str = Form(...)) -> Any:
        if not settings.web_auth_enabled or auth.check_password(password):
            response = RedirectResponse(url="/", status_code=303)
            if settings.web_auth_enabled:
                response.set_cookie(
                    auth.COOKIE_NAME,
                    auth.create_session_cookie(settings.web_password),
                    httponly=True,
                    samesite="lax",
                    max_age=auth.SESSION_LIFETIME_SECONDS,
                )
            return response
        return RedirectResponse(url="/login?error=1", status_code=303)

    @app.get("/logout")
    def logout() -> Any:
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(auth.COOKIE_NAME)
        return response

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

    @app.get("/plugins", response_class=HTMLResponse)
    def plugins_page(request: Request) -> HTMLResponse:
        """Page dédiée aux plugins (Catégorie E) : jusqu'ici uniquement inspectable en CLI
        ('s1mone plugin list', Phase 8) ou via /api/plugins brut. Même transparence côté web."""
        return templates.TemplateResponse(request, "plugins.html", {})

    @app.get("/partials/plugins", response_class=HTMLResponse)
    def partial_plugins(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "partials/plugins.html",
            {
                "plugins": list_plugins(),
                "plugins_dir": str(settings.plugins_dir),
                "connectors": [c["name"] for c in available_connectors()],
                "task_types": available_types(),
            },
        )

    @app.get("/api/settings")
    def api_settings() -> dict[str, Any]:
        """Configuration effective de S1M0NE (Catégorie E), secrets masqués — voir
        Settings.as_safe_dict() (core/config.py), jamais exposé nulle part avant."""
        return settings.as_safe_dict()

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> HTMLResponse:
        """Page dédiée aux paramètres (Catégorie E) : lecture seule, volontairement — modifier
        config.toml/.env reste un acte manuel et explicite (mega-prompt : rien de magique, aucun
        réglage de sécurité changé sans que l'utilisateur ait ouvert le fichier lui-même)."""
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "config": settings.as_safe_dict(),
                "config_path": str(DEFAULT_CONFIG_PATH),
                "env_path": str(DEFAULT_ENV_PATH),
            },
        )

    @app.get("/partials/notes-search", response_class=HTMLResponse)
    def partial_notes_search(request: Request, q: str = "") -> HTMLResponse:
        """Recherche plein texte de notes personnelles (Catégorie F, mini second brain) — lecture
        seule côté web : indexer un nouveau fichier reste réservé à la CLI ('s1mone notes
        index <chemin>'), un chemin de fichier arbitraire n'a pas sa place dans un formulaire
        web (même logique que 'pas de memory remember en CLI', D.3 : chaque façade n'expose que
        ce qui a du sens pour elle)."""
        from core.notes import NotesUnavailableError, notes_stats, search_notes

        available = notes_stats()["available"]
        results: list[dict[str, Any]] = []
        error: str | None = None
        if available and q.strip():
            try:
                results = search_notes(q, limit=30)
            except NotesUnavailableError as exc:
                error = str(exc)
        return templates.TemplateResponse(
            request,
            "partials/notes_search.html",
            {"query": q, "results": results, "available": available, "error": error},
        )

    @app.get("/discover", response_class=HTMLResponse)
    def discover_page(request: Request) -> HTMLResponse:
        """Catalogue statique de découverte (Catégorie G) : 100 projets réels et notables
        (npm/PyPI/GitHub/GitLab/Codeberg/HuggingFace/SourceForge), compilés une fois par
        recherche web et embarqués avec S1M0NE — consultable hors-ligne, sans jamais interroger
        les vraies API (contrairement à /search, Phase 5, qui lui fait de la recherche en
        direct)."""
        from core.discover import available_sites, catalog_metadata

        return templates.TemplateResponse(
            request,
            "discover.html",
            {"sites": available_sites(), "meta": catalog_metadata()},
        )

    @app.get("/partials/discover", response_class=HTMLResponse)
    def partial_discover(request: Request, q: str = "", site: str = "") -> HTMLResponse:
        from core.discover import list_entries, search_catalog

        if q.strip():
            results = search_catalog(q, limit=100)
        else:
            results = list_entries(site=site or None)
        return templates.TemplateResponse(
            request, "partials/discover_results.html", {"results": results, "query": q}
        )

    @app.post("/api/discover/install", response_class=HTMLResponse)
    def api_discover_install(
        request: Request,
        site: str = Form(...),
        name: str = Form(...),
        url: str = Form(""),
        confirmed: bool = Form(False),
    ) -> HTMLResponse:
        """Installe RÉELLEMENT une app (npm/pip/git), confinée sous fs_root/installed_apps/ —
        voir core/app_install.py pour toutes les garanties de sécurité. `confirmed` doit être
        explicitement transmis (case à cocher côté formulaire, en plus du hx-confirm côté
        navigateur) — deux niveaux de confirmation pour une action qui exécute du code tiers."""
        from core.app_install import (
            InstallConfirmationRequiredError,
            InvalidNameError,
            InvalidUrlError,
            UnsupportedSiteError,
            install_app,
        )

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            result = install_app(site, name, url or None, confirmed=confirmed)
        except (UnsupportedSiteError, InvalidNameError, InvalidUrlError) as exc:
            error = str(exc)
        except InstallConfirmationRequiredError as exc:
            error = str(exc)

        return templates.TemplateResponse(
            request,
            "partials/install_result.html",
            {"site": site, "name": name, "error": error, "result": result},
        )

    @app.get("/partials/installed-apps", response_class=HTMLResponse)
    def partial_installed_apps(request: Request) -> HTMLResponse:
        from core.app_install import list_installed
        from core.app_run import RUNNERS

        return templates.TemplateResponse(
            request, "partials/installed_apps.html", {"entries": list_installed(), "runners": RUNNERS}
        )

    @app.get("/partials/run-history", response_class=HTMLResponse)
    def partial_run_history(request: Request) -> HTMLResponse:
        """Historique PERSISTANT des exécutions (contrairement au résultat "live" affiché juste
        après avoir cliqué "Lancer", qui disparaît si la page est rechargée) — voir DECISIONS.md
        §D24 (correctif "je ne vois rien")."""
        from core.app_run import list_runs

        return templates.TemplateResponse(
            request, "partials/run_history.html", {"entries": list_runs()}
        )

    @app.post("/api/discover/run", response_class=HTMLResponse)
    def api_discover_run(
        request: Request,
        site: str = Form(...),
        name: str = Form(...),
        runner: str = Form(...),
        entry: str = Form(...),
        args: str = Form(""),
        network: bool = Form(False),
        confirmed: bool = Form(False),
    ) -> HTMLResponse:
        """Exécute RÉELLEMENT un fichier d'une app déjà installée, sandboxée par Firejail — voir
        core/app_run.py pour toutes les garanties de sécurité. `confirmed` doit être explicitement
        transmis (case cachée, en plus du hx-confirm côté navigateur)."""
        import shlex

        from core.app_install import InvalidNameError
        from core.app_run import (
            InvalidEntryError,
            NotInstalledError,
            RunConfirmationRequiredError,
            SandboxUnavailableError,
            UnknownRunnerError,
            run_app,
        )

        error: str | None = None
        result: dict[str, Any] | None = None
        try:
            extra_args = shlex.split(args) if args.strip() else []
            result = run_app(
                site, name, runner, entry, extra_args, network=network, confirmed=confirmed
            )
        except (
            InvalidNameError,
            NotInstalledError,
            UnknownRunnerError,
            InvalidEntryError,
            SandboxUnavailableError,
            RunConfirmationRequiredError,
        ) as exc:
            error = str(exc)
        except ValueError as exc:  # arguments mal quotés (shlex.split)
            error = f"Arguments invalides : {exc}"

        response = templates.TemplateResponse(
            request,
            "partials/run_result.html",
            {"site": site, "name": name, "error": error, "result": result},
        )
        if result is not None:
            # Signale à la section "Historique des exécutions" de se rafraîchir (htmx
            # hx-trigger="runCompleted from:body") — le résultat "live" ci-dessus disparaît si la
            # page est rechargée, l'historique lui persiste réellement (core.memory).
            response.headers["HX-Trigger"] = "runCompleted"
        return response

    @app.get("/api/notifications")
    def api_notifications_list(unread_only: bool = False, limit: int = 50) -> dict[str, Any]:
        return {
            "notifications": notifications.list_notifications(unread_only=unread_only, limit=limit),
            "unread_count": notifications.count_unread(),
        }

    @app.post("/api/notifications/{notification_id}/read")
    def api_notifications_read(notification_id: str) -> dict[str, Any]:
        ok = notifications.mark_read(notification_id)
        if not ok:
            raise HTTPException(
                status_code=404, detail=f"Notification introuvable : {notification_id}"
            )
        return {"ok": True}

    @app.post("/api/notifications/read-all")
    def api_notifications_read_all() -> dict[str, Any]:
        return {"ok": True, "count": notifications.mark_all_read()}

    def _notifications_context() -> dict[str, Any]:
        items = notifications.list_notifications(limit=10)
        for n in items:
            n["created_display"] = format_timestamp(n.get("created_at"))
        return {"notifications": items, "unread_count": notifications.count_unread()}

    @app.get("/partials/notifications", response_class=HTMLResponse)
    def partial_notifications(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "partials/notifications.html", _notifications_context()
        )

    @app.post("/partials/notifications/read-all", response_class=HTMLResponse)
    def partial_notifications_read_all(request: Request) -> HTMLResponse:
        notifications.mark_all_read()
        return templates.TemplateResponse(
            request, "partials/notifications.html", _notifications_context()
        )

    @app.post("/partials/notifications/{notification_id}/read", response_class=HTMLResponse)
    def partial_notifications_read(request: Request, notification_id: str) -> HTMLResponse:
        notifications.mark_read(notification_id)
        return templates.TemplateResponse(
            request, "partials/notifications.html", _notifications_context()
        )

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
    async def api_search(
        q: str = "",
        sources: str | None = None,
        limit: int = 10,
        sort: str = "relevance",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
        outcome = await search_all(q, limit_per_source=limit, sources=source_list)
        try:
            ordered = sort_results(outcome["results"], sort_by=sort)
            page_info = paginate_results(ordered, page=page, page_size=page_size)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "results": page_info["items"],
            "errors": outcome["errors"],
            "cache_hits": outcome["cache_hits"],
            "page": page_info["page"],
            "page_size": page_info["page_size"],
            "total": page_info["total"],
            "total_pages": page_info["total_pages"],
        }

    @app.get("/api/search/sources")
    def api_search_sources() -> dict[str, Any]:
        return {"sources": available_connectors()}

    @app.get("/partials/search-results", response_class=HTMLResponse)
    async def partial_search_results(
        request: Request,
        q: str = "",
        sources: str | None = None,
        limit: int = 10,
        sort: str = "relevance",
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> HTMLResponse:
        source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
        outcome = (
            await search_all(q, limit_per_source=limit, sources=source_list)
            if q.strip()
            else {"results": [], "errors": {}, "cache_hits": []}
        )
        sort_error: str | None = None
        try:
            ordered = sort_results(outcome["results"], sort_by=sort)
            page_info = paginate_results(ordered, page=page, page_size=page_size)
        except ValueError as exc:
            sort_error = str(exc)
            page_info = {"items": [], "page": 1, "page_size": page_size, "total": 0, "total_pages": 1}

        # Les liens Précédent/Suivant (htmx hx-vals) rejouent exactement les mêmes filtres, pour
        # ne jamais perdre la recherche/le tri en changeant de page.
        base_vals = {"q": q, "sources": sources or "", "limit": limit, "sort": sort, "page_size": page_size}
        prev_vals = json.dumps({**base_vals, "page": max(1, page_info["page"] - 1)}, ensure_ascii=False)
        next_vals = json.dumps({**base_vals, "page": page_info["page"] + 1}, ensure_ascii=False)

        return templates.TemplateResponse(
            request,
            "partials/search_results.html",
            {
                "query": q,
                "errors": outcome["errors"],
                "cache_hits": outcome["cache_hits"],
                "results": page_info["items"],
                "page": page_info["page"],
                "total_pages": page_info["total_pages"],
                "total": page_info["total"],
                "sort_by": sort,
                "sort_error": sort_error,
                "prev_vals": prev_vals,
                "next_vals": next_vals,
                "sort_options": SORT_OPTIONS,
            },
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
    def api_chat_history(project_id: str | None = None) -> dict[str, Any]:
        return {"messages": [m.as_dict() for m in get_conversation_history(project_id=project_id)]}

    @app.post("/api/chat/reset")
    def api_chat_reset(project_id: str | None = None) -> dict[str, Any]:
        reset_conversation(project_id=project_id)
        return {"ok": True}

    @app.post("/api/chat")
    async def api_chat(body: ChatRequest) -> dict[str, Any]:
        if not body.message.strip():
            raise HTTPException(status_code=400, detail="Message vide.")
        try:
            return await ai_converse(
                body.message.strip(),
                provider=body.provider,
                model=body.model,
                reset=body.reset,
                project_id=body.project_id,
                agent=body.agent,
            )
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:  # projet inconnu
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects")
    def api_projects_list() -> dict[str, Any]:
        return {"projects": projects.list_projects()}

    @app.get("/api/schedules")
    def api_schedules_list() -> dict[str, Any]:
        return {"schedules": scheduler.list_schedules()}

    @app.get("/api/stats")
    def api_stats() -> dict[str, Any]:
        """Instantané d'usage (tâches, mémoire, cache, projets, notifications, planifications) —
        lecture seule, aucune donnée sensible (voir core/stats.py)."""
        return usage_stats()

    @app.get("/partials/stats", response_class=HTMLResponse)
    def partial_stats(request: Request) -> HTMLResponse:
        stats = usage_stats()
        return templates.TemplateResponse(
            request,
            "partials/stats.html",
            {"stats": stats, "generated_display": format_timestamp(stats["generated_at"])},
        )

    @app.get("/stats", response_class=HTMLResponse)
    def stats_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "stats.html", {})

    @app.get("/memory", response_class=HTMLResponse)
    def memory_page(request: Request) -> HTMLResponse:
        """Page dédiée à la mémoire (NEXT_STEPS §C.1) : jusqu'ici uniquement inspectable en CLI
        ('s1mone memory list/show/forget', Phase 7). Transparence identique côté web : tout ce
        que S1M0NE retient reste consultable et supprimable ici, rien n'est caché.

        Garantit aussi l'existence du cookie de session anonyme (D.3) avant que les partials
        htmx (déclenchés au chargement de la page) n'en aient besoin."""
        session_id = request.cookies.get(BROWSER_SESSION_COOKIE) or secrets.token_urlsafe(16)
        response = templates.TemplateResponse(
            request,
            "memory.html",
            {
                "levels": memory.VALID_LEVELS,
                "projects_list": projects.list_projects(),
                "session_id": session_id,
            },
        )
        response.set_cookie(
            BROWSER_SESSION_COOKIE,
            session_id,
            max_age=BROWSER_SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response

    def _session_notes_response(request: Request, session_id: str) -> HTMLResponse:
        entries = memory.list_memory(level="session", session_id=session_id)
        for e in entries:
            e["created_display"] = format_timestamp(e.get("created_at"))
        response = templates.TemplateResponse(
            request,
            "partials/session_notes.html",
            {"entries": entries, "session_id": session_id},
        )
        response.set_cookie(
            BROWSER_SESSION_COOKIE,
            session_id,
            max_age=BROWSER_SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.get("/partials/session-notes", response_class=HTMLResponse)
    def partial_session_notes(request: Request) -> HTMLResponse:
        """Notes de session (Catégorie D §D.3) : premier vrai consommateur du niveau mémoire
        'session' (réservé depuis la Phase 7). Scopées par un cookie anonyme propre à ce
        navigateur — jamais partagées avec un autre appareil, ni avec la mémoire
        persistante/projet."""
        session_id = request.cookies.get(BROWSER_SESSION_COOKIE) or secrets.token_urlsafe(16)
        return _session_notes_response(request, session_id)

    @app.post("/partials/session-notes", response_class=HTMLResponse)
    def partial_session_notes_save(
        request: Request, key: str = Form(...), value: str = Form(...)
    ) -> HTMLResponse:
        session_id = request.cookies.get(BROWSER_SESSION_COOKIE) or secrets.token_urlsafe(16)
        if key.strip():
            memory.remember("session", key.strip(), value, session_id=session_id)
        return _session_notes_response(request, session_id)

    @app.post("/partials/session-notes/forget", response_class=HTMLResponse)
    def partial_session_notes_forget(request: Request, key: str = Form(...)) -> HTMLResponse:
        session_id = request.cookies.get(BROWSER_SESSION_COOKIE)
        if session_id:
            memory.forget("session", key, session_id=session_id)
        return _session_notes_response(request, session_id or secrets.token_urlsafe(16))

    @app.get("/partials/memory-list", response_class=HTMLResponse)
    def partial_memory_list(
        request: Request, level: str = "", project_id: str = "", q: str = ""
    ) -> HTMLResponse:
        lvl = level or None
        pid = project_id or None
        query = q or None
        error: str | None = None
        try:
            entries = memory.list_memory(lvl, project_id=pid, query=query)
        except ValueError as exc:
            entries = []
            error = str(exc)
        for e in entries:
            e["created_display"] = format_timestamp(e.get("created_at"))
        return templates.TemplateResponse(
            request, "partials/memory_list.html", {"entries": entries, "error": error, "query": query}
        )

    @app.get("/partials/memory-value", response_class=HTMLResponse)
    def partial_memory_value(
        request: Request, level: str = "", key: str = "", project_id: str = "", session_id: str = ""
    ) -> HTMLResponse:
        pid = project_id or None
        sid = session_id or None
        try:
            value = memory.recall(level, key, project_id=pid, session_id=sid)
        except ValueError as exc:
            return templates.TemplateResponse(
                request, "partials/memory_value.html", {"error": str(exc)}
            )
        value_json = json.dumps(value, ensure_ascii=False, indent=2)
        return templates.TemplateResponse(
            request,
            "partials/memory_value.html",
            {"level": level, "key": key, "value_json": value_json},
        )

    @app.post("/partials/memory/forget", response_class=HTMLResponse)
    def partial_memory_forget(
        request: Request,
        level: str = Form(...),
        key: str = Form(...),
        project_id: str = Form(""),
        session_id: str = Form(""),
    ) -> HTMLResponse:
        """Supprime une entrée puis recharge la liste COMPLÈTE (sans filtre) — simplification
        assumée (NEXT_STEPS §C.1) : préserver le filtre exact affiché avant suppression aurait
        exigé de le retransmettre depuis le bouton, pour un gain marginal sur une action rare."""
        pid = project_id or None
        sid = session_id or None
        error: str | None = None
        try:
            memory.forget(level, key, project_id=pid, session_id=sid)
        except ValueError as exc:
            error = str(exc)
        entries = memory.list_memory() if error is None else []
        for e in entries:
            e["created_display"] = format_timestamp(e.get("created_at"))
        return templates.TemplateResponse(
            request, "partials/memory_list.html", {"entries": entries, "error": error}
        )

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
