"""Comandos del grupo `umbra spec`."""

from pathlib import Path

import typer

from umbra import service
from umbra.cli import context
from umbra.unified.explain import spec_line
from umbra.unified.output import emit, fail

app = typer.Typer(help="Specs: de la spec a las tareas.", no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


@app.command("new")
def new(idea: str = typer.Argument(..., help="La idea, en una frase")) -> None:
    """Conversa con el asistente hasta tener spec, plan y tareas en borrador."""
    if not service.interactive():
        fail("`umbra spec new` necesita una terminal interactiva (es una conversación); "
             "ejecútalo desde tu terminal, no desde un script o un pipe.", code=2)
    ctx = context.load()
    try:
        service.spec_max_cost(ctx)
        service.preflight(ctx, confirm=lambda q: typer.confirm(q, default=False))
    except service.OpError as e:
        fail(str(e), code=e.code)
    from umbra.cli.design import ask_system
    ask_system(ctx.root, ctx.config)  # el sistema de diseño del proyecto, si aún no lo dijo
    from umbra.cli.spec_screen import SpecApp  # textual solo se carga si se usa
    SpecApp(ctx, idea).run()


@app.command("resume")
def resume(ref: str | None = typer.Argument(
        None, help="Número (NNN) o carpeta de la spec; sin argumento, la última abierta")) -> None:
    """Reabre una conversación en su fase, con su historial."""
    if not service.interactive():
        fail("`umbra spec resume` necesita una terminal interactiva (es una conversación).",
             code=2)
    ctx = context.load()
    try:
        service.spec_max_cost(ctx)
        service.preflight(ctx, confirm=lambda q: typer.confirm(q, default=False))
        row = service.spec_resume_target(ctx, ref)
        lock = service.spec_lock(ctx, row["id"])
    except service.OpError as e:
        fail(str(e), code=e.code)
    from umbra.cli.spec_screen import SpecApp
    SpecApp(ctx, row["idea"], conv_id=row["id"], lock=lock).run()


@app.command("list")
def list_(as_json: bool = JsonOpt) -> None:
    """Avance por spec: fase, historias hechas y costo."""
    ctx = context.load(as_json)
    result = service.spec_progress(ctx)

    def render(c):
        if not result:
            c.print("No hay specs todavía. Empieza con `umbra spec new`.")
        for p in result:
            c.print(spec_line(p), highlight=False)

    emit(result, as_json, render)


@app.command("tasks")
def tasks(
    ruta: Path = typer.Argument(..., help="Carpeta de la spec (con spec.md)"),
    yes: bool = typer.Option(False, "--yes", help="Confirma sin preguntar"),
    as_json: bool = JsonOpt,
) -> None:
    """Crea una tarea en borrador por historia; si editaste historias, ofrece actualizarlas."""
    ctx = context.load(as_json)
    try:
        result = service.spec_tasks(ctx, ruta)
        stale = service.misaligned(ctx, ruta) if result["existing"] else []
        result.update(misaligned=stale, updated=[], skipped=[])
        if stale:
            if not as_json:
                typer.echo("Historias editadas desde que se crearon sus tareas:")
                for m in stale:
                    typer.echo(f"  tarea {m['number']}: «{m['title']}»"
                               + ("" if m["updatable"] else f" (no se toca: {m['reason']})"))
                    for f, d in m["changes"].items():
                        typer.echo(f"    {f}:\n      - {d['old']}\n      + {d['new']}")
            # --json nunca pregunta: solo actualiza con --yes
            if any(m["updatable"] for m in stale) and (
                    yes or (not as_json and typer.confirm("¿Actualizar estas tareas?"))):
                result.update(service.spec_tasks_update(ctx, ruta))
            else:
                result["skipped"] = [{"number": m["number"], "reason": m["reason"] or
                                      "sin confirmar"} for m in stale]
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)

    def render(c):
        if result["updated"]:
            c.print(f"tareas actualizadas: {result['updated']}.")
        elif result["misaligned"]:
            c.print("no se actualizó ninguna tarea.")
        elif result["created"]:
            c.print(f"tareas en borrador creadas: {result['created']}, encadenadas por "
                    "prioridad. Revísalas con `umbra task list` y acéptalas con "
                    "`umbra task accept`.")
        else:
            c.print(f"no hay historias nuevas: ya existen las tareas {result['existing']}.")

    emit(result, as_json, render)
