"""Comandos del grupo Management: tareas."""

import getpass
import json
from pathlib import Path

import typer
from rich.table import Table

from umbra import service
from umbra.cli import context
from umbra.management import planning
from umbra.unified import explain
from umbra.unified.events import add_event
from umbra.unified.output import emit, fail
from umbra.unified.store import new_id, now

app = typer.Typer(help="Tareas: registrar, listar y ajustar.", no_args_is_help=True)
JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


@app.command("add")
def add(
    title: str,
    description: str = typer.Option("", "--description", "-d"),
    about: str = typer.Option("", "--about", help="De qué trata, en lenguaje llano"),
    accept: list[str] = typer.Option([], "--accept", "-a", help="Criterio de aceptación"),
    scope: list[str] = typer.Option([], "--scope", "-s", help="Ruta dentro del alcance"),
    priority: int = typer.Option(2, "--priority", "-p", min=1, max=3),
    draft: bool = typer.Option(False, "--draft", help="Crear como borrador"),
    repo: list[str] = typer.Option([], "--repo", "-r",
                                   help="En un espacio de trabajo: repo donde se hace"),
    as_json: bool = JsonOpt,
) -> None:
    """Registra una tarea (aceptada salvo --draft)."""
    ctx = context.load(as_json)
    try:
        service.check_repos(ctx, repo, "la tarea")
    except service.OpError as e:
        fail(f"{e}: indícalo con --repo", code=e.code, as_json=as_json)
    number = ctx.conn.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM task").fetchone()[0]
    ctx.conn.execute(
        "INSERT INTO task (id, number, title, about, description, acceptance, scope, priority,"
        " status, repos, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (new_id(), number, title, about, description, json.dumps(accept, ensure_ascii=False),
         json.dumps(scope), priority, "draft" if draft else "accepted", json.dumps(repo), now(),
         now()))
    add_event(ctx.conn, None, "task.added", "cli", number=number, title=title)
    result = {"number": number, "title": title, "status": "draft" if draft else "accepted"}
    emit(result, as_json, lambda c: c.print(f"tarea {number} registrada: {title}"))


def _set_status(op, numbers: list[int], status: str, as_json: bool) -> None:
    ctx = context.load(as_json)
    try:
        changed = op(ctx, numbers)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit({"tasks": changed, "status": status}, as_json,
         lambda c: c.print(f"tareas {', '.join(map(str, changed))}: {status}"))


@app.command("repo")
def repo_(number: int, repos: list[str], as_json: bool = JsonOpt) -> None:
    """En un espacio de trabajo: dice en qué repo (o repos) se hace una tarea."""
    ctx = context.load(as_json)
    try:
        service.set_task_repos(ctx, number, repos)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit({"task": number, "repos": repos}, as_json,
         lambda c: c.print(f"tarea {number}: {' + '.join(repos)}"))


@app.command("accept")
def accept_(numbers: list[int], as_json: bool = JsonOpt) -> None:
    """Acepta tareas en borrador para poder ejecutarlas."""
    _set_status(service.accept, numbers, "accepted", as_json)


@app.command("drop")
def drop(numbers: list[int], as_json: bool = JsonOpt) -> None:
    """Descarta tareas (no se borran: quedan en el historial)."""
    _set_status(service.drop, numbers, "dropped", as_json)


@app.command("edit")
def edit(
    number: int,
    title: str | None = typer.Option(None, "--title"),
    description: str | None = typer.Option(None, "--description", "-d"),
    about: str | None = typer.Option(None, "--about", help="De qué trata, en lenguaje llano"),
    accept: list[str] | None = typer.Option(None, "--accept", "-a",
                                            help="Reemplaza los criterios de aceptación"),
    scope: list[str] | None = typer.Option(None, "--scope", "-s", help="Reemplaza el alcance"),
    priority: int | None = typer.Option(None, "--priority", "-p", min=1, max=3),
    expect_revision: int | None = typer.Option(None, "--expect-revision",
                                               help="Falla si la tarea cambió desde entonces"),
    as_json: bool = JsonOpt,
) -> None:
    """Edita una tarea; incrementa su revisión (control optimista)."""
    ctx = context.load(as_json)
    task = context.task_by_number(ctx, number, as_json)
    fields = {"title": title, "about": about, "description": description, "priority": priority,
              "acceptance": json.dumps(accept, ensure_ascii=False) if accept else None,
              "scope": json.dumps(scope) if scope else None}
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        fail("nada que cambiar", as_json=as_json)
    revision = task["revision"] if expect_revision is None else expect_revision
    sets = ", ".join(f"{k} = ?" for k in fields)
    cur = ctx.conn.execute(
        f"UPDATE task SET {sets}, revision = revision + 1, updated_at = ?"
        " WHERE id = ? AND revision = ?", (*fields.values(), now(), task["id"], revision))
    if cur.rowcount != 1:
        fail(f"conflicto: la tarea {number} está en la revisión {task['revision']}, "
             f"no en la {revision}", code=4, as_json=as_json)
    add_event(ctx.conn, None, "task.edited", "cli", number=number, fields=list(fields))
    emit({"number": number, "revision": revision + 1}, as_json,
         lambda c: c.print(f"tarea {number} actualizada (revisión {revision + 1})"))


@app.command("allow")
def allow(number: int, paths: list[str] = typer.Argument(..., help="Rutas que autorizas"),
          as_json: bool = JsonOpt) -> None:
    """Autoriza cambiar, solo en esta tarea, tests o rutas que la política protege; si la tarea
    estaba detenida por eso, sigue desde Construir."""
    if not service.interactive():
        fail("autorizar lo decide una persona: requiere una terminal interactiva", code=3)
    ctx = context.load(as_json)
    try:
        result = service.allow_paths(ctx, number, paths)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"tarea {number}: autorizado cambiar {', '.join(result['allowed'])}"
        + (f"; sigue desde {result['resumed_from']}" if result["resumed_from"] else "")))


@app.command("answer")
def answer(number: int, text: str = typer.Argument(..., help="Tu respuesta al agente"),
           as_json: bool = JsonOpt) -> None:
    """Responde las preguntas del agente; la tarea sigue desde donde se detuvo."""
    ctx = context.load(as_json)
    try:
        result = service.answer(ctx, number, text)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)
    emit(result, as_json, lambda c: c.print(
        f"tarea {number}: respuesta registrada; sigue desde {result['resumed_from']}"))


@app.command("deps")
def deps(
    number: int,
    on: list[int] = typer.Option(..., "--on", help="Tarea de la que depende"),
    remove: bool = typer.Option(False, "--remove", help="Quitar la dependencia"),
    as_json: bool = JsonOpt,
) -> None:
    """Declara (o quita) dependencias; rechaza ciclos."""
    ctx = context.load(as_json)
    task = context.task_by_number(ctx, number, as_json)
    for m in on:
        dep = context.task_by_number(ctx, m, as_json)
        if remove:
            ctx.conn.execute("DELETE FROM dependency WHERE task_id = ? AND depends_on_id = ?",
                             (task["id"], dep["id"]))
            continue
        if m == number or planning.would_cycle(ctx.conn, task["id"], dep["id"]):
            fail(f"la dependencia {number} → {m} crea un ciclo", code=4, as_json=as_json)
        ctx.conn.execute("INSERT OR IGNORE INTO dependency (task_id, depends_on_id)"
                         " VALUES (?, ?)", (task["id"], dep["id"]))
    add_event(ctx.conn, None, "task.deps", "cli", number=number, on=on, remove=remove)
    current = [r[0] for r in ctx.conn.execute(
        "SELECT t.number FROM dependency d JOIN task t ON t.id = d.depends_on_id"
        " WHERE d.task_id = ? ORDER BY t.number", (task["id"],))]
    emit({"number": number, "depends_on": current}, as_json,
         lambda c: c.print(f"tarea {number} depende de: {current or 'ninguna'}"))


@app.command("list")
def list_(as_json: bool = JsonOpt) -> None:
    """Lista las tareas con su última ejecución."""
    ctx = context.load(as_json)
    rows = [dict(r) for r in ctx.conn.execute(
        "SELECT t.number, t.title, t.status, t.priority,"
        " (SELECT r.status FROM run r WHERE r.task_id = t.id ORDER BY r.created_at DESC LIMIT 1)"
        " AS run_status FROM task t ORDER BY t.number")]

    for r in rows:
        task = ctx.conn.execute("SELECT * FROM task WHERE number = ?", (r["number"],)).fetchone()
        r["waiting_on"] = planning.pending_dependencies(ctx.conn, task["id"])
        r["situation"] = explain.short(explain.explain_number(ctx.conn, ctx.udir, task))
        r["title"], r["repos"] = explain.task_title(task), json.loads(task["repos"] or "[]")

    def render(c):
        table = Table("#", "tarea", "situación", "prioridad", "espera a")
        for r in rows:
            style = ("yellow" if r["situation"].startswith("Detenida") else
                     "red" if r["situation"].startswith("Falló") else
                     "cyan" if r["situation"].startswith(("Espera tu", "Trabajando")) else "")
            table.add_row(str(r["number"]), r["title"], f"[{style}]{r['situation']}[/]"
                          if style else r["situation"], str(r["priority"]),
                          ", ".join(map(str, r["waiting_on"])) or "-")
        c.print(table)
        if any(r["situation"].startswith(("Detenida", "Falló")) for r in rows):
            c.print("[dim]Para entender por qué una tarea se detuvo: umbra explain <n>[/dim]")

    emit(rows, as_json, render)


def plan(
    spec: Path = typer.Argument(..., exists=True, dir_okay=False, help="Spec en Markdown"),
    profile: str = typer.Option("proposer", "--profile"),
    as_json: bool = JsonOpt,
) -> None:
    """Guarda la spec y propone tareas en borrador (revísalas antes de aceptarlas)."""
    ctx = context.load(as_json)
    body = spec.read_text(encoding="utf-8")
    spec_id, version, created = planning.save_spec(ctx.conn, body, getpass.getuser())
    try:
        proposal = planning.propose(ctx.root, ctx.udir, ctx.conn, body, version, profile)
        if proposal.questions:
            result = {"spec_version": version, "questions": proposal.questions, "tasks": []}
        else:
            numbers = planning.insert_proposals(ctx.conn, spec_id, proposal)
            result = {"spec_version": version, "questions": [], "tasks": numbers}
    except planning.PlanningError as e:
        fail(str(e), as_json=as_json)

    def render(c):
        c.print(f"spec v{version} ({'nueva' if created else 'sin cambios'})")
        if result["questions"]:
            c.print("[yellow]el proponente necesita aclaraciones:[/yellow]")
            for q in result["questions"]:
                c.print(f"  - {q}")
        else:
            c.print(f"tareas en borrador: {result['tasks']}. Revísalas con `umbra task list` "
                    "y acéptalas con `umbra task accept`.")

    emit(result, as_json, render)
