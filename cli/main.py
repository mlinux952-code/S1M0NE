"""
cli/main.py — Terminal Gateway de S1M0NE (Phase 1 : commandes minimales).

Commandes disponibles :
    s1mone status   -> diagnostic complet (config, sqlite, disque, ressources)
    s1mone stats    -> instantané d'usage (tâches, mémoire, cache, projets, notifications ...)
    s1mone system   -> aperçu CPU/RAM/swap/disque en direct
    s1mone version  -> version + infos plateforme
    s1mone config show  -> configuration effective (config.toml + .env), secrets masqués (Cat. E)
    s1mone cache list/clear -> détail et nettoyage manuel du cache de recherche (Cat. E)
    s1mone notes index/search  -> mini second brain : recherche plein texte de tes notes (Cat. F)
    (Cat. F : nouveaux types de tâche planifiables 'url_check' et 'rss_check', voir
     's1mone schedule create --help')
    s1mone discover list/search/sites -> catalogue statique de 100 projets notables sur les 7
    sites connectés (npm/PyPI/GitHub/GitLab/Codeberg/HuggingFace/SourceForge), embarqué avec
    S1M0NE, consultable hors-ligne, sans mise à jour automatique (Cat. G)
    s1mone discover install/installed -> installation RÉELLE (npm/pip/git), confinée sous
    fs_root/installed_apps/, jamais globale sur la machine — confirmation obligatoire (Cat. G+)
    s1mone discover run/runs -> exécution RÉELLE d'une app déjà installée, sandboxée par
    Firejail (namespaces + seccomp + limites RAM/CPU + réseau coupé par défaut) — jamais sans
    sandbox, confirmation obligatoire (Cat. G++)

Le terminal doit rester utilisable même sans l'interface web (mega-prompt §6) :
cette CLI ne dépend d'aucun serveur, elle appelle directement les modules core/system.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ai.base import ProviderError
from ai.gateway import available_providers
from ai.gateway import check_all_providers
from ai.gateway import converse as ai_converse
from ai.gateway import reset_conversation
import connectors.engine as search_engine
from connectors.engine import available_connectors, search_all
from core import memory as memory_module
from core import permissions
from core.cache import cache_clear_all, cache_cleanup, cache_delete, cache_list
from core.config import settings
from core.db import backup_db, list_backups
from core import notifications as notifications_module
from core import projects as projects_module
from core.shell_runner import run_command as run_shell_command
from core.timeutil import format_timestamp
from plugins.manager import list_plugins
from system.healthcheck import run_all_checks
from system.monitor import get_platform_info, get_snapshot, resource_level
from core import scheduler as scheduler_module
from tasks.manager import (
    cancel_task,
    get_task,
    list_tasks,
    run_due_schedules_safely,
    run_pending_tasks,
    submit_task,
    worker_loop,
)
from tasks.registry import available_types

app = typer.Typer(
    name="s1mone",
    help="S1M0NE — plateforme personnelle intelligente (maison numérique).",
    add_completion=True,
)
console = Console()

task_app = typer.Typer(help="Gestion des tâches (Task Manager).")
app.add_typer(task_app, name="task")

memory_app = typer.Typer(help="Inspection de la mémoire persistante (Phase 7).")
app.add_typer(memory_app, name="memory")

exec_app = typer.Typer(help="Commandes système réelles, en liste blanche (Phase 9 - Sécurité).")
app.add_typer(exec_app, name="exec")

plugin_app = typer.Typer(help="Plugins tiers (Phase 8) : connecteurs et types de tâches additionnels.")
app.add_typer(plugin_app, name="plugin")

backup_app = typer.Typer(help="Sauvegarde de la base SQLite (mémoire, tâches, cache).")
app.add_typer(backup_app, name="backup")

notify_app = typer.Typer(help="Notifications locales (fin de tâche, erreurs).")
app.add_typer(notify_app, name="notify")

project_app = typer.Typer(help="Projets (regroupent de la mémoire dédiée, ex. une conversation IA par projet).")
app.add_typer(project_app, name="project")

schedule_app = typer.Typer(help="Tâches récurrentes : répète un type de tâche toutes les N secondes/minutes/heures/jours.")
app.add_typer(schedule_app, name="schedule")

config_app = typer.Typer(help="Configuration effective de S1M0NE (Catégorie E), secrets masqués.")
app.add_typer(config_app, name="config")

cache_app = typer.Typer(help="Cache de recherche (Phase 4) : consultation et nettoyage manuel.")
app.add_typer(cache_app, name="cache")

notes_app = typer.Typer(help="Recherche plein texte de notes personnelles (Catégorie F, mini second brain).")
app.add_typer(notes_app, name="notes")

discover_app = typer.Typer(
    help="Catalogue statique de 100 projets réels notables (npm/PyPI/GitHub/GitLab/Codeberg/"
    "HuggingFace/SourceForge), embarqué avec S1M0NE — consultable hors-ligne (Catégorie G)."
)
app.add_typer(discover_app, name="discover")


_COMMANDS_NEEDING_DB = {
    "status",
    "stats",
    "task",
    "search",
    "chat",
    "memory",
    "backup",
    "notify",
    "project",
    "schedule",
    "cache",
    "notes",
}


@app.callback()
def _ensure_ready(ctx: typer.Context) -> None:
    """Exécuté avant chaque commande : garantit que la base SQLite existe déjà (idempotent),
    mais seulement pour les commandes qui en ont réellement besoin (status, task ...). On évite
    ainsi de créer la base et de polluer la sortie de logs pour un simple --help/version/system."""
    if ctx.invoked_subcommand in _COMMANDS_NEEDING_DB:
        from core.db import init_db

        init_db()

_LEVEL_COLORS = {"NORMAL": "green", "WARNING": "yellow", "CRITICAL": "bold red"}
_STATUS_COLORS = {
    "QUEUED": "cyan",
    "RUNNING": "yellow",
    "SUCCESS": "green",
    "FAILED": "bold red",
    "CANCELLED": "grey58",
}


_fmt_ts = format_timestamp  # alias local, logique partagée avec le web (core/timeutil.py)


def _resolve_project_or_exit(identifier: str) -> str:
    """Résout un identifiant de projet (id ou nom) en id réel, ou quitte proprement sinon."""
    project = projects_module.resolve_project(identifier)
    if project is None:
        console.print(f"[red]Projet inconnu : '{identifier}' (voir 's1mone project list').[/red]")
        raise typer.Exit(code=1)
    return project["id"]


@app.command()
def status() -> None:
    """Diagnostic complet : configuration, base de données, disque, ressources."""
    report = run_all_checks()

    table = Table(title="S1M0NE — status", show_lines=False)
    table.add_column("Vérification")
    table.add_column("État")
    table.add_column("Détail")

    for check in report["checks"]:
        state = "[green]OK[/green]" if check["ok"] else "[bold red]KO[/bold red]"
        detail = check["detail"] or check.get("reason") or ""
        table.add_row(check["name"], state, str(detail))

    console.print(table)

    level = report["resource_level"]
    color = _LEVEL_COLORS.get(level, "cyan")
    console.print(f"\nNiveau de ressources : [{color}]{level}[/{color}]")

    overall = "[green]S1M0NE est opérationnelle.[/green]" if report["overall_ok"] else (
        "[bold red]S1M0NE a détecté un problème — voir le tableau ci-dessus.[/bold red]"
    )
    console.print(overall)

    if not report["overall_ok"]:
        raise typer.Exit(code=1)


@app.command()
def stats() -> None:
    """Instantané d'usage : tâches, mémoire, cache de recherche, projets, notifications,
    tâches récurrentes (compteurs uniquement, lecture seule — voir core/stats.py).

    Différent de 's1mone status' (diagnostic de bonne santé) : ici, ce sont des compteurs
    d'usage, pas un contrôle de configuration/ressources."""
    from core.stats import usage_stats

    data = usage_stats()

    tasks = Table(title="Tâches")
    tasks.add_column("Statut")
    tasks.add_column("Nombre", justify="right")
    for status_name, n in data["tasks"]["by_status"].items():
        tasks.add_row(status_name, str(n))
    tasks.add_row("[bold]Total[/bold]", f"[bold]{data['tasks']['total']}[/bold]")
    rate = data["tasks"]["success_rate_percent"]
    tasks.add_row("Taux de succès", f"{rate} %" if rate is not None else "—")
    console.print(tasks)

    memory_table = Table(title="Mémoire")
    memory_table.add_column("Niveau")
    memory_table.add_column("Nombre", justify="right")
    for level, n in data["memory"]["by_level"].items():
        memory_table.add_row(level, str(n))
    memory_table.add_row("[bold]Total[/bold]", f"[bold]{data['memory']['total']}[/bold]")
    console.print(memory_table)

    other = Table(title="Cache, projets, notifications, tâches récurrentes")
    other.add_column("Indicateur")
    other.add_column("Valeur", justify="right")
    other.add_row("Cache — total / valides / expirées",
                  f"{data['cache']['total']} / {data['cache']['valid']} / {data['cache']['expired']}")
    other.add_row("Projets", str(data["projects"]["total"]))
    other.add_row("Notifications — total / non lues",
                  f"{data['notifications']['total']} / {data['notifications']['unread']}")
    other.add_row("Tâches récurrentes — total / actives",
                  f"{data['schedules']['total']} / {data['schedules']['enabled']}")
    console.print(other)

    console.print(f"[dim]Généré à : {_fmt_ts(data['generated_at'])}[/dim]")


@app.command()
def system() -> None:
    """Aperçu en direct CPU / RAM / swap / disque, sans rien modifier sur la machine."""
    snap = get_snapshot()
    info = get_platform_info()
    level = resource_level(snap)
    color = _LEVEL_COLORS.get(level, "cyan")

    table = Table(title=f"S1M0NE — system  (niveau : [{color}]{level}[/{color}])")
    table.add_column("Métrique")
    table.add_column("Valeur")

    table.add_row("OS", f"{info['system']} {info['release']}")
    table.add_row("Python", info["python_version"])
    table.add_row("CPU cœurs (physiques/logiques)",
                  f"{snap.cpu_count_physical} / {snap.cpu_count_logical}")
    table.add_row("CPU utilisation", f"{snap.cpu_percent} %")
    table.add_row("RAM", f"{snap.ram_available_gb} Gio libres / {snap.ram_total_gb} Gio "
                          f"({snap.ram_percent_used} % utilisés)")
    table.add_row("Swap", f"{snap.swap_used_gb} / {snap.swap_total_gb} Gio "
                           f"({snap.swap_percent_used} % utilisés)")
    table.add_row("Disque (DATA_DIR)", f"{snap.disk_free_gb} Gio libres / {snap.disk_total_gb} Gio "
                                        f"({snap.disk_percent_used} % utilisés)")
    table.add_row("DATA_DIR", str(settings.data_dir))

    console.print(table)


@app.command()
def web(
    host: str = typer.Option("0.0.0.0", help="Adresse d'écoute du serveur web."),
    port: int = typer.Option(8420, help="Port d'écoute du serveur web."),
    reload: bool = typer.Option(False, help="Rechargement auto (développement uniquement)."),
) -> None:
    """Démarre l'interface web S1M0NE (dashboard + terminal web)."""
    import uvicorn

    console.print(f"[green]Démarrage de l'interface web sur http://{host}:{port}[/green]")
    console.print("Arrête avec CTRL+C.")
    uvicorn.run("web.app:app", host=host, port=port, reload=reload)


@app.command()
def version() -> None:
    """Affiche la version de S1M0NE et les infos de plateforme."""
    info = get_platform_info()
    console.print("[bold]S1M0NE[/bold] — v0.1.0 (Phase 1 : Fondation)")
    console.print(f"Python {info['python_version']} sur {info['system']} {info['release']}")


@app.command()
def search(
    query: Optional[str] = typer.Argument(
        None, help="Terme à rechercher (facultatif avec --list-sources)."
    ),
    sources: Optional[str] = typer.Option(
        None,
        "--sources",
        help="Sources séparées par des virgules (ex: npm,github). Par défaut : toutes.",
    ),
    limit: int = typer.Option(10, help="Nombre maximum de résultats par source."),
    sort: str = typer.Option(
        "relevance",
        "--sort",
        help=f"Tri des résultats agrégés (NEXT_STEPS §C.2). Options : {', '.join(search_engine.SORT_OPTIONS)}.",
    ),
    page: int = typer.Option(1, "--page", help="Numéro de page (résultats déjà triés)."),
    page_size: int = typer.Option(
        search_engine.DEFAULT_PAGE_SIZE, "--page-size", help="Résultats affichés par page."
    ),
    list_sources: bool = typer.Option(
        False, "--list-sources", help="Affiche juste la liste des sources disponibles et quitte."
    ),
) -> None:
    """Recherche dans les connecteurs (Phase 5) : npm, Hugging Face, GitHub, GitLab, Codeberg,
    PyPI et SourceForge (ces deux derniers en mode dégradé : nom exact uniquement)."""
    if list_sources:
        table = Table(title="S1M0NE — sources de recherche disponibles")
        table.add_column("Source")
        table.add_column("Description")
        for c in available_connectors():
            table.add_row(c["name"], c["description"])
        console.print(table)
        return

    if not query or not query.strip():
        console.print("[red]Terme de recherche manquant.[/red] Exemple : s1mone search react")
        console.print("(ou 's1mone search --list-sources' pour voir les sources disponibles)")
        raise typer.Exit(code=1)

    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else None
    outcome = asyncio.run(search_all(query, limit_per_source=limit, sources=source_list))

    try:
        sorted_results = search_engine.sort_results(outcome["results"], sort_by=sort)
        page_info = search_engine.paginate_results(sorted_results, page=page, page_size=page_size)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    results = page_info["items"]
    errors = outcome["errors"]
    cache_hits = outcome["cache_hits"]

    # overflow="ellipsis" + no_wrap=True : une seule ligne par résultat, tronquée proprement avec
    # "…", au lieu de tableaux qui explosent sur 4-5 lignes par résultat (retour utilisateur :
    # "tableau trop large / difficile à lire" — voir PROJECT_STATE.md).
    table = Table(
        title=f"S1M0NE — recherche : \"{query}\" (tri : {sort}, page {page_info['page']}/{page_info['total_pages']})"
    )
    table.add_column("Source", max_width=12, no_wrap=True)
    table.add_column("Nom", max_width=28, overflow="ellipsis", no_wrap=True)
    table.add_column("Description", max_width=45, overflow="ellipsis", no_wrap=True)
    table.add_column("URL", max_width=35, overflow="ellipsis", no_wrap=True, style="grey58")

    for r in results:
        note = " *" if r.get("extra", {}).get("exact_match_only") else ""
        # Certaines sources renvoient des descriptions avec des retours à la ligne bruts (ex.
        # GitLab) : on les aplatit pour garantir une seule ligne par résultat dans le tableau.
        description = " ".join((r.get("description") or "").split())
        table.add_row(r["source"], r["name"] + note, description, r.get("url") or "")

    console.print(table)

    if page_info["total"] > page_info["page_size"]:
        console.print(
            f"[grey58]{page_info['total']} résultat(s) au total sur {page_info['total_pages']} "
            f"page(s) — voir la page suivante avec --page {page_info['page'] + 1}.[/grey58]"
        )

    if not results:
        console.print("[grey58]Aucun résultat.[/grey58]")
    elif any(r.get("extra", {}).get("exact_match_only") for r in results):
        console.print(
            "[grey58]* = résultat par nom exact uniquement (pas de recherche par mot-clé sur "
            "cette source)[/grey58]"
        )

    if cache_hits:
        console.print(f"[grey58]Servi depuis le cache : {', '.join(sorted(cache_hits))}[/grey58]")

    if errors:
        for src, msg in errors.items():
            console.print(f"[bold red]Erreur ({src}) :[/bold red] {msg}")


def _print_tool_trace(tool_calls: Optional[list]) -> None:
    """Affiche les outils réellement exécutés par le mode agentique (NEXT_STEPS §B.2) avant la
    réponse : transparence obligatoire (mega-prompt anti-hallucination) — l'utilisateur doit
    toujours voir quand l'IA a exécuté une vraie commande/recherche plutôt que juste répondu."""
    if not tool_calls:
        return
    for call in tool_calls:
        console.print(
            f"[grey58]🔧 outil : {call['name']}({call['arguments']})[/grey58]"
        )


@app.command()
def chat(
    message: Optional[str] = typer.Argument(
        None, help="Message à envoyer (facultatif : sans message, ouvre une conversation interactive)."
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", help="Fournisseur IA à utiliser (défaut : config.toml [ai] default_provider)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", help="Modèle à utiliser (défaut : celui du fournisseur choisi)."
    ),
    list_providers: bool = typer.Option(
        False, "--list-providers", help="Affiche les fournisseurs IA disponibles et leur statut."
    ),
    check: bool = typer.Option(
        False,
        "--check",
        help=(
            "Envoie un vrai message minimal à chaque fournisseur configuré pour vérifier qu'il "
            "répond (détecte un modèle retiré du catalogue AVANT un vrai usage). Consomme un peu "
            "de quota gratuit."
        ),
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Efface la conversation mémorisée avant d'envoyer ce message."
    ),
    no_memory: bool = typer.Option(
        False,
        "--no-memory",
        help="Appel ponctuel : ne lit ni n'écrit la conversation persistante (Phase 7).",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        help="Id ou nom de projet (NEXT_STEPS §B.4) : conversation séparée, propre à ce projet.",
    ),
    agent: bool = typer.Option(
        False,
        "--agent",
        help=(
            "Mode agentique (NEXT_STEPS §B.2) : l'assistant peut interroger search() et un "
            "run_command() STRICTEMENT en lecture seule (jamais d'écriture/suppression) avant "
            "de répondre. Jamais activé par défaut. Voir DECISIONS.md D18."
        ),
    ),
) -> None:
    """Discute avec un assistant IA (Phase 6), qui se souvient de la conversation d'une session à
    l'autre (Phase 7 - Mémoire). Gratuit par défaut (Groq), voir README.md pour changer de
    fournisseur (OpenRouter, Ollama en local)."""
    project_id = _resolve_project_or_exit(project) if project else None
    if list_providers:
        table = Table(title="S1M0NE — fournisseurs IA disponibles")
        table.add_column("Fournisseur")
        table.add_column("Statut")
        table.add_column("Modèle par défaut")
        table.add_column("Description", max_width=60)
        for p in available_providers():
            status = "[green]configuré[/green]" if p["configured"] else "[yellow]à configurer[/yellow]"
            table.add_row(str(p["name"]), status, str(p["default_model"]), str(p["description"]))
        console.print(table)
        for p in available_providers():
            if not p["configured"]:
                console.print(f"[grey58]{p['name']} : {p['setup_hint']}[/grey58]")
        return

    if check:
        console.print(
            "[grey58]Vérification en cours (un vrai message minimal par fournisseur "
            "configuré)...[/grey58]"
        )
        results = asyncio.run(check_all_providers())
        table = Table(title="S1M0NE — vérification des fournisseurs IA")
        table.add_column("Fournisseur")
        table.add_column("Statut")
        table.add_column("Modèle testé")
        table.add_column("Détail", max_width=60)
        any_configured = False
        for r in results:
            if not r["configured"]:
                table.add_row(str(r["provider"]), "[grey58]non configuré[/grey58]", "-", "")
                continue
            any_configured = True
            status = "[green]OK[/green]" if r["ok"] else "[bold red]ÉCHEC[/bold red]"
            table.add_row(str(r["provider"]), status, str(r["model"]), str(r["detail"]))
        console.print(table)
        if not any_configured:
            console.print(
                "[yellow]Aucun fournisseur configuré. Voir 's1mone chat --list-providers'.[/yellow]"
            )
        return

    if message and message.strip():
        try:
            outcome = asyncio.run(
                ai_converse(
                    message.strip(),
                    provider=provider,
                    model=model,
                    reset=reset,
                    use_memory=not no_memory,
                    project_id=project_id,
                    agent=agent,
                )
            )
        except ProviderError as exc:
            console.print(f"[bold red]Erreur IA :[/bold red] {exc}")
            raise typer.Exit(code=1) from exc
        console.print(f"[grey58]({outcome['provider']} / {outcome['model']})[/grey58]")
        _print_tool_trace(outcome.get("tool_calls"))
        console.print(outcome["reply"])
        return

    # Pas de message : conversation interactive. La mémoire (Phase 7) est persistée en base entre
    # deux lancements : fermer puis rouvrir "s1mone chat" reprend la conversation là où elle en
    # était, sauf --reset ou '/reset' en cours de session.
    scope_hint = f" (projet : {project})" if project else ""
    agent_hint = " [agentique : outils READ-only actifs]" if agent else ""
    console.print(
        f"[bold]S1M0NE — chat interactif{scope_hint}{agent_hint}[/bold] (mémoire persistante "
        "activée — tape 'exit' pour quitter, '/reset' pour repartir de zéro)"
    )
    if reset:
        reset_conversation(project_id=project_id)
        console.print("[grey58]Conversation précédente effacée.[/grey58]")
    while True:
        try:
            user_input = console.input("[bold cyan]toi >[/bold cyan] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[grey58]Fin de la conversation.[/grey58]")
            break
        text = user_input.strip()
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            console.print("[grey58]Fin de la conversation.[/grey58]")
            break
        if text.lower() == "/reset":
            reset_conversation(project_id=project_id)
            console.print("[grey58]Conversation effacée. On repart de zéro.[/grey58]")
            continue
        try:
            outcome = asyncio.run(
                ai_converse(
                    text,
                    provider=provider,
                    model=model,
                    use_memory=not no_memory,
                    project_id=project_id,
                    agent=agent,
                )
            )
        except ProviderError as exc:
            console.print(f"[bold red]Erreur IA :[/bold red] {exc}")
            continue
        _print_tool_trace(outcome.get("tool_calls"))
        console.print(f"[bold magenta]s1mone >[/bold magenta] {outcome['reply']}")


@task_app.command("submit")
def task_submit(
    task_type: str = typer.Argument(
        ..., help=f"Type de tâche. Disponibles : {', '.join(available_types())}"
    ),
    param: list[str] = typer.Option(
        [], "--param", help="Paramètre au format clé=valeur (répétable)."
    ),
) -> None:
    """Ajoute une tâche à la file d'attente (QUEUED). Ne l'exécute pas immédiatement."""
    parameters: dict[str, str] = {}
    for item in param:
        if "=" not in item:
            console.print(f"[red]Paramètre invalide (attendu clé=valeur) : {item}[/red]")
            raise typer.Exit(code=1)
        key, value = item.split("=", 1)
        parameters[key] = value

    try:
        task_id = submit_task(task_type, parameters)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Tâche créée :[/green] {task_id}  (type={task_type}, status=QUEUED)")
    console.print(
        "Elle sera exécutée par 's1mone task worker' ou automatiquement si 's1mone web' tourne."
    )


@task_app.command("list")
def task_list(
    status: Optional[str] = typer.Option(None, help="Filtrer par statut (QUEUED/RUNNING/...)."),
    limit: int = typer.Option(20, help="Nombre maximum de tâches affichées."),
) -> None:
    """Liste les tâches (les plus récentes d'abord)."""
    tasks = list_tasks(status=status, limit=limit)
    table = Table(title="S1M0NE — tâches")
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Statut")
    table.add_column("Créée à")
    table.add_column("Terminée à")

    for t in tasks:
        color = _STATUS_COLORS.get(t["status"], "white")
        table.add_row(
            t["id"],
            t["type"],
            f"[{color}]{t['status']}[/{color}]",
            _fmt_ts(t["created_at"]),
            _fmt_ts(t["finished_at"]),
        )
    console.print(table)
    if not tasks:
        console.print("[grey58]Aucune tâche pour ce filtre.[/grey58]")


@task_app.command("show")
def task_show(task_id: str) -> None:
    """Affiche le détail complet d'une tâche (paramètres, résultat, erreur)."""
    task = get_task(task_id)
    if not task:
        console.print(f"[red]Tâche introuvable : {task_id}[/red]")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(task))


@task_app.command("cancel")
def task_cancel(task_id: str) -> None:
    """Annule une tâche : immédiatement si QUEUED, vraie annulation asyncio si RUNNING."""
    ok = cancel_task(task_id)
    if ok:
        console.print(f"[yellow]Annulation effectuée pour {task_id}.[/yellow]")
    else:
        console.print(
            f"[red]Impossible d'annuler {task_id} (introuvable, déjà terminée, ou pas de worker actif).[/red]"
        )
        raise typer.Exit(code=1)


@task_app.command("worker")
def task_worker(
    once: bool = typer.Option(
        False, help="Traiter le lot de tâches en attente une seule fois, puis quitter."
    ),
    interval: float = typer.Option(2.0, help="Secondes entre deux passages (mode continu)."),
) -> None:
    """Démarre un worker de tâches en CLI (utile sans lancer l'interface web)."""
    if once:
        scheduled = run_due_schedules_safely()
        processed = asyncio.run(run_pending_tasks())
        if scheduled:
            console.print(f"{scheduled} tâche(s) créée(s) par une planification arrivée à échéance.")
        console.print(f"{processed} tâche(s) traitée(s).")
        return

    console.print("Worker de tâches démarré (CTRL+C pour arrêter)...")
    try:
        asyncio.run(worker_loop(interval_seconds=interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker arrêté.[/yellow]")


@memory_app.command("list")
def memory_list(
    level: Optional[str] = typer.Option(
        None,
        "--level",
        help=f"Filtrer par niveau ({', '.join(memory_module.VALID_LEVELS)}). Défaut : tous.",
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Filtrer sur un projet précis (id ou nom, niveau 'project')."
    ),
    session_id: Optional[str] = typer.Option(
        None,
        "--session-id",
        help="Filtrer sur une session précise (niveau 'session', ex. le cookie affiché sur /memory).",
    ),
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Recherche plein texte (Catégorie D) : sous-chaîne insensible à la casse dans la clé ou la valeur.",
    ),
) -> None:
    """Liste les entrées mémorisées (métadonnées uniquement — voir 'memory show' pour le contenu).

    Transparence (Phase 7) : tout ce que S1M0NE retient de toi (ex. l'historique de chat) reste
    inspectable et supprimable à tout moment, rien n'est caché."""
    project_id = _resolve_project_or_exit(project) if project else None
    try:
        entries = memory_module.list_memory(
            level, project_id=project_id, session_id=session_id, query=query
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    title = f"S1M0NE — mémoire (recherche : \"{query}\")" if query else "S1M0NE — mémoire"
    table = Table(title=title)
    table.add_column("Niveau")
    table.add_column("Clé")
    table.add_column("Projet")
    table.add_column("Session")
    table.add_column("Enregistrée à")
    for e in entries:
        table.add_row(
            e["level"],
            e["key"],
            e.get("project_id", "") or "",
            e.get("session_id", "") or "",
            _fmt_ts(e["created_at"]),
        )
    console.print(table)
    if not entries:
        console.print("[grey58]Aucune entrée pour ce filtre.[/grey58]")


@memory_app.command("show")
def memory_show(
    level: str = typer.Argument(..., help=f"Niveau ({', '.join(memory_module.VALID_LEVELS)})."),
    key: str = typer.Argument(..., help="Clé (voir 's1mone memory list')."),
    project: Optional[str] = typer.Option(
        None, "--project", help="Id ou nom de projet (requis si level='project')."
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session-id", help="Id de session (requis si level='session')."
    ),
) -> None:
    """Affiche le contenu complet d'une entrée mémorisée."""
    project_id = _resolve_project_or_exit(project) if project else None
    try:
        value = memory_module.recall(level, key, project_id=project_id, session_id=session_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if value is None:
        console.print(f"[red]Aucune entrée pour {level}/{key}.[/red]")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(value, ensure_ascii=False))


@memory_app.command("forget")
def memory_forget(
    level: str = typer.Argument(..., help=f"Niveau ({', '.join(memory_module.VALID_LEVELS)})."),
    key: str = typer.Argument(..., help="Clé (voir 's1mone memory list')."),
    project: Optional[str] = typer.Option(
        None, "--project", help="Id ou nom de projet (requis si level='project')."
    ),
    session_id: Optional[str] = typer.Option(
        None, "--session-id", help="Id de session (requis si level='session')."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Supprime une entrée mémorisée (ex. 'memory forget persistent chat_history' = comme
    's1mone chat --reset', mais depuis l'extérieur d'une conversation)."""
    if level not in memory_module.VALID_LEVELS:
        console.print(f"[red]Niveau de mémoire invalide : '{level}'. Attendu : {memory_module.VALID_LEVELS}.[/red]")
        raise typer.Exit(code=1)
    project_id = _resolve_project_or_exit(project) if project else None
    if not yes and not typer.confirm(f"Supprimer définitivement {level}/{key} ?"):
        console.print("[grey58]Annulé.[/grey58]")
        raise typer.Exit(code=0)
    try:
        memory_module.forget(level, key, project_id=project_id, session_id=session_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[yellow]Supprimé : {level}/{key}[/yellow]")


@exec_app.command("list")
def exec_list() -> None:
    """Liste la totalité de la liste blanche des commandes système (Phase 9), avec le niveau de
    permission requis pour chacune et le niveau actuellement configuré pour ce terminal local."""
    level = permissions.cli_level()
    table = Table(title="S1M0NE — commandes système (liste blanche)")
    table.add_column("Commande")
    table.add_column("Permission requise")
    table.add_column("Destructrice")
    table.add_column("Chemin")
    table.add_column("Description")
    for spec in permissions.available_commands():
        allowed = spec.permission <= level
        perm_style = "green" if allowed else "grey58"
        table.add_row(
            spec.name,
            f"[{perm_style}]{spec.permission.name}[/{perm_style}]",
            "[bold red]oui[/bold red]" if spec.destructive else "non",
            "oui" if spec.takes_path else "—",
            spec.description if allowed else f"[grey58]{spec.description} (niveau insuffisant)[/grey58]",
        )
    console.print(table)
    console.print(
        f"Niveau du terminal local : [bold]{level.name}[/bold] "
        r"(config.toml \[security] cli_permission_level, ou $S1MONE_CLI_PERMISSION_LEVEL). "
        f"Bac à sable des chemins : [bold]{settings.fs_root}[/bold]."
    )


@exec_app.command("run")
def exec_run(
    command: str = typer.Argument(..., help="Commande complète, ex: 'ls .' ou 'rm brouillon.txt'."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirmer d'avance une commande destructrice."),
) -> None:
    """Exécute une commande système réelle, si elle est dans la liste blanche et que le niveau
    de permission du terminal local le permet. Les commandes destructrices (rm, rmdir) demandent
    toujours une confirmation, sauf si --yes est passé."""
    try:
        result = run_shell_command(
            command,
            level=permissions.cli_level(),
            fs_root=settings.fs_root,
            confirmed=yes,
        )
    except permissions.ConfirmationRequiredError:
        name = command.split()[0] if command.split() else command
        if not typer.confirm(f"Commande destructrice '{command}' — confirmer l'exécution ?"):
            console.print("[grey58]Annulé.[/grey58]")
            raise typer.Exit(code=0) from None
        result = run_shell_command(
            command, level=permissions.cli_level(), fs_root=settings.fs_root, confirmed=True
        )
    except permissions.UnknownCommandError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except permissions.PermissionError_ as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if result["stdout"]:
        console.print(result["stdout"], end="")
    if result["stderr"]:
        console.print(f"[yellow]{result['stderr']}[/yellow]", end="")
    if result.get("timed_out"):
        raise typer.Exit(code=1)
    if result["returncode"] not in (0, None):
        raise typer.Exit(code=result["returncode"])


@plugin_app.command("list")
def plugin_list() -> None:
    """Liste les plugins chargés (Phase 8) : fichiers déposés dans plugins_local/ + paquets pip
    installés exposant un entry point 's1mone'. Voir plugins_local/README.md pour en écrire un."""
    plugins = list_plugins()
    table = Table(title="S1M0NE — plugins chargés")
    table.add_column("Nom")
    table.add_column("Origine")
    table.add_column("Hooks implémentés")
    for p in plugins:
        table.add_row(p["name"], p["source"], ", ".join(p["hooks"]) or "—")
    console.print(table)
    if not plugins:
        console.print(
            f"[grey58]Aucun plugin chargé. Dossier surveillé : {settings.plugins_dir}[/grey58]"
        )
    console.print(
        f"Connecteurs disponibles (intégrés + plugins) : {[c['name'] for c in available_connectors()]}"
    )
    console.print(f"Types de tâches disponibles (intégrés + plugins) : {available_types()}")


@config_app.command("show")
def config_show() -> None:
    """Affiche la configuration effective de S1M0NE (config.toml + .env fusionnés), secrets
    masqués (Settings.as_safe_dict()) — lecture seule, modifie les fichiers toi-même si besoin."""
    from rich.markup import escape

    safe = settings.as_safe_dict()
    for section, values in safe.items():
        if section == "_env_keys_present":
            continue
        table = Table(title=escape(f"[{section}]"))
        table.add_column("Clé")
        table.add_column("Valeur")
        if isinstance(values, dict):
            for k, v in values.items():
                table.add_row(str(k), str(v))
        else:
            table.add_row(section, str(values))
        console.print(table)

    env_keys = safe.get("_env_keys_present", [])
    console.print(
        f"[dim]Variables d'environnement actives (.env) : {', '.join(env_keys) or 'aucune'}[/dim]"
    )


@cache_app.command("list")
def cache_list_cmd(
    limit: int = typer.Option(50, help="Nombre maximum d'entrées affichées (les plus récentes)."),
) -> None:
    """Liste les entrées du cache de recherche (Phase 4), complète les compteurs de 's1mone stats'
    en montrant le détail : clé, source, âge, état (valide/expirée), taille."""
    entries = cache_list(limit=limit)
    table = Table(title="S1M0NE — cache de recherche")
    table.add_column("Clé")
    table.add_column("Source")
    table.add_column("Créée à")
    table.add_column("État")
    table.add_column("Taille")
    for e in entries:
        etat = "[green]valide[/green]" if not e["expired"] else "[red]expirée[/red]"
        if not e["expired"]:
            etat += f" ({e['seconds_remaining']}s restantes)"
        table.add_row(
            e["key"],
            e["source"] or "-",
            format_timestamp(e["created_at"]),
            etat,
            f"{e['value_size']} o",
        )
    console.print(table)
    if not entries:
        console.print("[grey58]Cache vide.[/grey58]")


@cache_app.command("clear")
def cache_clear_cmd(
    key: Optional[str] = typer.Option(
        None, "--key", help="Ne supprime que cette clé précise (voir 's1mone cache list')."
    ),
    expired_only: bool = typer.Option(
        False, "--expired-only", help="Ne supprime que les entrées déjà expirées (garde les valides)."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Vide le cache de recherche, en tout ou en partie. Sans danger : au pire, la prochaine
    recherche recontacte la source au lieu de servir une réponse déjà connue (Phase 4)."""
    if key:
        if not yes and not typer.confirm(f"Supprimer l'entrée de cache '{key}' ?"):
            console.print("[grey58]Annulé.[/grey58]")
            raise typer.Exit(code=0)
        cache_delete(key)
        console.print(f"[yellow]Entrée '{key}' supprimée (si elle existait).[/yellow]")
        return
    if expired_only:
        if not yes and not typer.confirm("Supprimer toutes les entrées expirées du cache ?"):
            console.print("[grey58]Annulé.[/grey58]")
            raise typer.Exit(code=0)
        n = cache_cleanup()
        console.print(f"[yellow]{n} entrée(s) expirée(s) supprimée(s).[/yellow]")
        return
    if not yes and not typer.confirm("Vider ENTIÈREMENT le cache de recherche (valides + expirées) ?"):
        console.print("[grey58]Annulé.[/grey58]")
        raise typer.Exit(code=0)
    n = cache_clear_all()
    console.print(f"[yellow]{n} entrée(s) supprimée(s) (cache entièrement vidé).[/yellow]")


@notes_app.command("index")
def notes_index_cmd(
    path: str = typer.Argument(..., help="Fichier ou dossier à indexer (.md/.markdown/.txt)."),
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Parcourir les sous-dossiers (défaut : oui)."
    ),
) -> None:
    """Indexe des notes personnelles pour la recherche plein texte (Catégorie F, mini second
    brain). Rien n'est jamais indexé automatiquement : geste explicite à chaque fois, comme un
    'git add'. Ré-indexer un fichier déjà connu remplace son contenu (jamais de doublon)."""
    from core.notes import NotesUnavailableError, index_path

    try:
        result = index_path(path, recursive=recursive)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except NotesUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        f"[green]{result['indexed']} note(s) indexée(s)[/green], "
        f"{result['skipped']} fichier(s) ignoré(s) (extension non prise en charge)."
    )
    for err in result["errors"]:
        console.print(f"[red]Erreur : {err}[/red]")


@notes_app.command("search")
def notes_search_cmd(
    query: str = typer.Argument(..., help="Termes recherchés (recherche par mot-clé, pas par sens)."),
    limit: int = typer.Option(20, help="Nombre maximum de résultats."),
) -> None:
    """Recherche dans les notes déjà indexées (titre + contenu), classées par pertinence."""
    from rich.markup import escape

    from core.notes import NotesUnavailableError, search_notes

    try:
        results = search_notes(query, limit=limit)
    except NotesUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not results:
        console.print("[grey58]Aucun résultat.[/grey58]")
        return
    for r in results:
        # escape() est indispensable ici : le titre/snippet vient du contenu LIBRE de l'utilisateur
        # et peut contenir des crochets ('[...]', notamment ceux ajoutés par snippet() pour
        # surligner les mots trouvés) que Rich interpréterait sinon comme des balises de style.
        console.print(f"[bold]{escape(r['title'])}[/bold]  [dim]({escape(r['path'])})[/dim]")
        console.print(f"  {escape(r['snippet'])}")


@notes_app.command("stats")
def notes_stats_cmd() -> None:
    """Nombre de notes actuellement indexées."""
    from core.notes import notes_stats

    stats = notes_stats()
    if not stats["available"]:
        console.print("[red]Recherche de notes indisponible sur ce SQLite (FTS5 non supporté).[/red]")
        raise typer.Exit(code=1)
    console.print(f"{stats['total']} note(s) indexée(s).")


@notes_app.command("clear")
def notes_clear_cmd(
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Vide entièrement l'index de notes (les fichiers d'origine ne sont jamais touchés)."""
    from core.notes import NotesUnavailableError, clear_notes_index

    if not yes and not typer.confirm("Vider entièrement l'index de notes ?"):
        console.print("[grey58]Annulé.[/grey58]")
        raise typer.Exit(code=0)
    try:
        n = clear_notes_index()
    except NotesUnavailableError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[yellow]{n} note(s) retirée(s) de l'index.[/yellow]")


@discover_app.command("list")
def discover_list_cmd(
    site: Optional[str] = typer.Option(None, "--site", help="Filtrer par site (npm, pypi, github, gitlab, codeberg, huggingface, sourceforge)."),
    category: Optional[str] = typer.Option(None, "--category", help="Filtrer par catégorie (ex: 'CLI', 'self-hosted', 'LLM'...)."),
) -> None:
    """Liste le catalogue statique de découverte (Catégorie G) : 100 projets réels et notables,
    compilés une fois par recherche web, embarqués avec S1M0NE — zéro appel réseau pour parcourir
    cette liste. Pour une recherche EN DIRECT sur ces mêmes sites, voir 's1mone search'."""
    from core.discover import catalog_metadata, list_entries

    entries = list_entries(site=site, category=category)
    meta = catalog_metadata()
    table = Table(title=f"S1M0NE — catalogue de découverte (compilé le {meta['compiled_on']})")
    table.add_column("Nom")
    table.add_column("Site")
    table.add_column("Catégorie")
    table.add_column("Description")
    for e in entries:
        table.add_row(e["name"], e["site"], e["category"], e["description"])
    console.print(table)
    console.print(f"[dim]{len(entries)} / {meta['total']} entrées. {meta['note']}[/dim]")


@discover_app.command("search")
def discover_search_cmd(
    query: str = typer.Argument(..., help="Mot recherché (nom, description ou catégorie)."),
) -> None:
    """Recherche par mot-clé dans le catalogue statique de découverte (Catégorie G)."""
    from rich.markup import escape

    from core.discover import search_catalog

    results = search_catalog(query)
    if not results:
        console.print("[grey58]Aucun résultat.[/grey58]")
        return
    for e in results:
        console.print(f"[bold]{escape(e['name'])}[/bold] [dim]({e['site']} / {e['category']})[/dim]")
        console.print(f"  {escape(e['description'])}")
        console.print(f"  [blue]{e['url']}[/blue]")


@discover_app.command("sites")
def discover_sites_cmd() -> None:
    """Liste les sites présents dans le catalogue de découverte."""
    from core.discover import available_sites

    for s in available_sites():
        console.print(f"- {s}")


@discover_app.command("install")
def discover_install_cmd(
    site: str = typer.Argument(..., help="Site : npm, pypi, github, gitlab, codeberg, huggingface (PAS sourceforge)."),
    name: str = typer.Argument(..., help="Nom du paquet (npm/pypi) ou 'owner/repo' (github/gitlab/codeberg/huggingface)."),
    url: Optional[str] = typer.Option(None, "--url", help="URL du dépôt (auto-détectée si le nom existe dans le catalogue statique)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Installe RÉELLEMENT une app (npm install / pip install / git clone), confinée sous
    fs_root/installed_apps/ — jamais d'installation globale sur la machine. Cette commande
    télécharge et exécute du code tiers (comportement normal de npm/pip/git), affiché
    intégralement, jamais masqué. Utilise ensuite 's1mone exec ls installed_apps/...' (le
    terminal existant de S1M0NE) pour inspecter ce qui a été installé."""
    from core.app_install import (
        InstallConfirmationRequiredError,
        InvalidNameError,
        InvalidUrlError,
        UnsupportedSiteError,
        install_app,
    )
    from core.discover import list_entries

    resolved_url = url
    if resolved_url is None:
        for entry in list_entries(site=site):
            if entry["name"].lower() == name.lower():
                resolved_url = entry["url"]
                break

    if not yes:
        console.print(
            f"[yellow]Installation réelle de '{name}' ({site}) — télécharge et exécute du code "
            f"tiers, confiné sous fs_root/installed_apps/.[/yellow]"
        )
        if not typer.confirm("Confirmer l'installation ?"):
            console.print("[grey58]Annulé.[/grey58]")
            raise typer.Exit(code=0)

    try:
        result = install_app(site, name, resolved_url, confirmed=True)
    except (UnsupportedSiteError, InvalidNameError, InvalidUrlError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except InstallConfirmationRequiredError as exc:  # ne devrait pas arriver ici (confirmed=True)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    status = "[green]réussie[/green]" if result["ok"] else "[red]échouée[/red]"
    console.print(f"Commande : [dim]{result['command_display']}[/dim]")
    console.print(f"Installation {status} en {result['duration_seconds']}s dans {result['install_dir']}")
    console.print(result["output"])
    if not result["ok"]:
        raise typer.Exit(code=1)


@discover_app.command("installed")
def discover_installed_cmd() -> None:
    """Historique des installations réelles effectuées via S1M0NE (plus récentes en premier)."""
    from core.app_install import list_installed

    entries = list_installed()
    if not entries:
        console.print("[grey58]Aucune installation effectuée pour l'instant.[/grey58]")
        return
    table = Table(title="Applications installées via S1M0NE")
    table.add_column("Site")
    table.add_column("Nom")
    table.add_column("Statut")
    table.add_column("Dossier")
    for e in entries:
        status = "[green]ok[/green]" if e["ok"] else "[red]échec[/red]"
        table.add_row(e["site"], e["name"], status, e["install_dir"])
    console.print(table)


@discover_app.command("run")
def discover_run_cmd(
    site: str = typer.Argument(..., help="Site de l'app déjà installée (github, npm, pypi...)."),
    name: str = typer.Argument(..., help="Nom du paquet/dépôt tel qu'installé (ex: 'owner/repo')."),
    runner: str = typer.Argument(..., help="Interpréteur autorisé : python3, python, node, npm, java, ruby, php, perl."),
    entry: str = typer.Argument(..., help="Fichier à exécuter, relatif au dossier installé."),
    args: list[str] = typer.Argument(None, help="Arguments supplémentaires passés au script."),
    network: bool = typer.Option(False, "--network", help="Autoriser l'accès réseau (coupé par défaut)."),
    memory_mb: int = typer.Option(512, "--memory-mb", help="Limite mémoire du sandbox (Mo)."),
    cpu_seconds: int = typer.Option(30, "--cpu-seconds", help="Limite de temps CPU du sandbox (s)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Exécute RÉELLEMENT un fichier d'une app déjà installée (Cat. G+), confinée par Firejail
    (namespaces + seccomp, aucun daemon, overhead quasi nul — pas de VM, adapté à une machine
    faible). Réseau coupé par défaut, mémoire/CPU plafonnés, vue disque restreinte au dossier de
    l'app. Refuse d'exécuter si Firejail n'est pas installé (jamais de repli non sandboxé)."""
    from core.app_install import InvalidNameError
    from core.app_run import (
        InvalidEntryError,
        NotInstalledError,
        RunConfirmationRequiredError,
        SandboxUnavailableError,
        UnknownRunnerError,
        run_app,
    )

    if not yes:
        console.print(
            f"[yellow]Exécution réelle de '{name}' ({site}) via {runner} — sandboxée par "
            f"Firejail, réseau {'autorisé' if network else 'coupé'}.[/yellow]"
        )
        if not typer.confirm("Confirmer l'exécution ?"):
            console.print("[grey58]Annulé.[/grey58]")
            raise typer.Exit(code=0)

    try:
        result = run_app(
            site,
            name,
            runner,
            entry,
            list(args or []),
            network=network,
            memory_mb=memory_mb,
            cpu_seconds=cpu_seconds,
            confirmed=True,
        )
    except (
        InvalidNameError,
        NotInstalledError,
        UnknownRunnerError,
        InvalidEntryError,
        SandboxUnavailableError,
    ) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except RunConfirmationRequiredError as exc:  # ne devrait pas arriver ici (confirmed=True)
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    status = "[green]réussie[/green]" if result["ok"] else "[red]échouée[/red]"
    console.print(f"Commande : [dim]{result['command_display']}[/dim]")
    console.print(f"Exécution {status} en {result['duration_seconds']}s")
    console.print(result["output"])
    if not result["ok"]:
        raise typer.Exit(code=1)


@discover_app.command("runs")
def discover_runs_cmd() -> None:
    """Historique des exécutions réelles effectuées via S1M0NE (plus récentes en premier)."""
    from core.app_run import list_runs

    entries = list_runs()
    if not entries:
        console.print("[grey58]Aucune exécution effectuée pour l'instant.[/grey58]")
        return
    table = Table(title="Exécutions d'apps installées via S1M0NE")
    table.add_column("Site")
    table.add_column("Nom")
    table.add_column("Commande")
    table.add_column("Statut")
    for e in entries:
        status = "[green]ok[/green]" if e["ok"] else "[red]échec[/red]"
        table.add_row(e["site"], e["name"], e["command_display"], status)
    console.print(table)


@backup_app.command("create")
def backup_create() -> None:
    """Crée une sauvegarde horodatée de la base SQLite (mémoire, tâches, cache). Purge
    automatiquement les plus anciennes au-delà de config.toml [backup] keep (défaut : 10)."""
    try:
        path = backup_db()
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Sauvegarde créée :[/green] {path}")


@backup_app.command("list")
def backup_list() -> None:
    """Liste les sauvegardes existantes (les plus récentes d'abord)."""
    backups = list_backups()
    table = Table(title="S1M0NE — sauvegardes")
    table.add_column("Fichier")
    table.add_column("Taille")
    table.add_column("Créée à")
    for b in backups:
        size_kb = b["size_bytes"] / 1024
        table.add_row(Path(b["path"]).name, f"{size_kb:.1f} Ko", _fmt_ts(b["created_at"]))
    console.print(table)
    if not backups:
        console.print(f"[grey58]Aucune sauvegarde. Dossier : {settings.backups_dir}[/grey58]")


@project_app.command("create")
def project_create(
    name: str = typer.Argument(..., help="Nom du projet (unique)."),
    description: Optional[str] = typer.Option(None, "--description", help="Description libre."),
    path: Optional[str] = typer.Option(None, "--path", help="Chemin associé (facultatif)."),
) -> None:
    """Crée un nouveau projet."""
    try:
        project_id = projects_module.create_project(name, description=description, path=path)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Projet créé :[/green] {project_id} ({name})")


@project_app.command("list")
def project_list() -> None:
    """Liste tous les projets."""
    items = projects_module.list_projects()
    table = Table(title="S1M0NE — projets")
    table.add_column("Id")
    table.add_column("Nom")
    table.add_column("Description")
    table.add_column("Mis à jour")
    for p in items:
        table.add_row(p["id"], p["name"], p.get("description") or "", _fmt_ts(p["updated_at"]))
    console.print(table)
    if not items:
        console.print(
            "[grey58]Aucun projet. Crée-en un avec 's1mone project create <nom>'.[/grey58]"
        )


@project_app.command("show")
def project_show(identifier: str = typer.Argument(..., help="Id ou nom du projet.")) -> None:
    """Affiche le détail d'un projet."""
    project = projects_module.resolve_project(identifier)
    if project is None:
        console.print(f"[red]Projet inconnu : '{identifier}'.[/red]")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(project, ensure_ascii=False))


@project_app.command("delete")
def project_delete(
    identifier: str = typer.Argument(..., help="Id ou nom du projet."),
    keep_memory: bool = typer.Option(
        False, "--keep-memory", help="Ne pas effacer la mémoire associée (conservée orpheline)."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Supprime un projet (et sa mémoire associée, sauf --keep-memory)."""
    project = projects_module.resolve_project(identifier)
    if project is None:
        console.print(f"[red]Projet inconnu : '{identifier}'.[/red]")
        raise typer.Exit(code=1)
    if not yes and not typer.confirm(f"Supprimer définitivement le projet '{project['name']}' ?"):
        console.print("[grey58]Annulé.[/grey58]")
        raise typer.Exit(code=0)
    projects_module.delete_project(project["id"], delete_memory=not keep_memory)
    console.print(f"[yellow]Projet supprimé : {project['name']}[/yellow]")


@schedule_app.command("create")
def schedule_create(
    task_type: str = typer.Argument(
        ..., help=f"Type de tâche à répéter. Disponibles : {', '.join(available_types())}"
    ),
    interval: str = typer.Option(
        ..., "--interval", help="Fréquence : '30s', '5m', '2h', '1d', ou un nombre de secondes."
    ),
    param: list[str] = typer.Option(
        [], "--param", help="Paramètre au format clé=valeur (répétable)."
    ),
    run_now: bool = typer.Option(
        False, "--run-now", help="Crée aussi une première exécution immédiate."
    ),
) -> None:
    """Planifie l'exécution récurrente d'un type de tâche."""
    parameters: dict[str, str] = {}
    for item in param:
        if "=" not in item:
            console.print(f"[red]Paramètre invalide (attendu clé=valeur) : {item}[/red]")
            raise typer.Exit(code=1)
        key, value = item.split("=", 1)
        parameters[key] = value

    try:
        seconds = scheduler_module.parse_interval(interval)
        schedule_id = scheduler_module.create_schedule(
            task_type, parameters, interval_seconds=seconds, run_immediately=run_now
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Planification créée :[/green] {schedule_id} (toutes les {interval})")


@schedule_app.command("list")
def schedule_list() -> None:
    """Liste toutes les planifications."""
    items = scheduler_module.list_schedules()
    table = Table(title="S1M0NE — planifications")
    table.add_column("Id")
    table.add_column("Type")
    table.add_column("Intervalle (s)")
    table.add_column("Active")
    table.add_column("Prochaine échéance")
    table.add_column("Dernière exécution")
    for s in items:
        active = "[green]oui[/green]" if s["enabled"] else "[grey58]non[/grey58]"
        table.add_row(
            s["id"],
            s["task_type"],
            str(s["interval_seconds"]),
            active,
            _fmt_ts(s["next_run_at"]),
            _fmt_ts(s["last_run_at"]),
        )
    console.print(table)
    if not items:
        console.print("[grey58]Aucune planification.[/grey58]")


@schedule_app.command("show")
def schedule_show(schedule_id: str = typer.Argument(..., help="Id de la planification.")) -> None:
    """Affiche le détail d'une planification."""
    schedule = scheduler_module.get_schedule(schedule_id)
    if schedule is None:
        console.print(f"[red]Planification introuvable : {schedule_id}[/red]")
        raise typer.Exit(code=1)
    console.print_json(json.dumps(schedule, ensure_ascii=False))


@schedule_app.command("enable")
def schedule_enable(schedule_id: str = typer.Argument(..., help="Id de la planification.")) -> None:
    """Réactive une planification désactivée."""
    if not scheduler_module.set_enabled(schedule_id, True):
        console.print(f"[red]Planification introuvable : {schedule_id}[/red]")
        raise typer.Exit(code=1)
    console.print("[green]Planification réactivée.[/green]")


@schedule_app.command("disable")
def schedule_disable(schedule_id: str = typer.Argument(..., help="Id de la planification.")) -> None:
    """Désactive une planification sans la supprimer (les échéances passées ne sont pas rattrapées)."""
    if not scheduler_module.set_enabled(schedule_id, False):
        console.print(f"[red]Planification introuvable : {schedule_id}[/red]")
        raise typer.Exit(code=1)
    console.print("[yellow]Planification désactivée.[/yellow]")


@schedule_app.command("delete")
def schedule_delete(
    schedule_id: str = typer.Argument(..., help="Id de la planification."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Ne pas demander de confirmation."),
) -> None:
    """Supprime définitivement une planification."""
    if scheduler_module.get_schedule(schedule_id) is None:
        console.print(f"[red]Planification introuvable : {schedule_id}[/red]")
        raise typer.Exit(code=1)
    if not yes and not typer.confirm("Supprimer définitivement cette planification ?"):
        console.print("[grey58]Annulé.[/grey58]")
        raise typer.Exit(code=0)
    scheduler_module.delete_schedule(schedule_id)
    console.print("[yellow]Planification supprimée.[/yellow]")


@notify_app.command("list")
def notify_list(
    unread_only: bool = typer.Option(
        False, "--unread-only", help="N'affiche que les notifications non lues."
    ),
    limit: int = typer.Option(20, help="Nombre maximum de notifications affichées."),
) -> None:
    """Liste les notifications (les plus récentes d'abord)."""
    items = notifications_module.list_notifications(unread_only=unread_only, limit=limit)
    table = Table(title="S1M0NE — notifications")
    table.add_column("État")
    table.add_column("Niveau")
    table.add_column("Message", max_width=70)
    table.add_column("Créée à")
    level_colors = {"success": "green", "error": "red", "info": "cyan"}
    for n in items:
        state = "[grey58]lue[/grey58]" if n["read"] else "[bold]non lue[/bold]"
        color = level_colors.get(n["level"], "white")
        table.add_row(state, f"[{color}]{n['level']}[/{color}]", n["message"], _fmt_ts(n["created_at"]))
    console.print(table)
    if not items:
        console.print("[grey58]Aucune notification.[/grey58]")


@notify_app.command("read")
def notify_read(
    notification_id: Optional[str] = typer.Argument(
        None, help="Id de la notification à marquer comme lue (voir 's1mone notify list')."
    ),
    all_: bool = typer.Option(False, "--all", help="Marque toutes les notifications comme lues."),
) -> None:
    """Marque une notification (ou toutes, avec --all) comme lue."""
    if all_:
        n = notifications_module.mark_all_read()
        console.print(f"[green]{n} notification(s) marquée(s) comme lue(s).[/green]")
        return
    if not notification_id:
        console.print("[red]Précise un id, ou utilise --all.[/red]")
        raise typer.Exit(code=1)
    ok = notifications_module.mark_read(notification_id)
    if ok:
        console.print("[green]Notification marquée comme lue.[/green]")
    else:
        console.print(f"[red]Aucune notification avec l'id '{notification_id}'.[/red]")
        raise typer.Exit(code=1)


@notify_app.command("clear")
def notify_clear() -> None:
    """Supprime toutes les notifications (lues et non lues)."""
    n = notifications_module.clear_all()
    console.print(f"[green]{n} notification(s) supprimée(s).[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
