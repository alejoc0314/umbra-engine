"""Comandos `umbra memory`: lo que umbra aprendió de las decisiones de la persona."""

import typer

from umbra.cli import context
from umbra.management import memory
from umbra.unified.output import emit, fail

app = typer.Typer(help="Lo aprendido en este repo: ver y reconstruir .umbra/aprendido.md.",
                  no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")
EMPTY = "umbra aún no ha aprendido nada en este repo"


@app.command("show")
def show(as_json: bool = JsonOpt) -> None:
    """Muestra .umbra/aprendido.md (decisiones, respuestas y rutas autorizadas)."""
    ctx = context.load(as_json)
    text = memory.load(ctx.udir, limit=10 ** 9)
    emit({"path": (ctx.udir / memory.FILE).as_posix(), "text": text, "empty": not text},
         as_json, lambda c: c.print(text if text else EMPTY, markup=False, highlight=False))


context_app = typer.Typer(help="CONTEXT.md: el mapa del repositorio que leen los agentes.",
                          no_args_is_help=True)


@context_app.command("build")
def context_build(as_json: bool = JsonOpt) -> None:
    """Genera o actualiza CONTEXT.md con el cartógrafo (solo escribe ese archivo)."""
    from umbra import service
    ctx = context.load(as_json)
    try:
        result = service.context_build(ctx)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        ("CONTEXT.md al día: " + result["summary"]) if result["changed"]
        else "CONTEXT.md sin cambios."))


@app.command("rebuild")
def rebuild(as_json: bool = JsonOpt) -> None:
    """Regenera .umbra/aprendido.md a partir del historial de decisiones."""
    ctx = context.load(as_json)
    try:
        path = memory.rebuild(ctx.conn, ctx.udir)
    except OSError as e:
        fail(f"no se pudo escribir {memory.FILE}: {e}", as_json=as_json)
    emit({"path": path.as_posix()}, as_json,
         lambda c: c.print(f"{memory.FILE} regenerado en {path.as_posix()}"))
