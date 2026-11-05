"""`umbra design`: decidir sobre el diseño de una tarea antes de que se construya."""

import typer

from umbra import service
from umbra.cli import context
from umbra.unified.output import emit, fail

app = typer.Typer(help="Diseño: aprobarlo o pedir cambios antes de construir.",
                  no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


@app.command("ok")
def ok(number: int, as_json: bool = JsonOpt) -> None:
    """Da el visto bueno al diseño: Construir maqueta sobre él."""
    ctx = context.load(as_json)
    try:
        result = service.design_approve(ctx, number)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"tarea {number}: diseño aprobado; sigue desde {result['resumed_from']}"))


@app.command("cambios")
def changes(number: int, text: str = typer.Argument(..., help="Qué quieres cambiar"),
            as_json: bool = JsonOpt) -> None:
    """Pide cambios al diseño: el diseñador los aplica y vuelve a preguntarte."""
    ctx = context.load(as_json)
    try:
        result = service.design_changes(ctx, number, text)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(f"tarea {number}: cambios pedidos al diseñador"))
