"""Comandos `umbra lesson`: la persona decide qué lecciones aprendidas se aplican (spec 035)."""

import json
from pathlib import Path

import typer

from umbra.cli import context
from umbra.unified.output import emit, fail

app = typer.Typer(help="Lecciones aprendidas: ver, aprobar, descartar, retirar y cosechar.",
                  no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")
STATUS = {"proposed": "propuesta", "approved": "aprobada", "discarded": "descartada",
          "retired": "retirada"}
MARK = {"proposed": "●", "approved": "✓", "discarded": "−", "retired": "↺"}


def _run(as_json: bool, op):
    from umbra import service
    ctx = context.load(as_json)
    try:
        return op(service, ctx)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)


def _zone(zone: list[str]) -> str:
    return ", ".join(zone) if zone else "todo el proyecto"


def _line(item: dict) -> str:
    extra = ""
    if item.get("stale"):
        extra += "  · posible obsoleta"
    if item.get("conflicts"):
        extra += f"  · conflicto con {', '.join(item['conflicts'])}"
    return (f"{MARK[item['status']]} {item['id']:<4} {STATUS[item['status']]:<10} "
            f"{item['text']}  [{_zone(item['zone'])}]{extra}")


@app.command("list")
def list_cmd(all_: bool = typer.Option(False, "--all", help="Incluye descartadas y retiradas"),
             status: str = typer.Option(None, "--status",
                                        help="proposed, approved, discarded o retired"),
             as_json: bool = JsonOpt) -> None:
    """Las lecciones del proyecto: propuestas primero, luego las aprobadas."""
    if status and status not in STATUS:
        fail(f"estado desconocido «{status}»: usa {', '.join(STATUS)}", as_json=as_json)
    items = _run(as_json, lambda s, ctx: s.lesson_list(ctx, status, all_))
    emit(items, as_json, lambda c: c.print(
        "\n".join(_line(i) for i in items) if items else "No hay lecciones que mostrar.",
        markup=False, highlight=False))


@app.command("show")
def show_cmd(lesson: str = typer.Argument(..., help="L7 o 7"), as_json: bool = JsonOpt) -> None:
    """Texto, zona, estado, orígenes, historial y tareas donde se aplicó."""
    item = _run(as_json, lambda s, ctx: s.lesson_show(ctx, lesson))

    def render(c) -> None:
        lines = [_line(item), f"Zona: {_zone(item['zone'])}", "", "Por qué se propone:"]
        lines += [f"  #{o['task']} {o['stage'] or ''} · {o['created_at'][:10]}: {o['detail']}"
                  for o in item["origins_detail"]] or ["  (sin orígenes)"]
        lines += ["", "Historial:"]
        lines += [f"  {h['created_at'][:16]} {h['action']} por {h['actor']} ({h['channel']})"
                  + (f": {h['before']}" if h["before"] else "") for h in item["history"]]
        lines += ["", "Se aplicó en:"]
        lines += [f"  #{a['task']} ({a['run_id'][:8]})" for a in item["applied_in"]] \
            or ["  ninguna tarea todavía"]
        c.print("\n".join(lines), markup=False, highlight=False)
    emit(item, as_json, render)


@app.command("approve")
def approve_cmd(lesson: str = typer.Argument(..., help="L7 o 7"),
                text: str = typer.Option(None, "--text", help="Aprueba con este texto"),
                zone: list[str] = typer.Option(None, "--zone", help="Glob de la zona"),
                project_wide: bool = typer.Option(False, "--project-wide",
                                                  help="Vale para todo el proyecto"),
                as_json: bool = JsonOpt) -> None:
    """Aprueba una propuesta (o vuelve a aprobar una retirada)."""
    item = _run(as_json, lambda s, ctx: s.lesson_approve(ctx, lesson, text, zone,
                                                         project_wide))
    emit(item, as_json, lambda c: c.print(
        f"{item['id']} aprobada: se aplicará en las tareas nuevas de {_zone(item['zone'])}.",
        markup=False, highlight=False))


@app.command("discard")
def discard_cmd(lesson: str = typer.Argument(..., help="L7 o 7"),
                reason: str = typer.Option("", "--reason", help="Por qué"),
                as_json: bool = JsonOpt) -> None:
    """Descarta una propuesta: no se vuelve a proponer igual."""
    item = _run(as_json, lambda s, ctx: s.lesson_discard(ctx, lesson, reason))
    emit(item, as_json, lambda c: c.print(f"{item['id']} descartada.", markup=False))


@app.command("retire")
def retire_cmd(lesson: str = typer.Argument(..., help="L7 o 7"),
               reason: str = typer.Option("", "--reason", help="Por qué"),
               as_json: bool = JsonOpt) -> None:
    """Retira una aprobada: deja de aplicarse y queda en el historial."""
    item = _run(as_json, lambda s, ctx: s.lesson_retire(ctx, lesson, reason))
    emit(item, as_json, lambda c: c.print(
        f"{item['id']} retirada: ya no se aplica en tareas nuevas.", markup=False))


@app.command("resolve")
def resolve_cmd(a: str = typer.Argument(..., help="L7 o 7"),
                b: str = typer.Argument(..., help="L8 o 8"), as_json: bool = JsonOpt) -> None:
    """Marca dos lecciones como compatibles y quita el conflicto."""
    items = _run(as_json, lambda s, ctx: s.lesson_resolve(ctx, a, b))
    emit(items, as_json, lambda c: c.print(
        f"{items[0]['id']} y {items[1]['id']} ya no están en conflicto.", markup=False))


@app.command("export")
def export_cmd(path: Path = typer.Argument(None, help="Archivo de destino (sin él, a pantalla)"),
               as_json: bool = JsonOpt) -> None:
    """Exporta las lecciones del proyecto para llevarlas a otra máquina."""
    data = _run(as_json, lambda s, ctx: s.lesson_export(ctx))
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if path is None:
        typer.echo(text)
        return
    try:
        path.write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        fail(f"no se pudo escribir {path}: {e}", as_json=as_json)
    out = {"path": str(path), "count": len(data["lessons"])}
    emit(out, as_json, lambda c: c.print(
        f"{out['count']} lecciones exportadas a {path}.", markup=False, highlight=False))


@app.command("import")
def import_cmd(path: Path = typer.Argument(..., help="Archivo creado con `umbra lesson export`"),
               as_json: bool = JsonOpt) -> None:
    """Importa lecciones exportadas: llegan con su estado, origen y fechas."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        fail(f"no se pudo leer {path}: {e}", as_json=as_json)
    except ValueError as e:
        fail(f"{path} no es un JSON válido ({e})", as_json=as_json)
    out = _run(as_json, lambda s, ctx: s.lesson_import(ctx, data))
    emit(out, as_json, lambda c: c.print(
        f"{out['created']} nuevas, {out['merged']} ya existían, "
        f"{out['origins_added']} orígenes añadidos.", markup=False, highlight=False))


@app.command("harvest")
def harvest_cmd(as_json: bool = JsonOpt) -> None:
    """Cosecha ya los tropiezos pendientes del proyecto."""
    out = _run(as_json, lambda s, ctx: s.lesson_harvest(ctx))
    emit(out, as_json, lambda c: c.print(
        f"{out['proposed']} lecciones nuevas por decidir." if out["proposed"]
        else "Nada nuevo que proponer.", markup=False))
