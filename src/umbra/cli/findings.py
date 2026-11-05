"""`umbra finding`: decidir sobre los hallazgos que frenaron una tarea."""

import typer
from rich.table import Table

from umbra import service
from umbra.cli import context
from umbra.cli.routines import _op
from umbra.unified.output import console, emit, fail

app = typer.Typer(help="Decidir sobre los hallazgos que frenaron una tarea", no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")
Which = typer.Argument(None, help="Números de `umbra finding list` (vacío = todos)")


@app.command("list")
def list_(number: int, as_json: bool = JsonOpt) -> None:
    """Hallazgos sin decidir: los que frenaron la tarea o, si no hay, los demás abiertos."""
    ctx = context.load(as_json)
    pending = (_op(service.pending_findings, ctx, number, as_json=as_json)
               or _op(service.open_findings, ctx, number, as_json=as_json))

    def render(c) -> None:
        if not pending:
            c.print(f"La tarea {number} no tiene hallazgos pendientes de decidir.")
            return
        t = Table("#", "gravedad", "hallazgo", "dónde")
        for i, f in enumerate(pending, 1):
            t.add_row(str(i), f["severity"], f["message"],
                      f"{f['file']}:{f['line']}" if f["file"] else "-")
        c.print(t)
        c.print(f"Si no aplica: umbra finding waive {number} [#...] -m \"motivo\"\n"
                f"Para después (crea una tarea en borrador): umbra finding defer {number} [#...]\n"
                f"Para corregirlo: umbra retry {number}", markup=False)

    emit(pending, as_json, render)


def _decide(number: int, which: list[int] | None, decision: str, reason: str) -> None:
    if not service.interactive():
        fail("decidir sobre hallazgos requiere una terminal interactiva (lo decide la persona)",
             code=3)
    ctx = context.load()
    result = _op(service.decide_findings, ctx, number, which or [], decision, reason)
    console.print(f"{result['decided']} hallazgo(s) decidido(s); quedan {result['remaining']}.",
                  highlight=False)
    if result["tasks"]:
        console.print("Tareas en borrador con lo pendiente: "
                      + ", ".join(map(str, result["tasks"])), highlight=False)
    if result["next_stage"]:
        console.print(f"Siguiente: umbra retry {number} (seguirá desde "
                      f"{result['next_stage']})", markup=False, highlight=False)


@app.command("waive")
def waive(number: int, which: list[int] | None = Which,
          reason: str = typer.Option(..., "--reason", "-m", help="Por qué no aplica")) -> None:
    """Marca hallazgos como «no aplica»: no se corrigen y el revisor no los vuelve a pedir."""
    _decide(number, which, "waived", reason)


@app.command("defer")
def defer(number: int, which: list[int] | None = Which,
          reason: str = typer.Option("se hará después", "--reason", "-m")) -> None:
    """Deja hallazgos para después: crea una tarea en borrador con cada uno."""
    _decide(number, which, "deferred", reason)
