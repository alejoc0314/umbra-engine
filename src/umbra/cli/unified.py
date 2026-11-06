"""Comandos del grupo Unified: init, doctor, status."""

import sys
from pathlib import Path

import typer
from rich.table import Table

from umbra import service
from umbra.unified import doctor as doctor_mod
from umbra.unified import explain, project, store
from umbra.unified.output import console, emit, fail

JsonOpt = typer.Option(False, "--json", help="Salida en JSON")


def init(yes: bool = typer.Option(False, "--yes", "-y", help="Crear el espacio sin preguntar"),
         as_json: bool = JsonOpt) -> None:
    """Crea .umbra/ en el repo actual y propone comandos según el stack. En una carpeta con
    varios repos (front y back, por ejemplo), crea un espacio de trabajo con todos ellos."""
    cwd = Path.cwd()
    if (not yes and not as_json and sys.stdin.isatty() and project.find_workspace(cwd) is None
            and project._git_root(cwd) is None):
        repos = project.child_repos(cwd)
        if len(repos) >= 2 and not typer.confirm(
                f"Crear un espacio de trabajo con {', '.join(repos)} (integrados en ese orden; "
                "luego lo puedes cambiar en .umbra/project.toml)?", default=True):
            raise typer.Exit(1)
    try:
        result = project.init_project(cwd)
    except (project.NotARepo, project.NotInitialized) as e:
        fail(str(e), code=2, as_json=as_json)

    def render(c):
        if result.get("workspace"):
            verb = "creado" if result["created"] else "ya existía"
            c.print(f"[green]espacio de trabajo {verb}[/green] en {result['root']}")
            for r in result["repos"]:
                c.print(f"  {r['name']} (stack: {r['stack']})")
            c.print("Orden de integración en [workspace] repos de .umbra/project.toml; los comandos"
                    " de cada repo, en su propio .umbra/project.toml.", markup=False)
            return
        if result["created"]:
            c.print(f"[green]umbra inicializado[/green] en {result['root']} "
                    f"(stack: {result['stack']})")
        else:
            c.print(f"ya estaba inicializado en {result['root']}; no se cambió nada")
        for name, cmd in result["commands"].items():
            c.print(f"  {name}: {cmd}")

    emit(result, as_json, render)


def doctor(as_json: bool = JsonOpt) -> None:
    """Comprueba git, gh, claude y codex: versión y sesión."""
    result = doctor_mod.diagnose()

    def render(c):
        table = Table("herramienta", "tipo", "versión", "sesión")
        for t in result["tools"]:
            if not t["found"]:
                table.add_row(t["name"], t["kind"], "[red]no encontrada[/red]", "-")
                continue
            session = {True: "[green]ok[/green]", False: "[red]sin sesión[/red]",
                       None: "-"}[t["session"]]
            table.add_row(t["name"], t["kind"], t["version"] or "?", session)
        c.print(table)
        c.print("[green]listo[/green]" if result["ok"] else
                "[red]faltan herramientas: se requieren git, gh y al menos un agente[/red]")

    emit(result, as_json, render)
    if not result["ok"]:
        raise typer.Exit(1)


def watch(all_: bool = typer.Option(False, "--all",
                                    help="Todos tus repos con umbra; Enter entra en uno")) -> None:
    """Vista en vivo: tareas, etapas con duración y costo, y eventos (q para salir)."""
    from umbra.cli.watch import WatchApp  # textual solo se carga si se usa
    if all_:
        from umbra.cli.projects_screen import ProjectsApp
        from umbra.management import projects
        while True:
            rows = projects.overview()
            if not rows:
                fail("ningún repo registrado todavía: umbra init (o umbra new) en cada uno",
                     code=2)
            chosen = ProjectsApp(rows).run()
            if not chosen:
                return
            if WatchApp(Path(chosen) / project.UMBRA_DIR, all_projects=True).run() != "projects":
                return
    try:
        _, udir = project.umbra_dir(Path.cwd())
    except (project.NotARepo, project.NotInitialized) as e:
        fail(str(e), code=2)
    WatchApp(udir).run()


def projects_cmd(as_json: bool = JsonOpt) -> None:
    """Tus repos con umbra: cuántas tareas te necesitan, cuántas en marcha y el gasto."""
    from umbra.management import projects
    rows = projects.overview()

    def render(c):
        if not rows:
            c.print("ningún repo registrado todavía: umbra init (o umbra new) en cada uno")
            return
        t = Table("proyecto", "stack", "te necesitan", "en marcha", "gasto", "ruta")
        for p in rows:
            t.add_row(p["name"], p.get("stack", "-"), str(p["needs"]), str(p["working"]),
                      p["cost"], p["root"])
        c.print(t)

    emit(rows, as_json, render)


def new(name: str,
        stack: str = typer.Option(..., "--stack", "-s", help="Playbook: python, node, laravel…"),
        remote: bool = typer.Option(True, "--remote/--no-remote",
                                    help="Crear el repo privado en GitHub y publicar"),
        context: bool = typer.Option(True, "--context/--no-context",
                                     help="Generar CONTEXT.md con el cartógrafo"),
        idea: str | None = typer.Option(None, "--idea", help="Abre la primera spec con esta idea"),
        as_json: bool = JsonOpt) -> None:
    """Crea un proyecto desde un playbook: repo, CI, convenciones, .umbra y CONTEXT.md."""
    try:
        result = service.new_project(name, stack, Path.cwd(), remote, context, idea)
    except service.OpError as e:
        fail(str(e), code=e.code, as_json=as_json)

    def render(c):
        c.print(f"[green]proyecto creado[/green] en {result['root']} ({result['stack']}): "
                + ", ".join(result["steps"]), highlight=False)
        if result.get("remote_error"):
            c.print(f"[yellow]sin repo en GitHub[/yellow]: {result['remote_error']}",
                    highlight=False, markup=True)
        if result.get("context_error"):
            c.print(f"[yellow]CONTEXT.md[/yellow]: {result['context_error']}", highlight=False)
        if result.get("conversation"):
            c.print(f"spec abierta con tu idea: cd {name} && umbra spec resume")
        else:
            c.print(f"siguiente: cd {name} && umbra spec new \"tu idea\" (o umbra task add)")

    emit(result, as_json, render)


playbook_app = typer.Typer(help="Playbooks: cómo arranca un proyecto nuevo de cada stack.")


@playbook_app.command("list")
def playbook_list(as_json: bool = JsonOpt) -> None:
    """Los playbooks disponibles (los del equipo pisan a los de umbra)."""
    from umbra.management import playbooks
    found = {k: v.as_posix() for k, v in playbooks.available().items()}
    emit(found, as_json, lambda c: [c.print(f"  {k}: {v}", highlight=False)
                                    for k, v in found.items()])


@playbook_app.command("sync")
def playbook_sync(url: str) -> None:
    """Trae (o pone al día) los playbooks del equipo desde un repo git a ~/.umbra/playbooks."""
    from umbra.management import playbooks
    try:
        what = playbooks.sync(url)
    except playbooks.PlaybookError as e:
        fail(str(e), code=3)
    console.print(f"playbooks {what} en {playbooks.home()}", highlight=False)


pack_app = typer.Typer(help="Paquetes: perfiles, rutinas y playbooks que viven fuera del repo.")


@pack_app.command("sync")
def pack_sync(url: str, name: str = typer.Option(None, "--name",
                                                  help="Carpeta en ~/.umbra/packs")) -> None:
    """Clona (o pone al día) un paquete desde un repo git en ~/.umbra/packs/<nombre>."""
    from umbra.management import packs
    try:
        what, dest = packs.sync(url, name)
    except packs.PackError as e:
        fail(str(e), code=3)
    console.print(f"paquete {what} en {dest.as_posix()}", highlight=False)


@pack_app.command("list")
def pack_list(as_json: bool = JsonOpt) -> None:
    """Los paquetes instalados y qué aporta cada uno."""
    from umbra.management import packs
    found = packs.installed()

    def render(c) -> None:
        if not found:
            c.print("No hay paquetes. Instala uno con: umbra pack sync <repo-git>")
        for p in found:
            c.print(f"{p['name']}  ({p['path']})", highlight=False)
            for kind in ("profiles", "routines", "playbooks"):
                if p[kind]:
                    c.print(f"  {kind}: {', '.join(p[kind])}", highlight=False)
    emit(found, as_json, render)


def metrics(as_json: bool = JsonOpt) -> None:
    """Tiempo hasta PR y merge, costo, ciclos de corrección y aceptación inicial."""
    from umbra.unified.metrics import compute
    try:
        _, udir = project.umbra_dir(Path.cwd())
    except (project.NotARepo, project.NotInitialized) as e:
        fail(str(e), code=2, as_json=as_json)
    result = compute(store.open_store(udir))

    def fmt(seconds):
        return "-" if seconds is None else f"{seconds / 60:.1f} min"

    def render(c):
        t = Table("#", "tarea", "estado", "hasta PR", "hasta merge", "ciclos", "costo")
        for r in result["runs"]:
            t.add_row(str(r["task"]), r["title"], r["status"], fmt(r["time_to_pr_s"]),
                      fmt(r["time_to_merge_s"]), str(r["fix_cycles"] + r["reworks"]),
                      f"${r['cost']}")
        c.print(t)
        s = result["summary"]
        c.print(f"ejecuciones {s['runs']} · integradas {s['merged']} · bloqueadas "
                f"{s['blocked']} · fallidas {s['failed']}")
        c.print(f"promedio hasta PR {fmt(s['avg_time_to_pr_s'])} · hasta merge "
                f"{fmt(s['avg_time_to_merge_s'])} · aceptación inicial "
                f"{s['first_pass_rate'] if s['first_pass_rate'] is not None else '-'}")
        c.print(f"gasto total ${s['total_cost']} · costo por entrega "
                f"{'$' + s['cost_per_delivery'] if s['cost_per_delivery'] else '-'}")

    emit(result, as_json, render)


def status(as_json: bool = JsonOpt) -> None:
    """Tareas, ejecuciones activas y gasto del proyecto."""
    try:
        root, udir = project.umbra_dir(Path.cwd())
    except (project.NotARepo, project.NotInitialized) as e:
        fail(str(e), code=2, as_json=as_json)
    conn = store.open_store(udir)
    result = store.status_summary(conn)
    result["specs"] = service.spec_progress(service.Ctx(root, udir, conn, {}))
    attention, working = [], []
    for task in conn.execute("SELECT * FROM task WHERE status = 'accepted' ORDER BY number"):
        exp = explain.explain_number(conn, udir, task)
        item = {"task": task["number"], "title": explain.task_title(task),
                "situation": explain.short(exp),
                "headline": exp.headline}
        if exp.state.startswith(("Detenida", "Falló", "Espera tu")):
            attention.append(item)
        elif exp.state in ("Trabajando", "En cola", "En pausa"):
            working.append(item)
    result["attention"], result["working"] = attention, working

    def render(c):
        t = result["tasks"]
        c.print(f"Tareas: {t['accepted']} aceptadas · {t['draft']} en borrador · "
                f"{t['done']} hechas · {t['dropped']} descartadas")
        if attention:
            c.print("\n[bold]Necesitan tu atención[/bold]")
            for a in attention:
                c.print(f"  {a['task']} · {a['title']}\n      {a['situation']}\n"
                        f"      [cyan]umbra explain {a['task']}[/cyan]")
        if working:
            c.print("\n[bold]En marcha[/bold]")
            for w in working:
                c.print(f"  {w['task']} · {w['title']}: {w['headline']}")
        if not attention and not working:
            c.print("\nNada en marcha ni pendiente de tu decisión.")
        if result["specs"]:
            c.print("\n[bold]Specs[/bold]")
            for p in result["specs"]:
                c.print(f"  {explain.spec_line(p)}", highlight=False)
        s = result["spend"]
        c.print(f"\nGasto acumulado: {explain.spend_text(s['total'], result['unpriced_tokens'])}",
                highlight=False)

    emit(result, as_json, render)
