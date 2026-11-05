"""`umbra db`: MySQL local. Consultar es libre; un cambio queda pendiente hasta que la persona
lo aplica (`umbra db apply` en su terminal o el botón de Telegram)."""

import typer
from rich.table import Table

from umbra import service
from umbra.cli import context
from umbra.cli.routines import _op
from umbra.unified.output import emit, fail

app = typer.Typer(help="MySQL local: consultar libre, cambiar con tu permiso",
                  no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")
DbOpt = typer.Option(None, "--db", help="Base de datos (por defecto [mysql] database)")


@app.command()
def query(sql: str, database: str | None = DbOpt, as_json: bool = JsonOpt) -> None:
    """Consulta de solo lectura (SELECT, SHOW, DESCRIBE, EXPLAIN)."""
    ctx = context.load(as_json)
    result = _op(service.db_query, ctx, sql, database, as_json=as_json)

    def render(c) -> None:
        t = Table(*result["columns"])
        for row in result["rows"]:
            t.add_row(*row)
        c.print(t)
        if result["truncated"]:
            c.print(f"(solo las primeras {len(result['rows'])} filas)")

    emit(result, as_json, render)


@app.command()
def change(sql: str, database: str | None = DbOpt, as_json: bool = JsonOpt) -> None:
    """Propone un cambio (INSERT, UPDATE, ALTER…): no se ejecuta hasta que lo apliques."""
    ctx = context.load(as_json)
    result = _op(service.db_propose, ctx, sql, database, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"Cambio {result['id']} pendiente: no se ha aplicado. La persona decide con "
        f"`umbra db apply {result['id']}` o el botón de Telegram.", markup=False))


@app.command("list")
def list_(as_json: bool = JsonOpt) -> None:
    """Cambios propuestos que esperan tu decisión."""
    ctx = context.load(as_json)
    pending = service.db_pending(ctx)

    def render(c) -> None:
        if not pending:
            c.print("No hay cambios pendientes.")
        for p in pending:
            c.print(f"{p['id']} ({p['database'] or 'base por defecto'}): {p['sql']}",
                    markup=False)

    emit(pending, as_json, render)


def _human(as_json: bool) -> None:
    if not service.interactive():
        fail("aplicar o descartar un cambio de BD requiere una terminal interactiva (lo decide "
             "la persona)", code=3, as_json=as_json)


@app.command()
def apply(change_id: str, as_json: bool = JsonOpt) -> None:
    """Aplica un cambio pendiente."""
    _human(as_json)
    ctx = context.load(as_json)
    r = _op(service.db_apply, ctx, change_id, as_json=as_json)
    emit(r, as_json, lambda c: c.print(f"Cambio {change_id} aplicado: {r['affected']} filas.",
                                       markup=False))


@app.command()
def discard(change_id: str, as_json: bool = JsonOpt) -> None:
    """Descarta un cambio pendiente sin aplicarlo."""
    _human(as_json)
    ctx = context.load(as_json)
    _op(service.db_discard, ctx, change_id, as_json=as_json)
    emit({"id": change_id}, as_json, lambda c: c.print(f"Cambio {change_id} descartado."))
