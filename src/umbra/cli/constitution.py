"""`umbra constitucion`: ver y enmendar la constitución del proyecto."""

import typer

from umbra.cli import context
from umbra.management import constitution as con
from umbra.unified.output import console, fail

app = typer.Typer(help="La constitución del proyecto: verla y enmendarla.", no_args_is_help=True)


@app.command("ver")
def show() -> None:
    """Muestra la constitución del proyecto (la reciben todos los agentes)."""
    ctx = context.load(False)
    try:
        console.print(con.show(ctx.root), highlight=False, markup=False)
    except con.ConstitutionError as e:
        fail(str(e))


@app.command("enmendar")
def amend(text: str = typer.Argument(..., help="Qué quieres cambiar, en tus palabras"),
          yes: bool = typer.Option(False, "--yes", "-y", help="Aprobar sin preguntar")) -> None:
    """Un agente redacta la enmienda (y sube la versión); tú la apruebas o la descartas."""
    ctx = context.load(False)
    try:
        diff = con.amend(ctx.conn, ctx.root, ctx.udir, text)
        console.print(diff, highlight=False, markup=False)
        if yes or typer.confirm("¿Apruebas la enmienda?"):
            sha = con.accept(ctx.conn, ctx.root)
            console.print(f"Enmienda aprobada (commit {sha[:10]}).")
        else:
            con.discard(ctx.conn, ctx.root)
            console.print("Enmienda descartada: la constitución queda como estaba.")
    except con.ConstitutionError as e:
        fail(str(e))
