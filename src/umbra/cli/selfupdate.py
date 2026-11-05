"""`umbra self-update`: pasar a la última versión publicada (instalación estable)."""

import typer
from rich.markdown import Markdown
from rich.padding import Padding
from rich.text import Text

from umbra import __version__, service
from umbra.unified import version
from umbra.unified.output import console, fail
from umbra.unified.store import ACTIVE_RUN_STATES


def _busy_here() -> list[int]:
    """Tareas trabajando en el proyecto actual: su worker corre desde esta instalación."""
    try:
        ctx = service.load()
    except service.OpError:
        return []  # fuera de un proyecto umbra: nada que vigilar aquí
    marks = ",".join("?" * len(ACTIVE_RUN_STATES))
    return [r[0] for r in ctx.conn.execute(
        f"SELECT t.number FROM run r JOIN task t ON t.id = r.task_id"
        f" WHERE r.status IN ({marks}) AND r.status NOT IN ('PAUSED', 'WAITING_APPROVAL')",
        ACTIVE_RUN_STATES)]


def self_update(
    check: bool = typer.Option(False, "--check", help="Solo mirar si hay una versión nueva"),
    yes: bool = typer.Option(False, "--yes", "-y", help="No pedir confirmación"),
) -> None:
    """Instala la última versión publicada de umbra (no lo que está a medias en main)."""
    try:
        latest = version.latest()
    except version.VersionError as e:
        fail(str(e))
    console.print(f"Instalada: {version.label()}", highlight=False)
    if not latest:
        console.print("Todavía no hay versiones publicadas.")
        return
    console.print(f"Última publicada: v{latest}", highlight=False)
    newer = version.parse(latest) > version.parse(__version__)
    if not newer and not version.is_dev():
        console.print("Ya tienes la última versión.")
        return
    if notes := version.notes(latest):
        console.print(Text(f"\nQué trae v{latest}:", style="bold"))
        console.print(Padding(Markdown(notes), (0, 0, 0, 2)))  # reflowa el CHANGELOG cortado
    if check:
        return
    if busy := _busy_here():
        fail(f"hay tareas trabajando ({', '.join(map(str, busy))}) y su worker usa esta "
             "instalación: espera a que terminen o páusalas, y vuelve a intentarlo", code=4)
    action = (f"actualizar a v{latest}" if newer
              else f"pasar de la copia de desarrollo a la versión estable v{latest}")
    if not yes and not typer.confirm(f"¿{action[0].upper()}{action[1:]}?"):
        raise typer.Exit(1)
    try:
        console.print(version.install(latest), highlight=False)
    except version.VersionError as e:
        fail(str(e))
