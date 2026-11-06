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


@app.command("elegir")
def pick(number: int, option: int = typer.Argument(..., help="Número de la dirección (1, 2…)"),
         as_json: bool = JsonOpt) -> None:
    """Elige una de las direcciones propuestas; el diseñador sigue esa línea."""
    ctx = context.load(as_json)
    try:
        result = service.design_pick(ctx, number, option)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"tarea {number}: elegida «{result['chosen']}»; el diseñador sigue en esa línea",
        highlight=False))


@app.command("gusto")
def likes(as_json: bool = JsonOpt) -> None:
    """Lo que umbra sabe de tu gusto (lo reciben el diseñador y el crítico). Puedes editarlo."""
    from umbra.management import taste
    data = {"path": taste.path().as_posix(), "text": taste.load()}
    emit(data, as_json, lambda c: c.print(
        (data["text"] or "Todavía nada: se llena con lo que eliges, pides y apruebas.")
        + f"\n\n({data['path']})", highlight=False, markup=False))


@app.command("sistemas")
def systems(as_json: bool = JsonOpt) -> None:
    """Los sistemas de diseño de tu catálogo (~/.umbra/design y paquetes)."""
    from umbra.management import design_systems as ds
    found = ds.catalog()

    def render(c) -> None:
        if not found:
            c.print("No hay sistemas: crea ~/.umbra/design/<sistema>/sistema.toml "
                    "(ver docs/usage.md).")
        for key, s in found.items():
            c.print(f"{key}: {s['nombre']}" + (f" — {s['descripcion']}" if s["descripcion"]
                                              else ""), highlight=False, markup=False)
    emit(found, as_json, render)


@app.command("sistema")
def system(name: str = typer.Argument(None, help="Sistema del catálogo, o «ninguno»")) -> None:
    """El sistema de diseño del proyecto: sin argumento lo muestra; con él, lo cambia."""
    from umbra.management import design_systems as ds
    ctx = context.load(False)
    if not name:
        current = ds.chosen(ctx.config)
        print(f"Sistema de diseño: {current or 'sin elegir'}. Disponibles: "
              + ", ".join(k for k, _ in ds.choices()))
        return
    try:
        ds.set_system(ctx.root, name)
    except ValueError as e:
        fail(str(e))
    print(f"Este proyecto usa ahora el sistema de diseño «{name}» (en .umbra/project.toml).")


def ask_system(root, config) -> None:
    """Antes de una spec: si hay catálogo y el proyecto no eligió sistema, pregunta."""
    from umbra.management import design_systems as ds
    if not ds.needs_choice(config):
        return
    options = ds.choices()
    print("¿Qué sistema de diseño usa este proyecto?")
    for i, (_, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    pick = typer.prompt("Número", default=str(len(options)))
    try:
        key = options[int(pick) - 1][0]
    except (ValueError, IndexError):
        key = ds.NONE
    ds.set_system(root, key)
    print(f"Guardado: sistema «{key}».")


@app.command("replicar")
def replicate(yes: bool = typer.Option(False, "--yes", "-y", help="Aprobar sin preguntar")) -> None:
    """Replica el diseño actual de la app en design/: una captura por vista con su índice, el
    sistema visual extraído del código y, con tu herramienta conectada, tableros «Actual · X»."""
    from umbra.management import replica
    ctx = context.load(False)
    try:
        r = replica.replicate(ctx.conn, ctx.root, ctx.udir, ctx.config)
        print(f"{len(r['images'])} vistas replicadas en design/actual/.\n{r['summary']}")
        for f in replica.pending(r["root"]):
            print(f"  {f}")
        if yes or typer.confirm(f"¿Guardas la réplica en {r['root'].name}?"):
            sha = replica.accept(ctx.conn, r["root"])
            print(f"Réplica guardada (commit {sha[:10]}).")
        else:
            replica.discard(ctx.conn, r["root"])
            print("Réplica descartada.")
    except replica.ReplicaError as e:
        fail(str(e))
