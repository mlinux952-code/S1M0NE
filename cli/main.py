"""
cli/main.py — Terminal Gateway de S1M0NE (Phase 1 : commandes minimales).

Commandes disponibles :
    s1mone status   -> diagnostic complet (config, sqlite, disque, ressources)
    s1mone system   -> aperçu CPU/RAM/swap/disque en direct
    s1mone version  -> version + infos plateforme

Le terminal doit rester utilisable même sans l'interface web (mega-prompt §6) :
cette CLI ne dépend d'aucun serveur, elle appelle directement les modules core/system.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from core.config import settings
from system.healthcheck import run_all_checks
from system.monitor import get_platform_info, get_snapshot, resource_level
from tasks.manager import (
    cancel_task,
    get_task,
    list_tasks,
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


_COMMANDS_NEEDING_DB = {"status", "task"}


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


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


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
        processed = asyncio.run(run_pending_tasks())
        console.print(f"{processed} tâche(s) traitée(s).")
        return

    console.print("Worker de tâches démarré (CTRL+C pour arrêter)...")
    try:
        asyncio.run(worker_loop(interval_seconds=interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker arrêté.[/yellow]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
