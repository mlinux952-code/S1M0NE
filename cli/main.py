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

import typer
from rich.console import Console
from rich.table import Table

from core.config import settings
from system.healthcheck import run_all_checks
from system.monitor import get_platform_info, get_snapshot, resource_level

app = typer.Typer(
    name="s1mone",
    help="S1M0NE — plateforme personnelle intelligente (maison numérique).",
    add_completion=True,
)
console = Console()

_LEVEL_COLORS = {"NORMAL": "green", "WARNING": "yellow", "CRITICAL": "bold red"}


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
    color = _LEVEL_COLORS.get(level, "white")
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
    color = _LEVEL_COLORS.get(level, "white")

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
